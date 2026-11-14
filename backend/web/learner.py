"""Local learner workspace. The cookie identifies a browser, not a production account."""
import hashlib
import secrets
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from db import transaction, one, rows, Json
from bootstrap import APP
from processing import chunks

COOKIE='mdd_learner'
JOIN="""SELECT i.*,b.material_id,m.name AS material_name FROM items i
 JOIN batches b ON b.id=i.batch_id JOIN materials m ON m.id=b.material_id """

class Payload(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Start(Payload):
    mode:str=Field(default='all',pattern='^(all|wrong)$')
    material_id:str=''
    kind:str=Field(default='',pattern='^(|single_choice|multiple_choice|true_false)$')
    tag:str=Field(default='',max_length=200)
    count:int=Field(default=10,ge=1,le=50)
class Answer(Payload):
    item_id:str
    version:int
    selected:list[StrictInt]=Field(min_length=1,max_length=4)
class Rating(Payload):
    version:int
    rating:str=Field(pattern='^(again|unsure|remembered)$')

def identity(request):
    token=request.cookies.get(COOKIE,'')
    if not token:return None
    return one('SELECT id FROM learners WHERE token_hash=%s',(hashlib.sha256(token.encode()).hexdigest(),))

def require_learner(request):
    person=identity(request)
    if not person:raise HTTPException(401,'学习档案已失效，请刷新页面')
    return person['id']

def published(item_id,cur=None):
    if cur:
        cur.execute(JOIN+" WHERE i.id=%s AND i.status='approved' FOR SHARE OF i",(item_id,));item=cur.fetchone()
    else:item=one(JOIN+" WHERE i.id=%s AND i.status='approved'",(item_id,))
    if not item:raise HTTPException(404,'内容已撤回或尚未通过审核')
    return item

def question(item):
    c=item['current']
    return dict(id=item['id'],version=item['version'],kind=item['kind'],prompt=c['prompt'],
                options=c.get('options',[]),difficulty=c.get('difficulty','基础'),tags=c.get('tags',[]),
                material_id=item['material_id'],material_name=item['material_name'])

def solution(item):
    return {**question(item),'answer':item['current']['answer'],
            'answer_indices':item['current'].get('answer_indices',[]),
            'ai_explanation':item['current'].get('ai_explanation',''),
            'evidence':item['evidence'].get('evidence',[]),
            'answer_origin':item['evidence'].get('answer_origin','material'),
            'learning_quality':item['evidence'].get('learning_quality')}

def latest_attempts(learner):
    return rows("""SELECT DISTINCT ON (a.item_id) a.item_id,a.correct,a.item_version,a.created_at
       FROM practice_attempts a JOIN practice_sessions s ON s.id=a.session_id
       WHERE s.learner_id=%s ORDER BY a.item_id,a.id DESC""",(learner,))

def catalog(learner):
    data=rows(JOIN+" WHERE i.status='approved' ORDER BY i.created_at,i.id")
    latest={x['item_id']:x for x in latest_attempts(learner)}
    ratings={x['item_id']:x for x in rows('SELECT * FROM card_progress WHERE learner_id=%s',(learner,))}
    result=[]
    for item in data:
        q=question(item);attempt=latest.get(item['id']);rating=ratings.get(item['id'])
        q['last_correct']=attempt['correct'] if attempt and attempt['item_version']==item['version'] else None
        q['rating']=rating['rating'] if rating and rating['item_version']==item['version'] else None
        result.append(q)
    return result

def build_router(csrf):
    router=APIRouter()
    @router.get('/learn')
    @router.get('/learn/')
    def page():return FileResponse(APP/'web/static/learner.html')
    @router.get('/static/learner.css')
    def style():return FileResponse(APP/'web/static/learner.css',media_type='text/css')
    @router.get('/static/learner.js')
    def script():return FileResponse(APP/'web/static/learner.js',media_type='application/javascript')

    @router.get('/api/learn/bootstrap')
    def bootstrap(request:Request,response:Response):
        person=identity(request)
        if not person:
            token=secrets.token_urlsafe(32);person={'id':secrets.token_hex(16)}
            with transaction() as cur:
                cur.execute('INSERT INTO learners(id,token_hash) VALUES(%s,%s)',(person['id'],hashlib.sha256(token.encode()).hexdigest()))
            response.set_cookie(COOKIE,token,max_age=365*86400,httponly=True,samesite='strict',secure=request.url.scheme=='https',path='/')
        return {'csrf':csrf,'profile_label':'本机学习档案 '+person['id'][:6],
                'identity_note':'同一浏览器保留学习档案；清除 Cookie 或换浏览器会建立新档案。尚未接入正式账号登录。'}

    @router.get('/api/learn/catalog')
    def library(request:Request):return catalog(require_learner(request))

    @router.get('/api/learn/progress')
    def progress(request:Request):
        learner=require_learner(request)
        stats=one("""SELECT count(*)::int AS attempts,count(*) FILTER (WHERE correct)::int AS correct,
          count(*) FILTER (WHERE (a.created_at AT TIME ZONE 'Asia/Shanghai')::date=(now() AT TIME ZONE 'Asia/Shanghai')::date)::int AS today
          FROM practice_attempts a JOIN practice_sessions s ON s.id=a.session_id WHERE s.learner_id=%s""",(learner,))
        sessions=rows("""SELECT s.id,s.mode,s.created_at,jsonb_array_length(s.questions) AS total,
          count(a.id)::int AS answered,count(a.id) FILTER (WHERE a.correct)::int AS correct
          FROM practice_sessions s LEFT JOIN practice_attempts a ON a.session_id=s.id
          WHERE s.learner_id=%s GROUP BY s.id ORDER BY s.created_at DESC LIMIT 20""",(learner,))
        return {'stats':stats,'sessions':sessions}

    @router.post('/api/learn/sessions')
    def start(body:Start,request:Request):
        learner=require_learner(request)
        data=[x for x in catalog(learner) if x['kind']!='card'
              and (not body.material_id or x['material_id']==body.material_id)
              and (not body.kind or x['kind']==body.kind)
              and (not body.tag or body.tag in x['tags'])
              and (body.mode!='wrong' or x['last_correct'] is False)]
        # Prefer unseen questions; never manufacture a requested quantity.
        data.sort(key=lambda x:x['last_correct'] is not None)
        chosen=[{'id':x['id'],'version':x['version']} for x in data[:body.count]]
        if not chosen:raise HTTPException(422,'当前条件下没有可练习的已审核题目')
        sid=secrets.token_hex(16)
        with transaction() as cur:
            cur.execute('INSERT INTO practice_sessions(id,learner_id,questions,mode) VALUES(%s,%s,%s,%s)',(sid,learner,Json(chosen),body.mode))
        return {'id':sid,'total':len(chosen),'requested':body.count}

    def owned_session(sid,learner,cur=None):
        sql='SELECT * FROM practice_sessions WHERE id=%s AND learner_id=%s'
        if cur:
            cur.execute(sql+' FOR UPDATE',(sid,learner));s=cur.fetchone()
        else:s=one(sql,(sid,learner))
        if not s:raise HTTPException(404,'练习记录不存在')
        return s

    @router.get('/api/learn/sessions/{sid}')
    def session(sid:str,request:Request):
        s=owned_session(sid,require_learner(request));result=[]
        attempts={a['item_id']:a for a in rows('SELECT * FROM practice_attempts WHERE session_id=%s',(sid,))}
        for ref in s['questions']:
            item=one(JOIN+" WHERE i.id=%s AND i.status='approved' AND i.version=%s",(ref['id'],ref['version']))
            if not item:
                result.append({'id':ref['id'],'unavailable':True});continue
            q=question(item);a=attempts.get(ref['id'])
            if a:q['result']={'correct':a['correct'],'selected':a['selected'],'solution':a['snapshot']}
            result.append(q)
        return {'id':sid,'questions':result,'created_at':s['created_at'],'mode':s['mode']}

    @router.post('/api/learn/sessions/{sid}/answer')
    def answer(sid:str,body:Answer,request:Request):
        learner=require_learner(request)
        with transaction() as cur:
            s=owned_session(sid,learner,cur)
            if not any(x['id']==body.item_id and x['version']==body.version for x in s['questions']):
                raise HTTPException(409,'题目不属于本次练习或版本已变更')
            item=published(body.item_id,cur)
            if item['version']!=body.version:raise HTTPException(409,'题目已更新，请重新开始练习')
            cur.execute('SELECT * FROM practice_attempts WHERE session_id=%s AND item_id=%s',(sid,body.item_id));old=cur.fetchone()
            selected=sorted(body.selected)
            if old:
                if old['selected']!=selected:raise HTTPException(409,'本题已提交，可在新练习中重新作答')
                return {'correct':old['correct'],'selected':old['selected'],'solution':old['snapshot']}
            options=item['current'].get('options',[])
            if len(set(selected))!=len(selected) or any(n<0 or n>=len(options) for n in selected):raise HTTPException(422,'选项无效')
            if item['kind'] in ['single_choice','true_false'] and len(selected)!=1:raise HTTPException(422,'本题只能选择一个选项')
            expected=item['current'].get('answer_indices',[])
            if item['kind']=='card' or not expected:raise HTTPException(409,'当前内容不能用于答题')
            correct=selected==sorted(expected);snapshot=solution(item)
            cur.execute('INSERT INTO practice_attempts(session_id,item_id,item_version,selected,correct,snapshot) VALUES(%s,%s,%s,%s,%s,%s)',
                        (sid,item['id'],item['version'],Json(selected),correct,Json(snapshot)))
        return {'correct':correct,'selected':selected,'solution':snapshot}

    @router.get('/api/learn/cards/{item_id}')
    def card(item_id:str,request:Request):
        require_learner(request);item=published(item_id)
        if item['kind']!='card':raise HTTPException(404,'知识卡不存在')
        return solution(item)

    @router.post('/api/learn/cards/{item_id}/rating')
    def rate(item_id:str,body:Rating,request:Request):
        learner=require_learner(request)
        with transaction() as cur:
            item=published(item_id,cur)
            if item['kind']!='card' or item['version']!=body.version:raise HTTPException(409,'知识卡已更新，请重新打开')
            cur.execute("""INSERT INTO card_progress(learner_id,item_id,item_version,rating) VALUES(%s,%s,%s,%s)
              ON CONFLICT(learner_id,item_id) DO UPDATE SET item_version=excluded.item_version,rating=excluded.rating,
              reviews=card_progress.reviews+1,updated_at=now()""",(learner,item_id,body.version,body.rating))
        return {'saved':True}

    @router.get('/api/learn/items/{item_id}/source/{source_id}')
    def source(item_id:str,source_id:str,request:Request):
        require_learner(request);item=published(item_id)
        if not any(e['source_id']==source_id for e in item['evidence'].get('evidence',[])):raise HTTPException(404,'非本条内容的出处')
        material=one('SELECT * FROM materials WHERE id=%s',(item['material_id'],));parts=chunks(material)
        for index,part in enumerate(parts):
            if part['source_id']==source_id:
                return {'material_name':material['name'],'selected':part,'context':[p for p in parts[max(0,index-2):index+3]
                    if 'courseware_id' not in part or p.get('courseware_id')==part['courseware_id']]}
        raise HTTPException(404,'原文片段不存在')
    return router
