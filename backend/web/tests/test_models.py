import copy, json, os, tempfile, unittest
from unittest.mock import patch
import test_app
from db import one, rows, transaction
from models import resolve_key, snapshot, cipher, normalize_url
import processing

class ModelTests(unittest.TestCase):
    setUp=test_app.AppTests.setUp
    post=test_app.AppTests.post

    def create(self,**overrides):
        data={'name':'测试模型','provider':'自定义兼容接口','base_url':'https://provider.example/v1','model':'model-test','api_key':'test-secret-not-real','json_mode':True}
        data.update(overrides)
        r=self.post('models',data)
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def edit(self,m,**changes):
        data={k:m[k] for k in ['version','name','provider','base_url','model','json_mode','enabled','input_price','output_price','currency']}
        data.update(changes)
        return self.post('models/'+m['id'],data)

    def enqueue(self,m):
        return self.post('generate',{'model_id':m['id'],'model_version':m['version'],'material_id':'transcript','course':'2112885753428808705','start':138,'end':139,'cards':1,'questions':0})

    def test_encrypt_and_no_secret_returned(self):
        key='test-multimodel-secret'
        m=self.create(api_key=key)
        encrypted=one('SELECT * FROM model_credentials')['ciphertext']
        self.assertNotIn(key,encrypted)
        self.assertEqual(resolve_key(one('SELECT * FROM model_profiles WHERE id=%s',(m['id'],))),key)
        for path in ['models','bootstrap','jobs','usage']:
            text=self.client.get('/api/'+path).text
            self.assertNotIn(key,text);self.assertNotIn(encrypted,text)
        self.assertNotIn('credential_id',m);self.assertTrue(m['key_configured'])

    def test_blank_retains_and_rotation_preserves_queued_credentials(self):
        m=self.create();old=one('SELECT * FROM model_profiles WHERE id=%s',(m['id'],))
        retained=self.edit(m,name='新名字',api_key='').json()
        now=one('SELECT * FROM model_profiles WHERE id=%s',(m['id'],))
        self.assertEqual(now['credential_id'],old['credential_id'])
        rotated=self.edit(retained,api_key='replacement-test-secret').json()
        newer=one('SELECT * FROM model_profiles WHERE id=%s',(m['id'],))
        self.assertNotEqual(newer['credential_id'],old['credential_id'])
        self.assertEqual(resolve_key(snapshot(old)),'test-secret-not-real')
        self.assertEqual(resolve_key(snapshot(newer)),'replacement-test-secret')
        self.assertEqual(self.edit(m,name='过期修改').status_code,409)

    def test_endpoint_change_requires_a_new_key(self):
        m=self.create()
        self.assertEqual(self.edit(m,base_url='https://other.example/v1').status_code,409)
        self.assertEqual(self.edit(m,base_url='https://other.example/v1',api_key='another-endpoint-key').status_code,200)

    def test_missing_disabled_and_stale_model_rejected(self):
        self.post('settings',{'version':1,'daily_call_limit':20})
        m=self.create(api_key='')
        self.assertEqual(self.enqueue(m).status_code,409)
        m=self.edit(m,api_key='now-present-secret',enabled=False).json()
        self.assertEqual(self.enqueue(m).status_code,409)
        m=self.edit(m,enabled=True).json();self.edit(m,name='下一版')
        self.assertEqual(self.enqueue(m).status_code,409)

    def test_model_selection_snapshot_budget_and_actual_dispatch(self):
        self.post('settings',{'version':1,'daily_call_limit':2})
        a=self.create(name='甲',model='chosen-model',base_url='https://a.example/v1',api_key='key-for-a-model')
        b=self.create(name='乙',model='other-model',base_url='https://b.example/v1',api_key='key-for-b-model')
        r=self.enqueue(a);self.assertEqual(r.status_code,200,r.text)
        job=one('SELECT * FROM jobs WHERE id=%s',(r.json()['id'],))
        self.assertEqual(job['config']['model_profile']['id'],a['id'])
        self.assertNotIn('key-for-a-model',json.dumps(job['config']))
        self.assertEqual(self.enqueue(b).status_code,429)
        self.edit(a,model='later-model',api_key='rotated-a-key')
        raw={'id':'response-id','model':'provider-real-version','usage':{'prompt_tokens':4,'completion_tokens':3,'total_tokens':7},'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]}
        fake=type('Fake',(),{'status_code':200,'json':lambda self:raw})()
        with patch('processing.normalize_url',side_effect=lambda value,resolve:value),patch('processing.httpx.post',return_value=fake) as call:
            self.assertTrue(processing.model_call(job,'generation',[])['ok'])
            args,kw=call.call_args
            self.assertEqual(args[0],'https://a.example/v1/chat/completions')
            self.assertEqual(kw['json']['model'],'chosen-model')
            self.assertEqual(kw['headers']['Authorization'],'Bearer key-for-a-model')
            self.assertFalse(kw['follow_redirects']);self.assertFalse(kw['trust_env'])
        saved=one('SELECT * FROM calls')
        self.assertEqual(saved['usage'],raw['usage']);self.assertEqual(saved['model_profile_id'],a['id'])
        self.assertEqual(saved['model_version'],1)

    def test_unsupported_json_mode_can_be_disabled(self):
        m=self.create(json_mode=False)
        self.post('settings',{'version':1,'daily_call_limit':2})
        jobid=self.enqueue(m).json()['id'];job=one('SELECT * FROM jobs WHERE id=%s',(jobid,))
        fake=type('Fake',(),{'status_code':401})()
        with patch('processing.normalize_url',side_effect=lambda value,resolve:value),patch('processing.httpx.post',return_value=fake) as call:
            with self.assertRaisesRegex(ValueError,'HTTP 401'):processing.model_call(job,'generation',[])
            self.assertNotIn('response_format',call.call_args.kwargs['json'])

    def test_key_never_echoed_on_validation_error(self):
        secret='do-not-echo-this-secret'
        r=self.post('models',{'name':'test','provider':'x','base_url':'bad','model':'x','api_key':{'bad':secret}})
        self.assertEqual(r.status_code,422);self.assertNotIn(secret,r.text)
        r=self.post('models',{'name':'test','provider':'DeepSeek','base_url':'https://u:'+secret+'@host.example','model':'x','api_key':secret})
        self.assertEqual(r.status_code,422);self.assertNotIn(secret,r.text)

    def test_endpoint_validation_and_lost_master(self):
        for url in ['http://example.org/v1','https://127.0.0.1/v1','https://localhost/v1','https://a.example/v1?key=secret','https://a.example/chat/completions']:
            with self.assertRaises(ValueError):normalize_url(url)
        with patch('models.socket.getaddrinfo',return_value=[(2,1,6,'',('10.0.0.1',443))]):
            with self.assertRaises(ValueError):normalize_url('https://provider.example',resolve=True)
        self.create()
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'KNOWLEDGE_MASTER_KEY_FILE':d+'/missing.key'}):
            with self.assertRaisesRegex(ValueError,'主密钥缺失'):cipher()
