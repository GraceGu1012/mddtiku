import hashlib,json
from pathlib import Path
from db import transaction,rows
from models import resolve_key
TABLES=['materials','items','batches','audit','prompt_versions','settings','model_profiles','model_credentials','jobs','calls','learners','practice_sessions','practice_attempts','card_progress']
def digest():
 result={}
 with transaction() as c:
  c.execute("SET LOCAL TIME ZONE 'UTC'")
  for t in TABLES:
   c.execute('SELECT to_jsonb(t) AS row FROM '+t+' t');values=[r['row'] for r in c.fetchall()]
   if t=='materials':
    for v in values:v['path']=Path(v['path']).name
   encoded=sorted(json.dumps(v,sort_keys=True,ensure_ascii=False) for v in values)
   result[t]={'count':len(values),'sha256':hashlib.sha256(json.dumps(encoded,ensure_ascii=False).encode()).hexdigest()}
 return result
if __name__=='__main__':
 import sys
 data=digest()
 if len(sys.argv)>1:
  assert data==json.loads(Path(sys.argv[1]).read_text()),'Database snapshot mismatch'
 for m in rows('SELECT path,sha256 FROM materials'):
  assert hashlib.sha256(Path(m['path']).read_bytes()).hexdigest()==m['sha256']
 for p in rows('SELECT * FROM model_profiles WHERE credential_id IS NOT NULL'):
  assert resolve_key(p)
 print(json.dumps({'tables':data,'files_verified':True,'credentials_decryptable':True},ensure_ascii=False))
