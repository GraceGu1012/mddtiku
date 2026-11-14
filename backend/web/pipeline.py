"""Three specialized agents with durable outputs, explicit retries and source-bound handoffs."""
import hashlib,json,re,uuid
from pathlib import Path
from fastapi import HTTPException
from db import one,rows,transaction,Json
import processing

STAGES=('analysis','knowledge','generation')
COSTS={'analysis':1,'knowledge':1,'generation':2}

def source_intact(material,expected):
    path=Path(material['path'])
    if material['sha256']!=expected or not path.is_file():return False
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()==expected

def seed_steps(cur,jid):
    for name in STAGES:cur.execute('INSERT INTO agent_steps(job_id,name) VALUES(%s,%s)',(jid,name))

def ordered_steps(jid):
    found={s['name']:s for s in rows('SELECT * FROM agent_steps WHERE job_id=%s',(jid,))}
    return [found[n] for n in STAGES if n in found]

def check_text(value,label,limit):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:raise ValueError(label+'格式不正确或过长')
    return value

def analyze(job,sources):
    value=processing.model_call(job,'analysis',[{'role':'system','content':job['config']['analysis_prompt']['content']},
        {'role':'user','content':json.dumps({'sources':sources},ensure_ascii=False)}])
    if not isinstance(value,dict):raise ValueError('解析分析结果不是JSON对象')
    check_text(value.get('summary'),'分析摘要',3000);check_text(value.get('document_type'),'内容类型',200)
    limits=value.get('limitations',[])
    if not isinstance(limits,list) or len(limits)>20 or any(not isinstance(x,str) or not x.strip() or len(x)>1000 for x in limits):raise ValueError('解析限制格式不正确')
    return {'summary':value['summary'],'document_type':value['document_type'],'limitations':limits,'sources':sources}

def extract(job,analysis):
    cfg=job['config'];limit=min(10,cfg['cards']+cfg['questions'])
    value=processing.model_call(job,'knowledge',[{'role':'system','content':cfg['knowledge_prompt']['content']},
        {'role':'user','content':json.dumps({'sources':analysis['sources'],'analysis':{k:v for k,v in analysis.items() if k!='sources'},'point_count':limit},ensure_ascii=False)}])
    if not isinstance(value,dict):raise ValueError('知识点结果不是JSON对象')
    points=value.get('points');lookup={s['source_id']:s for s in analysis['sources']};ids=set();clean=[]
    if not isinstance(points,list) or len(points)>limit:raise ValueError('知识点数量或结构不符合要求')
    for p in points:
        if not isinstance(p,dict):raise ValueError('知识点格式无效')
        pid=p.get('id')
        if not isinstance(pid,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}',pid) or pid in ids:raise ValueError('知识点ID无效或重复')
        ids.add(pid);check_text(p.get('title'),'知识点名称',150);check_text(p.get('summary'),'知识点概述',1000)
        ev=p.get('evidence')
        if not isinstance(ev,list) or not 1<=len(ev)<=20:raise ValueError('知识点缺少原文引文或引文过多')
        quotes=[]
        for e in ev:
            if not isinstance(e,dict):raise ValueError('知识点引文格式无效')
            s=lookup.get(e.get('source_id'));quote=e.get('quote')
            if not s or not isinstance(quote,str) or len(quote.strip())<4 or quote not in s['text']:raise ValueError('知识点引文无法逐字匹配原文')
            quotes.append({'source_id':s['source_id'],'quote':quote,'label':s.get('label','')})
        clean.append({'id':pid,'title':p['title'],'summary':p['summary'],'evidence':quotes})
    reason=value.get('insufficient_reason','')
    if not isinstance(reason,str) or len(reason)>3000:raise ValueError('知识点不足原因格式无效')
    return {'points':clean,'insufficient_reason':reason or ('所选范围未提取到可用的专业知识点' if not clean else '')}

