from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
import csv, hashlib, io, json, os, secrets, threading, uuid
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ConfigDict, SecretStr
from fastapi.exceptions import RequestValidationError
from learning_quality import pending_exam_context
from models import PRESETS, profiles, public_profile, snapshot, has_key, add_credential, normalize_url
from db import transaction, one, rows, Json
from bootstrap import initialize, APP, STORAGE
from processing import chunks, validate_content, evidence_errors, worker, stop_event
import pipeline

CSRF=secrets.token_urlsafe(32)
PORT=int(os.getenv('KNOWLEDGE_PORT','4312'))
ORIGINS={f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'}
PUBLIC_ORIGIN=os.getenv('KNOWLEDGE_PUBLIC_ORIGIN','')
if PUBLIC_ORIGIN:
    from urllib.parse import urlsplit
    for _o in PUBLIC_ORIGIN.split(','):
        _o=_o.strip().rstrip('/')
        if not _o:continue
        public_url=urlsplit(_o)
        if public_url.scheme!='https' or not public_url.netloc or public_url.path or public_url.query or public_url.fragment or public_url.username:
            raise RuntimeError('云端访问地址必须是无路径的HTTPS源地址')
        ORIGINS.add(_o)
MAX_UPLOAD=500*1024*1024

@asynccontextmanager
async def lifespan(app):
    initialize()
    thread=None
    if os.getenv('KNOWLEDGE_WORKER','1')=='1':
        with transaction() as cur:
            cur.execute("UPDATE jobs SET state='failed',error='服务中断；生成可能已计费，请核对后手动重试',finished_at=now() WHERE state='running'")
            cur.execute("UPDATE agent_steps SET state='failed',error='服务中断；请核对调用后重试',finished_at=now() WHERE state='running'")
            cur.execute("UPDATE materials SET parse_state='failed',error='解析中断，请重试' WHERE parse_state='parsing'")
        stop_event.clear();thread=threading.Thread(target=worker,daemon=True);thread.start()
    yield
    stop_event.set()
    if thread:thread.join(timeout=2)

app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None)
# 云托管模式：流量经微信内部通道进入，Host 是云托管网关域名，不再限定本机；
# 仍保留 CSRF / Origin / 长度校验，且仅开放学习端使用（工作台上传等大文件接口不对外承诺）。
CLOUD=os.getenv('KNOWLEDGE_CLOUD')=='1'
@app.middleware('http')
async def local_boundary(request,call_next):
    if not CLOUD and request.headers.get('host') not in {f'127.0.0.1:{PORT}',f'localhost:{PORT}'}:
        return JSONResponse({'detail':'仅允许本机访问'},400)
    if request.method not in ['GET','HEAD']:
        if request.headers.get('origin') and request.headers['origin'] not in ORIGINS:return JSONResponse({'detail':'不允许跨站操作'},403)
        if not secrets.compare_digest(request.headers.get('x-csrf-token',''),CSRF):return JSONResponse({'detail':'页面已过期，请刷新后重试'},403)
        length=request.headers.get('content-length')
        if length is None:return JSONResponse({'detail':'缺少请求长度'},411)
        limit=MAX_UPLOAD+1024*1024 if request.url.path=='/api/upload' else 2*1024*1024
        if int(length)>limit:return JSONResponse({'detail':'文件或请求超过大小上限'},413)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'"
    return response

@app.exception_handler(ValueError)
async def bad_value(request,error):return JSONResponse({'detail':str(error)},422)

@app.exception_handler(RequestValidationError)
async def invalid_request(request,error):
    # Pydantic's default errors include submitted input; never echo a submitted Key.
    return JSONResponse({'detail':[{'loc':e['loc'],'msg':e['msg'],'type':e['type']} for e in error.errors()]},422)

class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Edit(StrictModel):
    version:int
    content:dict
    reason:str=Field(min_length=1,max_length=2000)
class ReviewRef(StrictModel):
    id:str
    version:int
class Review(StrictModel):
    items:list[ReviewRef]=Field(min_length=1,max_length=100)
    action:str
    reason:str=Field(default='',max_length=2000)
    evidence_confirmed:bool=False
    confirm_delete:bool=False
