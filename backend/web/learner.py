"""Local learner workspace. The cookie identifies a browser, not a production account."""
import hashlib
import secrets
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from db import transaction, one, rows, Json
from bootstrap import APP
from processing import chunks
import httpx
from models import resolve_key, normalize_url

COOKIE='mdd_learner'
JOIN="""SELECT i.*,b.material_id,m.name AS material_name FROM items i
 JOIN batches b ON b.id=i.batch_id JOIN materials m ON m.id=b.material_id """
DAILY='(created_at AT TIME ZONE \'Asia/Shanghai\')::date=(now() AT TIME ZONE \'Asia/Shanghai\')::date'
LEVEL_NAMES=['见习学徒','初出茅庐','勤学新秀','知识行者','题海健将','百题斩将','记忆大师','学海宗师']
NICK_ADJ=['勤学的','好奇的','专注的','闪闪的','稳扎的','爱问的','早起的','笃定的']
NICK_NOUN=['墨小喵','答题侠','小书虫','星星官','墨豆豆','知识兔','小灯塔','墨小狮']
ASK_DAILY_LIMIT=20

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
class Ask(Payload):
    question:str=Field(min_length=2,max_length=500)

def identity(request):
    token=request.cookies.get(COOKIE,'')
    if token:
        found=one('SELECT id FROM learners WHERE token_hash=%s',(hashlib.sha256(token.encode()).hexdigest(),))
        if found:return found
    # callContainer gateway injects the WeChat openid header; fall back to it so
    # progress survives a lost cookie on the same WeChat account.
    openid=(request.headers.get('x-wx-openid') or '').strip()
    if openid:return one('SELECT id FROM learners WHERE openid=%s',(openid[:128],))
    return None

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

def award(cur,learner,kind,xp,item_id=None):
    cur.execute('INSERT INTO xp_events(learner_id,kind,xp,item_id) VALUES(%s,%s,%s,%s)',(learner,kind,xp,item_id))
    return xp

def level_of(xp):
    level=1
    while level<len(LEVEL_NAMES)+40 and xp>=50*level*(level+1):level+=1
    floor=50*(level-1)*level;ceiling=50*level*(level+1)
    return {'level':level,'level_name':LEVEL_NAMES[min(level-1,len(LEVEL_NAMES)-1)],
            'level_floor':floor,'level_ceiling':ceiling}

