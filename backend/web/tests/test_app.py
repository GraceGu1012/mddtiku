import os, sys, copy, json, unittest, io, csv
from pathlib import Path
from unittest.mock import patch
os.environ['KNOWLEDGE_DATABASE_URL']='dbname=knowledge_agent_test host=/tmp'
os.environ['KNOWLEDGE_WORKER']='0'
os.environ['KNOWLEDGE_MASTER_KEY_FILE']=str(Path(__file__).resolve().parents[2]/'runtime/test-master.key')
os.environ['KNOWLEDGE_STORAGE_DIR']=str(Path(__file__).resolve().parents[2]/'runtime/test_materials')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from db import transaction, one, rows, Json
from bootstrap import initialize, REPORT
import app
import processing

class AppTests(unittest.TestCase):
    def setUp(self):
        initialize()
        with transaction() as cur:
            cur.execute('SELECT current_database() AS db')
            assert cur.fetchone()['db']=='knowledge_agent_test'
            cur.execute('TRUNCATE learners,model_credentials,model_profiles,audit,items,calls,jobs,batches,materials,prompt_versions,settings RESTART IDENTITY CASCADE')
        initialize()
        self.client=TestClient(app.app,base_url='http://127.0.0.1:4312')
        self.headers={'X-CSRF-Token':app.CSRF}
    def post(self,path,value):return self.client.post('/api/'+path,json=value,headers=self.headers)
    def review(self,ids=['C01'],action='approve',**kw):
        refs=[{'id':i,'version':one('SELECT version FROM items WHERE id=%s',(i,))['version']} for i in ids]
        return self.post('review',dict(items=refs,action=action,evidence_confirmed=True,**kw))
    def test_review_gate_and_formal_library(self):
        self.assertEqual(self.client.get('/api/items?library=true').json(),[])
        self.assertEqual(self.post('review',{'items':[{'id':'C01','version':1}],'action':'approve'}).status_code,422)
        self.assertEqual(self.review().status_code,200)
        self.assertEqual([r['id'] for r in self.client.get('/api/items?library=true').json()],['C01'])
        self.assertEqual(one('SELECT count(*) AS n FROM audit')['n'],1)
    def test_edit_revokes_approval_and_retains_original(self):
        self.review();item=one("SELECT * FROM items WHERE id='C01'");content=copy.deepcopy(item['current']);content['prompt']+='（修订）'
        result=self.post('items/C01/edit',{'version':2,'content':content,'reason':'澄清提问'})
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.client.get('/api/items?library=true').json(),[])
        new=one("SELECT * FROM items WHERE id='C01'")
        self.assertEqual(new['original'],item['original']);self.assertTrue(new['suspect'])
        self.assertEqual(self.review().status_code,422)
        self.assertEqual(self.review(reason='已逐字复核原文中的答案和限定条件').status_code,200)
    def test_stale_edit_and_atomic_batch_conflict(self):
        response=self.post('review',{'items':[{'id':'C01','version':1},{'id':'Q01','version':9}],'action':'approve','evidence_confirmed':True})
        self.assertEqual(response.status_code,409)
        self.assertEqual(one("SELECT status FROM items WHERE id='C01'")['status'],'pending_review')
        self.assertEqual(one('SELECT count(*) AS n FROM audit')['n'],0)
        item=one("SELECT * FROM items WHERE id='C01'")
        self.assertEqual(self.post('items/C01/edit',{'version':99,'content':item['current'],'reason':'test'}).status_code,409)
    def test_suspect_cannot_bulk_pass(self):
        with transaction() as cur:cur.execute("UPDATE items SET suspect=true WHERE id='C02'")
        self.assertEqual(self.review(['C01','C02'],reason='已逐条核对全部原文依据').status_code,422)
        self.assertEqual(self.client.get('/api/items?library=true').json(),[])
    def test_false_provenance_prevents_approval(self):
        item=one("SELECT evidence FROM items WHERE id='C01'");item['evidence']['evidence'][0]['quote']='这不是原文'
        with transaction() as cur:cur.execute("UPDATE items SET evidence=%s WHERE id='C01'",(Json(item['evidence']),))
        self.assertEqual(self.review().status_code,422)
    def test_reject_restore_and_delete_confirmation(self):
        self.assertEqual(self.review(action='reject',reason='答案错误').status_code,200)
        self.assertEqual(self.review().status_code,409)
        self.assertEqual(self.review(action='restore').status_code,200)
        self.assertEqual(self.review(action='delete').status_code,422)
        self.assertEqual(self.review(action='delete',confirm_delete=True).status_code,200)
        self.assertEqual(one("SELECT status FROM items WHERE id='C01'")['status'],'deleted')
        self.assertEqual(len(self.client.get('/api/items/C01/history').json()),3)
    def test_source_locator_and_csv_export(self):
        source=self.client.get('/api/materials/transcript/source/csv-record-1792').json()
        self.assertEqual(source['selected']['courseware_id'],'2112885753428808705');self.assertEqual(source['selected']['num'],'138')
        item=one("SELECT * FROM items WHERE id='C01'");content=item['current'];content['answer']='=test,中文\n第二行'
        self.post('items/C01/edit',{'version':1,'content':content,'reason':'导出边界测试'})
        self.review(reason='测试隔离数据库中的导出转义，不是实际内容审核')
        result=self.client.get('/api/export?kind=card').content.decode('utf-8-sig')
        data=list(csv.reader(io.StringIO(result,newline='')))
        self.assertEqual(len(data),2);self.assertEqual(data[1][3],"'=test,中文\n第二行")
        from openpyxl import load_workbook
        ws=load_workbook(io.BytesIO(self.client.get('/api/export?kind=card&format=xlsx').content)).active
        self.assertEqual(ws['D2'].value,'=test,中文\n第二行');self.assertEqual(ws['D2'].data_type,'s')
    def test_csrf_origin_and_read_only_sources(self):
        self.assertEqual(self.client.post('/api/review',json={}).status_code,403)
        self.assertEqual(self.client.post('/api/review',json={},headers={**self.headers,'Origin':'https://example.org'}).status_code,403)
        self.assertEqual(self.client.get('/api/bootstrap',headers={'Host':'evil.example'}).status_code,400)
        self.assertEqual(self.client.get('/api/materials/2016/source/nope').status_code,404)
    def test_upload_duplicate_and_unsupported(self):
        data=(REPORT/'sources/transcript.csv').read_bytes()
        r=self.client.post('/api/upload',files={'file':('same.csv',data)},headers=self.headers)
        self.assertTrue(r.json()['duplicate']);self.assertEqual(len(self.client.get('/api/materials').json()),4)
        self.assertEqual(self.client.post('/api/upload',files={'file':('video.mp4',b'foo')},headers=self.headers).status_code,422)
    def test_prompt_settings_snapshot_and_daily_limit(self):
        self.assertEqual(self.post('generate',{'material_id':'transcript','start':138,'end':139,'cards':1,'questions':0}).status_code,409)
        self.post('settings',{'version':1,'model':'deepseek-flash','daily_call_limit':2})
        old=one('SELECT * FROM prompt_versions ORDER BY id DESC LIMIT 1')
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'fake-test-no-network'}):
            r=self.post('generate',{'material_id':'transcript','course':'2112885753428808705','start':138,'end':139,'cards':1,'questions':0})
            self.assertEqual(r.status_code,200)
            self.assertEqual(self.post('generate',{'material_id':'transcript','start':1,'end':2,'cards':1,'questions':0}).status_code,429)
        self.assertEqual(self.post('prompts',{'base_version':old['id'],'content':old['content']+'\n增加新的核验条件。'}).status_code,200)
        self.assertEqual(self.post('prompts',{'base_version':old['id'],'content':old['content']}).status_code,409)
        job=one('SELECT * FROM jobs')
        self.assertEqual(job['config']['prompt']['content'],old['content'])
        self.assertEqual(job['config']['settings']['model'],'deepseek-flash')
    def test_usage_preserved_even_invalid_generated_json(self):
        cfg={'settings':{'model':'test','input_price':2,'output_price':3,'currency':'CNY'}}
        with transaction() as cur:cur.execute("INSERT INTO jobs(id,material_id,kind,config) VALUES('mock','transcript','generate',%s)",(Json(cfg),))
        raw={'id':'resp-test','model':'returned-model','usage':{'prompt_tokens':11,'completion_tokens':7,'total_tokens':18,'prompt_cache_hit_tokens':3},'choices':[{'finish_reason':'stop','message':{'content':'bad json'}}]}
        fake=type('Fake',(),{'status_code':200,'json':lambda self:raw})()
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'mock'}),patch('processing.normalize_url',return_value='https://api.deepseek.com'),patch('processing.httpx.post',return_value=fake):
            with self.assertRaises(ValueError):processing.model_call({'id':'mock','config':cfg},'generation',[])
        record=one('SELECT * FROM calls')
        self.assertEqual(record['usage'],raw['usage']);self.assertEqual(record['model'],'returned-model');self.assertAlmostEqual(float(record['cost']),.000043)
    def test_generation_untrusted_evidence_rejected(self):
        source=one("SELECT * FROM materials WHERE id='transcript'")
        cfg={'course':'2112885753428808705','start':138,'end':139,'cards':1,'questions':0,'question_type':'single_choice','prompt':{'content':'test'},'settings':{}}
        item=one("SELECT * FROM items WHERE id='C01'")
        output={**item['current'],'kind':'card','evidence':[{'source_id':'csv-record-1792','quote':'模型编造引文'}]}
        with patch('processing.model_call',return_value={'items':[output]}):
            with self.assertRaises(ValueError):processing.generate({'id':'bad','config':cfg},source)
        self.assertIsNone(one("SELECT * FROM batches WHERE id='bad'"))
    def test_seed_is_idempotent_preserves_review(self):
        self.review();initialize()
        self.assertEqual(one("SELECT status FROM items WHERE id='C01'")['status'],'approved')
        self.assertEqual(one('SELECT count(*) AS n FROM items')['n'],10)

if __name__=='__main__':unittest.main()