class Prompt(StrictModel):
    base_version:int
    content:str=Field(min_length=40,max_length=30000)
class AgentPrompt(Prompt):
    stage:str
class Settings(StrictModel):
    version:int
    model:Optional[str]=Field(default=None,min_length=1,max_length=100,pattern=r'^[a-zA-Z0-9._-]+$')
    daily_call_limit:int=Field(ge=0,le=1000)
    input_price:Optional[float]=Field(default=None,ge=0,le=1000000)
    output_price:Optional[float]=Field(default=None,ge=0,le=1000000)
    currency:str=Field(default='CNY',pattern='^(CNY|USD)$')
class ModelProfile(StrictModel):
    version:Optional[int]=None
    name:str=Field(min_length=1,max_length=100)
    provider:str=Field(min_length=1,max_length=80)
    base_url:str=Field(min_length=1,max_length=500)
    model:str=Field(min_length=1,max_length=150,pattern=r'^[a-zA-Z0-9._:/-]+$')
    json_mode:bool=True
    enabled:bool=True
    api_key:Optional[SecretStr]=None
    input_price:Optional[float]=Field(default=None,ge=0,le=1000000)
    output_price:Optional[float]=Field(default=None,ge=0,le=1000000)
    currency:str=Field(default='CNY',pattern='^(CNY|USD)$')

class Generate(StrictModel):
    model_id:Optional[str]=None
    model_version:Optional[int]=None
    material_id:str
    course:str=''
    start:int=Field(ge=1)
    end:int=Field(ge=1)
    cards:int=Field(ge=0,le=20)
    questions:int=Field(ge=0,le=20)
    question_type:str='single_choice'
    answer_mode:str='allow_inference'

def material_or_404(id):
    m=one('SELECT * FROM materials WHERE id=%s',(id,))
    if not m:raise HTTPException(404,'材料不存在')
    return m

@app.get('/')
def home():return FileResponse(APP/'web/static/index.html')
@app.get('/static/hz-ui-tokens.css')
def ui_tokens():return FileResponse(APP/'web/static/hz-ui-tokens.css',media_type='text/css')

@app.get('/static/workbench.css')
def workbench_style():return FileResponse(APP/'web/static/workbench.css',media_type='text/css')

@app.get('/static/pipeline.js')
def pipeline_script():return FileResponse(APP/'web/static/pipeline.js',media_type='application/javascript')

@app.get('/api/bootstrap')
def bootstrap():
    counts=rows('SELECT status,count(*)::int AS count FROM items GROUP BY status')
    settings=one('SELECT * FROM settings WHERE id=1')
    prompt=one('SELECT * FROM prompt_versions ORDER BY id DESC LIMIT 1')
    return {'csrf':CSRF,'counts':counts,'settings':settings,'key_configured':any(p['key_configured'] and p['enabled'] for p in profiles()),'models':profiles(),'model_presets':PRESETS,'prompt':prompt,'actor':'本机审核人','database':'PostgreSQL','limits':{'upload_mb':500,'workers':1}}

@app.get('/api/materials')
def materials():
    return rows("""SELECT m.id,m.name,m.type,m.sha256,m.size,m.parse_state,m.confirmed,m.error,m.created_at,
    (SELECT count(*) FROM items i JOIN batches b ON b.id=i.batch_id WHERE b.material_id=m.id AND i.status!='deleted') AS generated,
    (SELECT count(*) FROM items i JOIN batches b ON b.id=i.batch_id WHERE b.material_id=m.id AND i.status='approved') AS approved
    FROM materials m ORDER BY created_at""")

@app.get('/api/materials/{id}/preview')
def preview(id:str,course:str='',start:int=1,limit:int=30):
    m=material_or_404(id);all_chunks=chunks(m,course)
    if start<1 or limit<1 or limit>100:raise HTTPException(422,'范围无效')
    return {'name':m['name'],'type':m['type'],'confirmed':m['confirmed'],'state':m['parse_state'],'courses':list((m['parsed'] or {}).get('groups',{})),'total':len(all_chunks),'chunks':all_chunks[start-1:start-1+limit],'limitations':(m['parsed'] or {}).get('limitations',[]),'issues':(m['parsed'] or {}).get('issues',[])}