def run_pipeline(job,material):
    cfg=job['config']
    if not source_intact(material,cfg['source_sha']):
        raise ValueError('材料原件缺失或指纹变化，不能继续旧流程，请重新核对材料')
    sources=processing.chunks(material,cfg.get('course',''))[cfg['start']-1:cfg['end']]
    steps={s['name']:s for s in ordered_steps(job['id'])};results={}
    for name in STAGES:
        step=steps[name]
        if step['state'] in ['completed','skipped']:
            results[name]=step['result'];continue
        if name=='generation' and not results['knowledge']['points']:
            result={'generated':0,'pending_review':0,'insufficient_reason':results['knowledge']['insufficient_reason']}
            with transaction() as cur:cur.execute("UPDATE agent_steps SET state='skipped',result=%s,finished_at=now() WHERE job_id=%s AND name=%s",(Json(result),job['id'],name))
            results[name]=result;continue
        with transaction() as cur:cur.execute("UPDATE agent_steps SET state='running',started_at=now(),error=NULL WHERE job_id=%s AND name=%s",(job['id'],name))
        try:
            if name=='analysis':result=analyze(job,sources)
            elif name=='knowledge':result=extract(job,results['analysis'])
            else:
                child={**job,'config':{**cfg,'knowledge_points':results['knowledge']['points']}}
                result=processing.generate(child,material)
            with transaction() as cur:cur.execute("UPDATE agent_steps SET state='completed',result=%s,finished_at=now() WHERE job_id=%s AND name=%s",(Json(result),job['id'],name))
            results[name]=result
        except Exception as error:
            message=str(error) if isinstance(error,ValueError) else '该阶段执行失败（'+type(error).__name__+'），请检查配置与日志'
            with transaction() as cur:cur.execute("UPDATE agent_steps SET state='failed',error=%s,finished_at=now() WHERE job_id=%s AND name=%s",(message,job['id'],name))
            raise
    return {**results['generation'],'knowledge_points':len(results['knowledge']['points'])}

def detail(jid):
    job=one("SELECT * FROM jobs WHERE id=%s AND kind='pipeline'",(jid,))
    if not job:raise HTTPException(404,'流程不存在')
    job['steps']=ordered_steps(jid)
    job['items']=rows('SELECT id,kind,status,current,evidence FROM items WHERE batch_id=%s ORDER BY created_at,id',(jid,))
    job['calls']=rows('SELECT purpose,model,usage,cost,currency,created_at FROM calls WHERE job_id=%s ORDER BY id',(jid,))
    job['queue_position']=one("SELECT count(*) AS n FROM jobs WHERE state='queued' AND (created_at,id)<= (%s,%s)",(job['created_at'],jid))['n'] if job['state']=='queued' else None
    return job

def history(mid,offset,limit):
    if offset<0 or not 1<=limit<=50:raise HTTPException(422,'历史分页范围无效')
    data=rows('SELECT * FROM jobs WHERE material_id=%s ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s',(mid,limit,offset))
    for j in data:j['steps']=ordered_steps(j['id'])
    return {'total':one('SELECT count(*) AS n FROM jobs WHERE material_id=%s',(mid,))['n'],'offset':offset,'limit':limit,'jobs':data}

def retry(jid):
    with transaction() as cur:
        # Same lock order as new submission: budget first, then prior job.
        cur.execute('SELECT * FROM settings WHERE id=1 FOR UPDATE');settings=cur.fetchone()
        cur.execute("SELECT * FROM jobs WHERE id=%s AND kind='pipeline' FOR UPDATE",(jid,));old=cur.fetchone()
        if not old or old['state']!='failed':raise HTTPException(409,'只有失败的流程可以重试')
        cur.execute("SELECT id,state FROM jobs WHERE config->>'retry_of'=%s AND state!='failed' ORDER BY created_at LIMIT 1",(jid,));existing=cur.fetchone()
        if existing:return dict(existing)
        cur.execute('SELECT id FROM batches WHERE id=%s',(jid,))
        if cur.fetchone():raise HTTPException(409,'该流程已保存生成结果，请先在审核台核对，避免重复计费生成')
        cur.execute('SELECT * FROM materials WHERE id=%s',(old['material_id'],));m=cur.fetchone()
        if m['parse_state']!='parsed' or not m['confirmed'] or not source_intact(m,old['config']['source_sha']):raise HTTPException(409,'原材料或解析状态变化，请重新核对后启动新流程')
        cur.execute('SELECT * FROM agent_steps WHERE job_id=%s',(jid,));steps={s['name']:s for s in cur.fetchall()}
        kept={n:s for n,s in steps.items() if s['state']=='completed' and n in ['analysis','knowledge']}
        cost=sum(COSTS[n] for n in STAGES if n not in kept)
        cur.execute("SELECT coalesce(sum(reserved_calls),0) AS n FROM jobs WHERE created_at >= date_trunc('day',now() AT TIME ZONE 'Asia/Shanghai') AT TIME ZONE 'Asia/Shanghai'")
        if cur.fetchone()['n']+cost>settings['value']['daily_call_limit']:raise HTTPException(429,'今日调用额度不足，未创建重试任务')
        new=uuid.uuid4().hex;cfg={**old['config'],'retry_of':jid}
        cur.execute("INSERT INTO jobs(id,material_id,kind,config,reserved_calls) VALUES(%s,%s,'pipeline',%s,%s)",(new,old['material_id'],Json(cfg),cost))
        seed_steps(cur,new)
        for n,s in kept.items():cur.execute("UPDATE agent_steps SET state='completed',result=%s,started_at=%s,finished_at=%s WHERE job_id=%s AND name=%s",(Json(s['result']),s['started_at'],s['finished_at'],new,n))
    return {'id':new,'state':'queued'}