def ensure_profile(learner_id):
    row=one('SELECT nickname,id FROM learners WHERE id=%s',(learner_id,))
    if row and not row['nickname']:
        seed=int(row['id'][:8],16)
        nick=NICK_ADJ[seed%len(NICK_ADJ)]+NICK_NOUN[(seed//len(NICK_ADJ))%len(NICK_NOUN)]+'·'+row['id'][:4].upper()
        with transaction() as cur:
            cur.execute("UPDATE learners SET nickname=%s WHERE id=%s AND nickname=''",(nick,learner_id))

def streak_days(learner):
    data=rows("""SELECT DISTINCT day FROM (
      SELECT (created_at AT TIME ZONE 'Asia/Shanghai')::date AS day FROM xp_events WHERE learner_id=%s
      UNION SELECT (a.created_at AT TIME ZONE 'Asia/Shanghai')::date FROM practice_attempts a
        JOIN practice_sessions s ON s.id=a.session_id WHERE s.learner_id=%s
      UNION SELECT (updated_at AT TIME ZONE 'Asia/Shanghai')::date FROM card_progress WHERE learner_id=%s) t
      ORDER BY day DESC LIMIT 400""",(learner,learner,learner))
    days={r['day'] for r in data}
    import datetime
    today=(one("SELECT (now() AT TIME ZONE 'Asia/Shanghai')::date AS d",())or {}).get('d')
    if not days or today is None:return 0
    cursor=today if today in days else today-datetime.timedelta(days=1)
    if cursor not in days:return 0
    streak=0
    while cursor in days:
        streak+=1;cursor-=datetime.timedelta(days=1)
    return streak

def gamification(learner):
    total=one('SELECT coalesce(sum(xp),0)::int AS xp FROM xp_events WHERE learner_id=%s',(learner,))['xp']
    today=one(f'SELECT coalesce(sum(xp),0)::int AS xp FROM xp_events WHERE learner_id=%s AND {DAILY}',(learner,))['xp']
    info=level_of(total)
    nickname=one('SELECT nickname FROM learners WHERE id=%s',(learner,))
    info.update({'xp':total,'today_xp':today,'streak_days':streak_days(learner),
                 'nickname':nickname['nickname'] if nickname else ''})
    return info

def mastery(learner):
    cards=[x for x in catalog(learner) if x['kind']=='card']
    mastered=sum(1 for x in cards if x['rating']=='remembered')
    learning=sum(1 for x in cards if x['rating'] in ('again','unsure'))
    fresh=len(cards)-mastered-learning
    percent=round(mastered*100/len(cards)) if cards else 0
    return {'total':len(cards),'mastered':mastered,'learning':learning,'fresh':fresh,
            'percent':percent,'review_count':learning}

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
        openid=(request.headers.get('x-wx-openid') or '').strip()[:128]
        person=identity(request)
        if openid:
            bound=one('SELECT id FROM learners WHERE openid=%s',(openid,))
            if bound and (not person or person['id']!=bound['id']):
                # Reissue a cookie bound to the WeChat-identified learner.
                token=secrets.token_urlsafe(32)
                with transaction() as cur:
                    cur.execute('UPDATE learners SET token_hash=%s WHERE id=%s',(hashlib.sha256(token.encode()).hexdigest(),bound['id']))
                response.set_cookie(COOKIE,token,max_age=365*86400,httponly=True,samesite='strict',secure=request.url.scheme=='https',path='/')
                person=bound
            elif not bound and person:
                with transaction() as cur:
                    cur.execute('UPDATE learners SET openid=%s WHERE id=%s AND openid IS NULL',(openid,person['id']))
        if not person:
            token=secrets.token_urlsafe(32);person={'id':secrets.token_hex(16)}
            with transaction() as cur:
                cur.execute('INSERT INTO learners(id,token_hash,openid) VALUES(%s,%s,%s)',
                            (person['id'],hashlib.sha256(token.encode()).hexdigest(),openid or None))
            response.set_cookie(COOKIE,token,max_age=365*86400,httponly=True,samesite='strict',secure=request.url.scheme=='https',path='/')
        ensure_profile(person['id'])
        note='同一微信账号自动保留学习档案。' if openid else '同一浏览器保留学习档案；清除 Cookie 或换浏览器会建立新档案。尚未接入正式账号登录。'
        return {'csrf':csrf,'profile_label':'学习档案 '+person['id'][:6],
                'identity_note':note}

    @router.get('/api/learn/dashboard')
    def dashboard(request:Request):
        learner=require_learner(request)
        return {'gamification':gamification(learner),'mastery':mastery(learner)}

    @router.get('/api/learn/structure')
    def structure_view(request:Request):
        learner=require_learner(request)
        data=rows(JOIN+" WHERE i.status='approved' ORDER BY i.created_at,i.id")
        latest={x['item_id']:x for x in latest_attempts(learner)}
        ratings={x['item_id']:x for x in rows('SELECT * FROM card_progress WHERE learner_id=%s',(learner,))}
        def state_of(item):
            a=latest.get(item['id']);r=ratings.get(item['id'])
            if item['kind']=='card':
                if r and r['item_version']==item['version']:return 'remembered' if r['rating']=='remembered' else 'learning'
                return 'fresh'
            if a and a['item_version']==item['version']:return 'mastered' if a['correct'] else 'weak'
            return 'fresh'
        materials={}
        for item in data:
            m=materials.setdefault(item['material_id'],{'id':item['material_id'],'name':item['material_name'],'units':{},'total':0,'done':0})
            evidence=item['evidence']
            if evidence.get('courseware_id'):label='课时 '+str(evidence['courseware_id'])
            elif item['current'].get('tags'):label=item['current']['tags'][0]
            else:label='综合'
            unit=m['units'].setdefault(str(evidence.get('courseware_id') or label),
                {'label':label,'cards':0,'questions':0,'done':0,'fresh':0,'total':0})
            st=state_of(item);is_card=item['kind']=='card'
            unit['cards' if is_card else 'questions']+=1
            unit['total']+=1;m['total']+=1
            if st in ('remembered','mastered'):unit['done']+=1;m['done']+=1
            elif st=='fresh':unit['fresh']+=1
        return [{'id':m['id'],'name':m['name'],'total':m['total'],'done':m['done'],
                 'percent':round(m['done']*100/m['total']) if m['total'] else 0,
                 'units':[{'label':u['label'],'cards':u['cards'],'questions':u['questions'],
                           'done':u['done'],'fresh':u['fresh'],'total':u['total'],
                           'percent':round(u['done']*100/u['total']) if u['total'] else 0}
                          for u in m['units'].values()]}
                for m in materials.values()]

    @router.get('/api/learn/leaderboard')
    def leaderboard(request:Request,period:str='week'):
        learner=require_learner(request)
        if period not in ('week','month'):period='week'
        trunc="date_trunc('week', now() AT TIME ZONE 'Asia/Shanghai') AT TIME ZONE 'Asia/Shanghai'" if period=='week' \
            else "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai') AT TIME ZONE 'Asia/Shanghai'"
        ensure_profile(learner)
        top=rows(f"""SELECT l.id,l.nickname,coalesce(sum(x.xp),0)::int AS xp FROM learners l
          JOIN xp_events x ON x.learner_id=l.id WHERE x.created_at >= {trunc}
          GROUP BY l.id,l.nickname ORDER BY xp DESC,l.id LIMIT 20""")
        my_xp=one(f'SELECT coalesce(sum(xp),0)::int AS xp FROM xp_events WHERE learner_id=%s AND created_at >= {trunc}',(learner,))['xp']
        rank=0
        if my_xp>0:
            rank=one(f"""SELECT count(*)::int+1 AS rank FROM (
              SELECT learner_id,sum(xp) AS total FROM xp_events WHERE created_at >= {trunc} GROUP BY learner_id
            ) s WHERE s.total > %s""",(my_xp,))['rank']
        g=gamification(learner)
        nickname=one('SELECT nickname FROM learners WHERE id=%s',(learner,))['nickname']
        me={'rank':rank,'xp':my_xp,'nickname':nickname,'level':g['level'],'level_name':g['level_name']}
        entries=[{'rank':i+1,'nickname':r['nickname'],'xp':r['xp'],'is_me':r['id']==learner}
                 for i,r in enumerate(top)]
        if my_xp>0 and not any(e['is_me'] for e in entries):
            entries.append(me)
        return {'period':period,'entries':entries,'me':me}

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
                return {'correct':old['correct'],'selected':old['selected'],'solution':old['snapshot'],'xp':0}
            options=item['current'].get('options',[])
            if len(set(selected))!=len(selected) or any(n<0 or n>=len(options) for n in selected):raise HTTPException(422,'选项无效')
            if item['kind'] in ['single_choice','true_false'] and len(selected)!=1:raise HTTPException(422,'本题只能选择一个选项')
            expected=item['current'].get('answer_indices',[])
            if item['kind']=='card' or not expected:raise HTTPException(409,'当前内容不能用于答题')
            correct=selected==sorted(expected);snapshot=solution(item)
            cur.execute('INSERT INTO practice_attempts(session_id,item_id,item_version,selected,correct,snapshot) VALUES(%s,%s,%s,%s,%s,%s)',
                        (sid,item['id'],item['version'],Json(selected),correct,Json(snapshot)))
            gained=0
            if correct:
                gained+=award(cur,learner,'answer_correct',10,item['id'])
                cur.execute('SELECT correct FROM practice_attempts WHERE session_id=%s ORDER BY id',(sid,))
                run=0
                for r in cur.fetchall():
                    run=run+1 if r['correct'] else 0
                if run%3==0:gained+=award(cur,learner,'streak_bonus',5)
        return {'correct':correct,'selected':selected,'solution':snapshot,'xp':gained}

    @router.get('/api/learn/cards/{item_id}')
    def card(item_id:str,request:Request):
        require_learner(request);item=published(item_id)
        if item['kind']!='card':raise HTTPException(404,'知识卡不存在')
        return solution(item)

    @router.post('/api/learn/cards/{item_id}/rating')
    def rate(item_id:str,body:Rating,request:Request):
        learner=require_learner(request)
        gained=0
        with transaction() as cur:
            item=published(item_id,cur)
            if item['kind']!='card' or item['version']!=body.version:raise HTTPException(409,'知识卡已更新，请重新打开')
            cur.execute('SELECT rating FROM card_progress WHERE learner_id=%s AND item_id=%s FOR UPDATE',(learner,item_id))
            old=cur.fetchone()
            cur.execute("""INSERT INTO card_progress(learner_id,item_id,item_version,rating) VALUES(%s,%s,%s,%s)
              ON CONFLICT(learner_id,item_id) DO UPDATE SET item_version=excluded.item_version,rating=excluded.rating,
              reviews=card_progress.reviews+1,updated_at=now()""",(learner,item_id,body.version,body.rating))
            if body.rating=='remembered' and (not old or old['rating']!='remembered'):
                gained=award(cur,learner,'card_mastered',15,item_id)
        return {'saved':True,'xp':gained}

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

    ASK_SYSTEM=('你是刷题小程序「墨督督」的学习助手。只依据给定的课程资料片段回答学员问题；'
                '用简体中文，先给结论再简要解释，控制在250字以内；'
                '若资料不足以回答，请直说，并建议学员回到课程练习中复习相关知识点；不编造资料之外的事实。')

    def retrieve(question,limit=6):
        items=rows(JOIN+" WHERE i.status='approved'",())
        def score(item):
            c=item['current']
            text=c['prompt']+' '+' '.join(c.get('tags',[]))+' '+c.get('ai_explanation','')
            s=0.0
            for t in c.get('tags',[]):
                if t and t in question:s+=6
            grams={text[i:i+2] for i in range(len(text)-1)}
            if grams:s+=0.1*sum(1 for i in range(len(question)-1) if question[i:i+2] in grams)
            return s
        ranked=sorted(((score(x),x) for x in items),key=lambda p:p[0],reverse=True)
        return [x for s,x in ranked[:limit] if s>0]

    def ask_llm(messages):
        profile=one("SELECT * FROM model_profiles WHERE id='deepseek-default'")
        if not profile:raise HTTPException(409,'答疑模型尚未配置，请联系管理员')
        base_url=normalize_url(profile['base_url'],resolve=True);key=resolve_key(profile)
        payload={'model':profile['model'],'messages':messages,'max_tokens':1024,'stream':False,'temperature':0.3}
        try:
            response=httpx.post(base_url+'/chat/completions',headers={'Authorization':'Bearer '+key},
                                json=payload,timeout=60,follow_redirects=False,trust_env=False)
        except httpx.RequestError:raise HTTPException(502,'答疑服务暂时不可用，请稍后再试')
        if response.status_code!=200:raise HTTPException(502,'答疑服务暂时不可用，请稍后再试')
        raw=response.json()
        with transaction() as cur:
            cur.execute('INSERT INTO calls(job_id,purpose,model,usage,cost,currency,response_id,model_profile_id,model_version) VALUES(NULL,%s,%s,%s,NULL,NULL,%s,%s,%s)',
                        ('learner_ask',raw.get('model',profile['model']),Json(raw.get('usage')),raw.get('id'),profile['id'],profile.get('version')))
        return raw['choices'][0]['message']['content'].strip()

    @router.post('/api/learn/ask')
    def ask(body:Ask,request:Request):
        learner=require_learner(request)
        used=one(f'SELECT count(*)::int AS n FROM ask_logs WHERE learner_id=%s AND {DAILY}',(learner,))['n']
        if used>=ASK_DAILY_LIMIT:raise HTTPException(429,f'今日答疑次数已用完（每天{ASK_DAILY_LIMIT}次），明天再来')
        found=retrieve(body.question)
        if not found:
            return {'answer':'这道题我在当前课程资料里没有找到直接相关的内容。建议你先在「课程练习」里做对应章节的题目，或换个说法再问一次。','grounded':False}
        context='\n'.join(f"{i+1}. 【{'、'.join(x['current'].get('tags',[]))}】{x['current']['prompt']}\n   答案：{x['current']['answer']}\n   解析：{x['current'].get('ai_explanation','')}"
                          for i,x in enumerate(found))
        answer=ask_llm([{'role':'system','content':ASK_SYSTEM},
                        {'role':'user','content':'课程资料片段：\n'+context+'\n\n学员问题：'+body.question}])
        answer=answer[:2000]
        with transaction() as cur:
            cur.execute('INSERT INTO ask_logs(learner_id,question,answer) VALUES(%s,%s,%s)',(learner,body.question,answer))
        return {'answer':answer,'grounded':True}
    return router