@app.get('/api/materials/{id}/source/{source_id}')
def source(id:str,source_id:str):
    m=material_or_404(id);rs=chunks(m)
    for index,r in enumerate(rs):
        if r['source_id']==source_id:return {'selected':r,'context':[x for x in rs[max(0,index-2):index+3] if 'courseware_id' not in r or x.get('courseware_id')==r['courseware_id']],'material':{'id':m['id'],'name':m['name'],'type':m['type']}}
    raise HTTPException(404,'出处不存在')

@app.get('/api/materials/{id}/file')
def original(id:str):
    m=material_or_404(id)
    return FileResponse(m['path'],filename=m['name'],media_type='application/pdf' if m['type']=='pdf' else 'application/octet-stream',content_disposition_type='inline' if m['type']=='pdf' else 'attachment')

@app.post('/api/materials/{id}/confirm')
def confirm_parse(id:str):
    m=material_or_404(id)
    if m['parse_state']!='parsed':raise HTTPException(409,'请先完成解析')
    with transaction() as cur:cur.execute('UPDATE materials SET confirmed=true WHERE id=%s',(id,))
    return {'confirmed':True}

@app.post('/api/upload')
async def upload(file:UploadFile=File(...)):
    ext=Path(file.filename or '').suffix.lower()
    if ext not in ['.csv','.pdf','.docx']:raise HTTPException(422,'当前已实现 CSV、文字版PDF、DOCX；视频需选ASR，DOC转换尚未接入')
    temp=STORAGE/(uuid.uuid4().hex+'.upload');digest=hashlib.sha256();size=0
    try:
        with temp.open('wb') as out:
            while block:=await file.read(1024*1024):
                size+=len(block)
                if size>MAX_UPLOAD:raise HTTPException(413,'单文件上限500MB')
                digest.update(block);out.write(block)
        if not size:raise HTTPException(422,'文件为空')
        sha=digest.hexdigest();mid=uuid.uuid4().hex;target=STORAGE/(sha+ext)
        with transaction() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(sha,))
            cur.execute('SELECT id,name FROM materials WHERE sha256=%s',(sha,));exists=cur.fetchone()
            if exists:return {'duplicate':True,'material':exists}
            temp.replace(target)
            cur.execute('INSERT INTO materials(id,name,type,sha256,path,size) VALUES(%s,%s,%s,%s,%s,%s)',(mid,Path(file.filename).name,ext[1:],sha,str(target),size))
            cur.execute('INSERT INTO jobs(id,material_id,kind,config) VALUES(%s,%s,\'parse\',%s)',(uuid.uuid4().hex,mid,Json({})))
        return {'duplicate':False,'id':mid,'state':'uploaded'}
    finally:
        temp.unlink(missing_ok=True);await file.close()

@app.post('/api/materials/{id}/retry')
def retry_parse(id:str):
    with transaction() as cur:
        cur.execute('SELECT * FROM materials WHERE id=%s FOR UPDATE',(id,));m=cur.fetchone()
        if not m or m['parse_state']!='failed':raise HTTPException(409,'仅失败的解析可重试')
        cur.execute("SELECT id FROM jobs WHERE material_id=%s AND state IN ('queued','running')",(id,))
        if cur.fetchone():raise HTTPException(409,'已有排队任务')
        cur.execute("UPDATE materials SET parse_state='uploaded',error=NULL WHERE id=%s",(id,))
        cur.execute("INSERT INTO jobs(id,material_id,kind,config) VALUES(%s,%s,'parse','{}')",(uuid.uuid4().hex,id))
    return {'queued':True}

