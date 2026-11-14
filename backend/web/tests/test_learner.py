import unittest
import test_app as base
from test_app import app, TestClient, one, rows, transaction, Json

class LearnerTests(unittest.TestCase):
    setUp=base.AppTests.setUp
    post=base.AppTests.post
    review=base.AppTests.review
    def start(self,**options):
        self.client.get('/api/learn/bootstrap')
        return self.post('learn/sessions',options)
    def answer(self,sid,item='Q01',selected=None,version=None):
        q=one('SELECT * FROM items WHERE id=%s',(item,))
        return self.post('learn/sessions/'+sid+'/answer',{'item_id':item,'version':version or q['version'],
            'selected':q['current']['answer_indices'] if selected is None else selected})
    def test_only_published_and_no_answer_leak(self):
        self.client.get('/api/learn/bootstrap')
        self.assertEqual(self.client.get('/api/learn/catalog').json(),[])
        self.assertEqual(self.start().status_code,422)
        self.review(['Q01','C01'])
        data=self.client.get('/api/learn/catalog').json()
        self.assertEqual({x['id'] for x in data},{'Q01','C01'})
        self.assertFalse(any('answer' in x or 'evidence' in x or 'answer_indices' in x for x in data))
        s=self.start(count=10).json();self.assertEqual(s['total'],1)
        content=self.client.get('/api/learn/sessions/'+s['id']).json()['questions'][0]
        self.assertNotIn('result',content);self.assertNotIn('answer_indices',content)
        self.assertEqual(self.client.get('/api/learn/cards/C02').status_code,404)
    def test_grade_idempotency_and_wrong_retry(self):
        self.review(['Q01']);s=self.start().json()
        r=self.answer(s['id'],selected=[0]);self.assertEqual(r.status_code,200);self.assertFalse(r.json()['correct'])
        self.assertEqual(self.answer(s['id'],selected=[0]).json(),r.json())
        self.assertEqual(one('SELECT count(*) AS n FROM practice_attempts')['n'],1)
        self.assertEqual(self.answer(s['id']).status_code,409)
        self.assertFalse(self.client.get('/api/learn/catalog').json()[0]['last_correct'])
        retry=self.start(mode='wrong').json();self.assertTrue(self.answer(retry['id']).json()['correct'])
        self.assertTrue(self.client.get('/api/learn/catalog').json()[0]['last_correct'])
        self.assertEqual(self.start(mode='wrong').status_code,422)
        self.assertEqual(self.client.get('/api/learn/progress').json()['stats']['attempts'],2)
    def test_browser_profiles_isolated(self):
        self.review(['Q01']);s=self.start().json();self.answer(s['id'])
        cookie=self.client.cookies.get('mdd_learner');self.assertIsNotNone(cookie)
        other=TestClient(app.app,base_url='http://127.0.0.1:4312')
        self.assertEqual(other.get('/api/learn/catalog').status_code,401)
        resp=other.get('/api/learn/bootstrap');self.assertIn('HttpOnly',resp.headers['set-cookie'])
        self.assertEqual(other.get('/api/learn/progress').json()['stats']['attempts'],0)
        self.assertEqual(other.get('/api/learn/sessions/'+s['id']).status_code,404)
        self.assertEqual(other.post('/api/learn/sessions/'+s['id']+'/answer',headers=self.headers,
            json={'item_id':'Q01','version':2,'selected':[1]}).status_code,404)
        restored=TestClient(app.app,base_url='http://127.0.0.1:4312');restored.cookies.set('mdd_learner',cookie)
        self.assertEqual(restored.get('/api/learn/progress').json()['stats']['attempts'],1)
    def test_withdrawal_edit_and_session_membership(self):
        self.review(['Q01','Q02']);s=self.start(count=1).json()
        self.assertEqual(self.answer(s['id'],item='Q02').status_code,409)
        self.assertEqual(self.review(['Q01'],action='restore').status_code,200)
        self.assertEqual(self.answer(s['id']).status_code,409) # version changed before membership check
        self.assertEqual(self.answer(s['id'],version=2).status_code,404)
        self.assertTrue(self.client.get('/api/learn/sessions/'+s['id']).json()['questions'][0]['unavailable'])
        self.assertEqual(one('SELECT count(*) AS n FROM practice_attempts')['n'],0)
        self.review(['Q01'])
        self.assertEqual(self.answer(s['id'],version=2).status_code,409)
    def test_multiple_and_true_false_grading(self):
        self.review(['Q01','Q02'])
        with transaction() as cur:
            q=one("SELECT current FROM items WHERE id='Q01'")['current'];q.update(kind='multiple_choice',answer_indices=[1,3],answer='B. 乙；D. 丁')
            cur.execute("UPDATE items SET kind='multiple_choice',current=%s WHERE id='Q01'",(Json(q),))
            q=one("SELECT current FROM items WHERE id='Q02'")['current'];q.update(kind='true_false',options=['正确','错误'],answer_indices=[0],answer='A. 正确')
            cur.execute("UPDATE items SET kind='true_false',current=%s WHERE id='Q02'",(Json(q),))
        s=self.start(kind='multiple_choice').json()
        self.assertEqual(self.answer(s['id'],selected=[1,1]).status_code,422)
        self.assertEqual(self.answer(s['id'],selected=[9]).status_code,422)
        self.assertTrue(self.answer(s['id'],selected=[3,1]).json()['correct'])
        s=self.start(kind='multiple_choice').json();self.assertFalse(self.answer(s['id'],selected=[1]).json()['correct'])
        s=self.start(kind='true_false').json();self.assertEqual(s['total'],1)
        self.assertEqual(self.answer(s['id'],item='Q02',selected=[0,1]).status_code,422)
        self.assertTrue(self.answer(s['id'],item='Q02',selected=[0]).json()['correct'])
    def test_card_rating_and_source_permissions(self):
        self.review(['C01']);self.client.get('/api/learn/bootstrap')
        card=self.client.get('/api/learn/cards/C01').json();self.assertTrue(card['answer'])
        self.assertEqual(self.post('learn/cards/C01/rating',{'version':card['version'],'rating':'remembered'}).status_code,200)
        self.assertEqual(self.client.get('/api/learn/catalog').json()[0]['rating'],'remembered')
        self.assertEqual(self.client.get('/api/learn/progress').json()['stats']['attempts'],0)
        sid=card['evidence'][0]['source_id'];source=self.client.get('/api/learn/items/C01/source/'+sid).json()
        self.assertIn(card['evidence'][0]['quote'],source['selected']['text'])
        self.assertEqual(self.client.get('/api/learn/items/C01/source/csv-record-1').status_code,404)
        self.assertEqual(self.review(['C01'],action='restore').status_code,200)
        self.assertEqual(self.client.get('/api/learn/items/C01/source/'+sid).status_code,404)
        self.assertEqual(self.post('learn/cards/C01/rating',{'version':card['version'],'rating':'again'}).status_code,404)
    def test_filtered_empty_and_csrf(self):
        self.review(['Q01']);self.client.get('/api/learn/bootstrap')
        self.assertEqual(self.start(tag='不存在').status_code,422)
        self.assertEqual(self.start(material_id='unknown').status_code,422)
        self.assertEqual(self.client.post('/api/learn/sessions',json={}).status_code,403)
        self.assertEqual(self.start(count=0).status_code,422)
