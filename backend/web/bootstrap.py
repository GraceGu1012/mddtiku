from pathlib import Path
import json, hashlib, shutil, os
from db import transaction, Json

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[1]
REPORT = ROOT / 'designs/knowledge-agent-intake'
STORAGE = Path(os.getenv('KNOWLEDGE_STORAGE_DIR', str(APP / 'runtime/materials')))

def storage_dir():
    return STORAGE

def initialize():
    STORAGE.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((REPORT/'data/manifest.json').read_text())
    batch = json.loads((REPORT/'data/current-model-batch.json').read_text())
    prompt = (APP/'web/generation_prompt.md').read_text()
    with transaction() as cur:
        cur.execute((APP/'web/schema.sql').read_text())
        cur.execute((APP/'web/exam_schema.sql').read_text())
        for stage in ['analysis','knowledge']:
            content=(APP/'web'/f'{stage}_prompt.md').read_text()
            cur.execute('SELECT id FROM agent_prompt_versions WHERE stage=%s LIMIT 1',(stage,))
            if not cur.fetchone():cur.execute('INSERT INTO agent_prompt_versions(stage,content,sha256) VALUES(%s,%s,%s)',(stage,content,hashlib.sha256(content.encode()).hexdigest()))
        cur.execute('INSERT INTO settings(id,value) VALUES(1,%s) ON CONFLICT DO NOTHING', (Json({'provider':'DeepSeek','model':'deepseek-flash','daily_call_limit':0,'input_price':None,'output_price':None,'currency':'CNY'}),))
        cur.execute("""INSERT INTO model_profiles(id,name,provider,base_url,model,env_key,input_price,output_price,currency)
            SELECT 'deepseek-default','DeepSeek 默认模型','DeepSeek','https://api.deepseek.com',
            value->>'model',true,(value->>'input_price')::numeric,(value->>'output_price')::numeric,coalesce(value->>'currency','CNY')
            FROM settings WHERE id=1 ON CONFLICT DO NOTHING""")
        cur.execute('SELECT id FROM prompt_versions LIMIT 1')
        if not cur.fetchone():
            cur.execute('INSERT INTO prompt_versions(name,content,sha256) VALUES(%s,%s,%s)', ('材料生成',prompt,hashlib.sha256(prompt.encode()).hexdigest()))
        for m in manifest['materials']:
            is_csv=m['type']=='csv'
            source=REPORT/'sources'/('transcript.csv' if is_csv else m['id']+'.pdf')
            target=STORAGE/(m['sha256']+source.suffix)
            if not target.exists(): shutil.copyfile(source,target)
            if hashlib.sha256(target.read_bytes()).hexdigest()!=m['sha256']: raise ValueError('原材料副本哈希不符')
            parsed=json.loads((REPORT/'data'/('transcript.json' if is_csv else 'pdf-'+m['id']+'.json')).read_text())
            cur.execute('INSERT INTO materials(id,name,type,sha256,path,size,parse_state,parsed,confirmed) VALUES(%s,%s,%s,%s,%s,%s,\'parsed\',%s,%s) ON CONFLICT DO NOTHING', (m['id'],m['filename'],m['type'],m['sha256'],str(target),m['size'],Json(parsed),is_csv))
        cur.execute('INSERT INTO batches(id,material_id,metadata) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING', (batch['id'],'transcript',Json({k:v for k,v in batch.items() if k!='items'})))
        for item in batch['items']:
            content={k:item[k] for k in ['prompt','answer','ai_explanation','difficulty','tags']}
            content['options']=item.get('options',[])
            content['answer_indices']=[item['answer_index']] if 'answer_index' in item else []
            evidence={k:item[k] for k in ['material_sha256','courseware_id','source_start','source_end','evidence','source_url']}
            cur.execute('INSERT INTO items(id,batch_id,kind,original,current,evidence,check_note) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', (item['id'],batch['id'],item['kind'],Json(content),Json(content),Json(evidence),item['semantic_self_check']))
    return {'materials':4,'sample_items':10}

if __name__=='__main__': print(initialize())