@app.get('/api/items')
def items(library:bool=False,kind:str='',status:str='',q:str='',material:str='',difficulty:str=''):
    query='SELECT i.*,b.material_id,m.name AS material_name FROM '+('approved_library' if library else 'items')+' i JOIN batches b ON b.id=i.batch_id JOIN materials m ON m.id=b.material_id WHERE i.status<>\'deleted\'';args=[]
    for field,value in [('i.kind',kind),('i.status',status),('b.material_id',material),("i.current->>'difficulty'",difficulty)]:
        if value:query+=' AND '+field+'=%s';args.append(value)
    if q:query+=" AND (i.current->>'prompt' ILIKE %s OR i.current->>'tags' ILIKE %s)";args.extend(['%'+q+'%']*2)
    return rows(query+' ORDER BY i.suspect DESC,i.created_at,i.id',args)

@app.get('/api/items/{id}/history')
def history(id:str):return rows('SELECT * FROM audit WHERE item_id=%s ORDER BY id DESC',(id,))

@app.post('/api/items/{id}/edit')
def edit(id:str,p:Edit):
    with transaction() as cur:
        cur.execute('SELECT * FROM items WHERE id=%s FOR UPDATE',(id,));item=cur.fetchone()
        if not item or item['status']=='deleted':raise HTTPException(404,'条目不存在')
        if item['version']!=p.version:raise HTTPException(409,'此内容已被更新，请刷新后重新编辑')
        validate_content(p.content,item['kind'])
        if item['current']==p.content:return {'changed':False,'version':item['version']}
        before={'content':item['current'],'status':item['status'],'version':item['version']}
        after={'content':p.content,'status':'pending_review','version':item['version']+1}
        cur.execute("UPDATE items SET current=%s,status='pending_review',suspect=true,check_note='人工修改后需重新核验答案与原文',version=version+1,updated_at=now() WHERE id=%s",(Json(p.content),id))
        cur.execute('INSERT INTO audit(item_id,action,actor,reason,before_data,after_data) VALUES(%s,\'edit\',\'本机审核人\',%s,%s,%s)',(id,p.reason,Json(before),Json(after)))
    return {'changed':True,'version':item['version']+1}

@app.post('/api/review')
def review(p:Review):
    states={'approve':'approved','reject':'rejected','restore':'pending_review','delete':'deleted'}
    if p.action not in states:raise HTTPException(422,'不支持的审核操作')
    if len({x.id for x in p.items})!=len(p.items):raise HTTPException(422,'条目重复')
    if p.action=='approve' and not p.evidence_confirmed:raise HTTPException(422,'请先确认已对照原文核验答案')
    if p.action=='reject' and p.reason not in ['答案错误','解析牵强','题目重复','表述不清','材料不足']:raise HTTPException(422,'请选择打回原因')
    if p.action=='delete' and not p.confirm_delete:raise HTTPException(422,'删除需二次确认；此操作只归档不清空')
    with transaction() as cur:
        for ref in sorted(p.items,key=lambda r:r.id):
            cur.execute('SELECT i.*,b.material_id FROM items i JOIN batches b ON b.id=i.batch_id WHERE i.id=%s FOR UPDATE OF i',(ref.id,));item=cur.fetchone()
            if not item:raise HTTPException(404,'条目不存在')
            if ref.version!=item['version']:raise HTTPException(409,'内容版本已变化，请刷新；本批操作全部取消')
            if item['status']=='deleted':raise HTTPException(409,'归档条目不能直接审核')
            if p.action=='approve':
                if item['status']!='pending_review':raise HTTPException(409,'只有待审核条目可通过')
                cur.execute('SELECT * FROM materials WHERE id=%s',(item['material_id'],));m=cur.fetchone()
                errors=evidence_errors(item,m)
                if errors:raise HTTPException(422,'；'.join(errors))
                validate_content(item['current'],item['kind'])
                if (item['suspect'] or item['evidence'].get('answer_origin')=='ai_inference') and (len(p.items)!=1 or len(p.reason.strip())<8):raise HTTPException(422,'AI推理、存疑或编辑后的条目须逐条复核，并填写至少8字依据说明')
            if p.action=='reject' and item['status']!='pending_review':raise HTTPException(409,'只有待审核条目可打回')
            before={'content':item['current'],'status':item['status'],'version':item['version']}
            after={**before,'status':states[p.action],'version':item['version']+1}
            cur.execute('UPDATE items SET status=%s,version=version+1,updated_at=now() WHERE id=%s',(states[p.action],item['id']))
            cur.execute('INSERT INTO audit(item_id,action,actor,reason,before_data,after_data) VALUES(%s,%s,\'本机审核人\',%s,%s,%s)',(item['id'],p.action,p.reason,Json(before),Json(after)))
    return {'updated':len(p.items)}

