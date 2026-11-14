import os, unittest
from unittest.mock import patch
import test_app as base
from test_app import app, TestClient, one, rows, transaction, Json

class GamificationTests(unittest.TestCase):
    setUp=base.AppTests.setUp
    post=base.AppTests.post
    review=base.AppTests.review
    def start(self,**options):
        self.client.get('/api/learn/bootstrap')
        return self.post('learn/sessions',options)
    def answer(self,sid,item,selected=None):
        q=one('SELECT * FROM items WHERE id=%s',(item,))
        if selected is None:selected=q['current']['answer_indices']
        return self.post('learn/sessions/'+sid+'/answer',
            {'item_id':item,'version':q['version'],'selected':selected})
    def rate(self,item,rating='remembered'):
        card=self.client.get('/api/learn/cards/'+item).json()
        return self.post('learn/cards/'+item+'/rating',{'version':card['version'],'rating':rating})

    def test_xp_rules_and_dashboard(self):
        self.review(['Q01','Q02','Q03','C01'])
        s=self.start(count=3).json()
        self.assertEqual(self.answer(s['id'],'Q01').json()['xp'],10)
        self.assertEqual(self.answer(s['id'],'Q02').json()['xp'],10)
        self.assertEqual(self.answer(s['id'],'Q03').json()['xp'],15) # 10 + 5 streak bonus
        data=self.client.get('/api/learn/dashboard').json()
        g=data['gamification']
        self.assertEqual(g['xp'],35);self.assertEqual(g['today_xp'],35)
        self.assertEqual(g['streak_days'],1);self.assertEqual(g['level'],1)
        self.assertEqual(data['mastery']['total'],1) # C01 approved but not rated yet
        self.assertEqual(data['mastery']['mastered'],0)
        self.assertEqual(self.rate('C01').json()['xp'],15)
        self.assertEqual(self.rate('C01').json()['xp'],0) # already remembered
        data=self.client.get('/api/learn/dashboard').json()
        self.assertEqual(data['mastery']['mastered'],1)
        self.assertEqual(data['mastery']['percent'],100)
        self.assertEqual(data['gamification']['xp'],50)
        # wrong answer grants nothing; replaying a graded question grants nothing
        s=self.start(count=1).json()
        self.assertEqual(self.answer(s['id'],'Q01',selected=[0] if one("SELECT current FROM items WHERE id='Q01'")['current']['answer_indices']!=[0] else [1]).json()['xp'],0)

    def test_structure_and_leaderboard(self):
        self.review(['Q01','Q02','C01','C02'])
        self.client.get('/api/learn/bootstrap')
        data=self.client.get('/api/learn/structure').json()
        self.assertTrue(any(m['total']==4 for m in data))
        units=[u for m in data for u in m['units']]
        self.assertTrue(all(u['total']==u['cards']+u['questions'] for u in units))
        self.assertTrue(self.answer(self.start(count=1).json()['id'],'Q01').json()['correct'])
        board=self.client.get('/api/learn/leaderboard?period=week').json()
        self.assertEqual(board['me']['xp'],10);self.assertEqual(board['me']['rank'],1)
        self.assertTrue(board['entries']);self.assertTrue(board['entries'][0]['nickname'])
        self.assertTrue(any(e['is_me'] for e in board['entries']))
        month=self.client.get('/api/learn/leaderboard?period=month').json()
        self.assertEqual(month['me']['xp'],10)
        self.assertEqual(self.client.get('/api/learn/leaderboard?period=bad').status_code,200)

    def test_openid_binding_shares_progress(self):
        self.review(['Q01'])
        headers={'x-wx-openid':'oX-1','X-CSRF-Token':app.CSRF}
        first=TestClient(app.app,base_url='http://127.0.0.1:4312')
        first.get('/api/learn/bootstrap',headers=headers)
        s=first.post('/api/learn/sessions',json={'count':1},headers=headers).json()
        first.post('/api/learn/sessions/'+s['id']+'/answer',json={'item_id':'Q01',
            'version':one("SELECT version FROM items WHERE id='Q01'")['version'],
            'selected':one("SELECT current FROM items WHERE id='Q01'")['current']['answer_indices']},headers=headers)
        second=TestClient(app.app,base_url='http://127.0.0.1:4312')
        second.get('/api/learn/bootstrap',headers=headers) # new cookie, same openid
        self.assertEqual(second.get('/api/learn/progress',headers=headers).json()['stats']['attempts'],1)
        board=second.get('/api/learn/leaderboard',headers=headers).json()
        self.assertEqual(board['me']['xp'],10)

    def test_ask_retrieval_and_limit(self):
        self.review(['C01','Q01'])
        self.client.get('/api/learn/bootstrap')
        r=self.post('learn/ask',{'question':'完全不相关的随机词组QQXX'})
        self.assertEqual(r.status_code,200);self.assertFalse(r.json()['grounded'])
        raw={'id':'x','model':'m','usage':{},'choices':[{'finish_reason':'stop','message':{'content':'依据资料，答案是……'}}]}
        fake=type('Fake',(),{'status_code':200,'json':lambda self:raw})()
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'mock'}),patch('learner.httpx.post',return_value=fake):
            prompt=one("SELECT current->>'prompt' AS p FROM items WHERE id='C01'")['p']
            r=self.post('learn/ask',{'question':prompt[:80]})
            self.assertEqual(r.status_code,200);self.assertTrue(r.json()['grounded'])
            self.assertEqual(one("SELECT purpose FROM calls WHERE purpose='learner_ask'")['purpose'],'learner_ask')
            # rate limit
            for _ in range(19):self.post('learn/ask',{'question':prompt[:80]})
            self.assertEqual(self.post('learn/ask',{'question':prompt[:80]}).status_code,429)
        self.assertEqual(self.post('learn/ask',{'question':'短'}).status_code,422)