@app.get('/api/export')
def export(kind:str='card',format:str='csv'):
    data=items(library=True,kind=kind);headers=['ID','题型','题干/正面','答案/背面','选项','AI解释','难度','知识点','材料','出处原文','答案来源']
    table=[[i['id'],i['kind'],i['current']['prompt'],i['current']['answer'],json.dumps(i['current']['options'],ensure_ascii=False),i['current']['ai_explanation'],i['current']['difficulty'],'、'.join(i['current']['tags']),i['material_name'],json.dumps(i['evidence'],ensure_ascii=False)] for i in data]
    for row,item in zip(table,data):row.append('AI推理补全（已人工审核；引文仅定位题面/知识点）' if item['evidence'].get('answer_origin')=='ai_inference' else '材料依据答案（已人工审核）')
    if format=='xlsx':
        from openpyxl import Workbook
        wb=Workbook();ws=wb.active;ws.title='已审核内容'
        for r in [headers]+table:
            if any(len(str(v))>32767 for v in r):raise HTTPException(422,'单元格超过Excel限制，请使用CSV导出完整内容')
            ws.append(r)
            for cell in ws[ws.max_row]:cell.data_type='s'
        stream=io.BytesIO();wb.save(stream)
        return Response(stream.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="library.xlsx"'})
    if format!='csv':raise HTTPException(422,'导出格式无效')
    stream=io.StringIO(newline='');writer=csv.writer(stream)
    # Quoting preserves multiline text; prefix guards spreadsheet formula execution.
    writer.writerows([["'"+str(v) if str(v).lstrip().startswith(('=','+','-','@','\t','\r')) else str(v) for v in r] for r in [headers]+table])
    return Response('\ufeff'+stream.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="library.csv"'})

@app.get('/api/prompts')
def prompts():return rows('SELECT * FROM prompt_versions ORDER BY id DESC')
@app.post('/api/prompts')
def save_prompt(p:Prompt):
    with transaction() as cur:
        cur.execute('SELECT id FROM settings WHERE id=1 FOR UPDATE')
        cur.execute('SELECT id FROM prompt_versions ORDER BY id DESC LIMIT 1');latest=cur.fetchone()
        if latest['id']!=p.base_version:raise HTTPException(409,'提示词已有新版，请刷新')
        cur.execute('INSERT INTO prompt_versions(name,content,sha256) VALUES(\'材料生成\',%s,%s) RETURNING id',(p.content,hashlib.sha256(p.content.encode()).hexdigest()))
        return dict(cur.fetchone())
@app.get('/api/models')
def list_models():return profiles()

def save_profile(p,model_id=None):
    url=normalize_url(p.base_url)
    if not p.name.strip():raise HTTPException(422,'请填写模型名称')
    if p.provider not in [v['provider'] for v in PRESETS]:raise HTTPException(422,'供应商无效')
    key=p.api_key.get_secret_value().strip() if p.api_key else ''
    with transaction() as cur:
        # Serialize key-file initialization and profile edits with queue submission.
        cur.execute('SELECT id FROM settings WHERE id=1 FOR UPDATE')
        if model_id:
            cur.execute('SELECT * FROM model_profiles WHERE id=%s FOR UPDATE',(model_id,));old=cur.fetchone()
            if not old:raise HTTPException(404,'模型不存在')
            if old['version']!=p.version:raise HTTPException(409,'模型配置已有更新，请刷新后修改')
            if url!=old['base_url'] and (old['credential_id'] or old['env_key']) and not key:raise HTTPException(409,'更换接口地址时须重新填写该接口的Key，防止旧Key发往其他服务')
        else:
            model_id=uuid.uuid4().hex;old={'credential_id':None,'env_key':False}
            cur.execute('INSERT INTO model_profiles(id,name,provider,base_url,model) VALUES(%s,%s,%s,%s,%s)',(model_id,p.name.strip(),p.provider,url,p.model))
        cid=add_credential(cur,model_id,url,key) if key else old['credential_id']
        env_key=False if key or url!=old.get('base_url',url) else old['env_key']
        cur.execute("""UPDATE model_profiles SET name=%s,provider=%s,base_url=%s,model=%s,json_mode=%s,enabled=%s,
          input_price=%s,output_price=%s,currency=%s,credential_id=%s,env_key=%s,
          version=version+%s,updated_at=now() WHERE id=%s RETURNING *""",
          (p.name.strip(),p.provider,url,p.model,p.json_mode,p.enabled,p.input_price,p.output_price,p.currency,cid,env_key,1 if p.version is not None else 0,model_id))
        return public_profile(dict(cur.fetchone()))

@app.post('/api/models')
def create_model(p:ModelProfile):
    if p.version is not None:raise HTTPException(422,'新增模型不应指定版本')
    return save_profile(p)

@app.post('/api/models/{id}')
def update_model(id:str,p:ModelProfile):return save_profile(p,id)

@app.post('/api/settings')
def save_settings(p:Settings):
    with transaction() as cur:
        cur.execute('SELECT * FROM settings WHERE id=1 FOR UPDATE');old=cur.fetchone()
        if p.version!=old['version']:raise HTTPException(409,'配置已更新，请刷新')
        value={**old['value'],'daily_call_limit':p.daily_call_limit}
        # Retain old clients while the new page configures each profile separately.
        if p.model is not None:
            value.update(p.model_dump(exclude={'version'}));value['provider']='DeepSeek'
            cur.execute("UPDATE model_profiles SET model=%s,input_price=%s,output_price=%s,currency=%s,version=version+1 WHERE id='deepseek-default'",(p.model,p.input_price,p.output_price,p.currency))
        cur.execute('UPDATE settings SET value=%s,version=version+1 WHERE id=1',(Json(value),))
    return {'saved':True}

@app.post('/api/generate')
def enqueue(p:Generate):
    return enqueue_job(p)

@app.post('/api/pipelines')
def enqueue_pipeline(p:Generate):
    return enqueue_job(p,kind='pipeline')

def enqueue_job(p,kind='generate'):
    m=material_or_404(p.material_id)
    if p.answer_mode not in ['allow_inference','source_only']:raise HTTPException(422,'答案生成方式无效')
    if not m['confirmed'] or m['parse_state']!='parsed':raise HTTPException(409,'请先预览并确认解析结果')
    if p.question_type not in ['single_choice','multiple_choice','true_false'] or not 1<=p.cards+p.questions<=20:raise HTTPException(422,'每批1–20条，题型无效')
    if kind=='pipeline' and m['type']=='csv' and p.course not in (m['parsed'] or {}).get('groups',{}):raise HTTPException(422,'请先选择一个独立字幕课时')
    rs=chunks(m,p.course)
    if p.end<p.start or p.end>len(rs):raise HTTPException(422,'材料范围无效')
    if sum(len(r['text']) for r in rs[p.start-1:p.end])>30000:raise HTTPException(422,'所选文字超过3万字，请缩小范围；不静默截断材料')
    with transaction() as cur:
        cur.execute('SELECT * FROM settings WHERE id=1 FOR UPDATE');s=cur.fetchone()
        cur.execute('SELECT * FROM model_profiles WHERE id=%s',(p.model_id or 'deepseek-default',));profile=cur.fetchone()
        if not profile:raise HTTPException(404,'所选模型不存在')
        if not profile['enabled']:raise HTTPException(409,'所选模型已停用，请重新选择')
        if p.model_version is not None and profile['version']!=p.model_version:raise HTTPException(409,'所选模型配置已更新，请刷新后重新确认')
        if not has_key(profile):raise HTTPException(409,'所选模型未配置Key，请先在模型管理中添加')
        cur.execute("SELECT coalesce(sum(reserved_calls),0) AS n FROM jobs WHERE created_at >= date_trunc('day',now() AT TIME ZONE 'Asia/Shanghai') AT TIME ZONE 'Asia/Shanghai'");used=cur.fetchone()['n']
        reserve=4 if kind=='pipeline' else 2
        if used+reserve>s['value']['daily_call_limit']:raise HTTPException(429,f'今日调用上限不足：本次需预留{reserve}次调用，未创建任务，请调整上限后手动提交')
        cur.execute('SELECT * FROM prompt_versions ORDER BY id DESC LIMIT 1');prompt=cur.fetchone()
        cfg={**p.model_dump(),'quality_policy_version':1,'answer_policy_version':2,'exam_context':pending_exam_context(),'settings':{**s['value'],**{k:float(profile[k]) if k in ['input_price','output_price'] and profile[k] is not None else profile[k] for k in ['model','provider','input_price','output_price','currency']}},'model_profile':snapshot(profile),'settings_version':s['version'],'prompt':jsonable_encoder(dict(prompt))};jid=uuid.uuid4().hex
        if kind=='pipeline':
            cfg['source_sha']=m['sha256']
            cfg['pipeline_version']=1
            for stage in ['analysis','knowledge']:
                cur.execute('SELECT * FROM agent_prompt_versions WHERE stage=%s ORDER BY id DESC LIMIT 1',(stage,))
                cfg[stage+'_prompt']=jsonable_encoder(dict(cur.fetchone()))
        cur.execute('INSERT INTO jobs(id,material_id,kind,config,reserved_calls) VALUES(%s,%s,%s,%s,%s)',(jid,m['id'],kind,Json(cfg),reserve))
        if kind=='pipeline':pipeline.seed_steps(cur,jid)
    return {'id':jid,'state':'queued'}

@app.get('/api/pipelines/{id}')
def pipeline_detail(id:str):return pipeline.detail(id)

@app.post('/api/pipelines/{id}/retry')
def retry_pipeline(id:str):return pipeline.retry(id)

@app.get('/api/materials/{id}/history')
def material_history(id:str,offset:int=0,limit:int=20):
    material_or_404(id)
    return pipeline.history(id,offset,limit)

@app.get('/api/agent-prompts')
def agent_prompts():return rows('SELECT * FROM agent_prompt_versions ORDER BY id DESC')

@app.post('/api/agent-prompts')
def save_agent_prompt(p:AgentPrompt):
    if p.stage not in ['analysis','knowledge']:raise HTTPException(422,'Agent类型无效')
    with transaction() as cur:
        cur.execute('SELECT id FROM settings WHERE id=1 FOR UPDATE')
        cur.execute('SELECT id FROM agent_prompt_versions WHERE stage=%s ORDER BY id DESC LIMIT 1',(p.stage,));old=cur.fetchone()
        if not old or old['id']!=p.base_version:raise HTTPException(409,'Agent提示词已有新版，请刷新')
        cur.execute('INSERT INTO agent_prompt_versions(stage,content,sha256) VALUES(%s,%s,%s) RETURNING id',(p.stage,p.content,hashlib.sha256(p.content.encode()).hexdigest()))
        return dict(cur.fetchone())

@app.get('/api/jobs')
def jobs():return rows('SELECT j.*,m.name AS material_name FROM jobs j JOIN materials m ON m.id=j.material_id ORDER BY created_at DESC LIMIT 100')
@app.get('/api/usage')
def usage():
    return {'calls':rows('SELECT * FROM calls ORDER BY id DESC LIMIT 200'),'reject_reasons':rows("SELECT reason,count(*)::int FROM audit WHERE action='reject' GROUP BY reason"),'reviews':rows("SELECT action,count(*)::int FROM audit WHERE action IN ('approve','reject') GROUP BY action"),'note':'当前对话样本usage不可获取；API统计仅包含实际返回，估价使用配置的单价且不计缓存折扣。审核统计为操作次数。'}

from learner import build_router
app.include_router(build_router(CSRF))
