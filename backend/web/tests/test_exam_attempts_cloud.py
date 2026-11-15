"""Cloud single-tenant exam attempts: save/resume/submit, grading, and gates."""
import copy, json, unittest
import test_app as base
from test_app import app, TestClient, one, transaction, Json

PAPER = {'id': 'exam-2031', 'year': 2031, 'title': '2031年真题', 'type': 'past_exam',
         'review_status': 'approved', 'category_id': None, 'content_sha256': 'hash-1',
         'payload': {}, 'source_files': {}}

def question(number, kind, answer):
    return {'paper_id': 'exam-2031', 'number': number, 'kind': kind,
            'answer_status': 'candidate' if answer else 'unresolved', 'review_status': 'approved',
            'payload': {'number': number, 'kind': kind, 'answer_status': 'candidate' if answer else 'unresolved',
                        'prompt': '第%d题' % number, 'options': ['甲', '乙', '丙'],
                        'answer': answer, 'explanation': '提交后可见' if answer else ''}}

class ExamAttemptTests(unittest.TestCase):
    setUp = base.AppTests.setUp
    post = base.AppTests.post

    def prepare(self, status='approved'):
        with transaction() as cur:
            # 测试库沿用旧版“仅草稿”约束，先升级为允许 approved（与 exam_review.approve 相同）
            for table in ('exam_papers', 'exam_questions'):
                constraint = table + '_review_status_check'
                cur.execute('SELECT pg_get_constraintdef(oid) AS d FROM pg_constraint WHERE conrelid=%s::regclass AND conname=%s', (table, constraint))
                found = cur.fetchone()
                if found and "'approved'" not in found['d']:
                    cur.execute('ALTER TABLE {} DROP CONSTRAINT {}'.format(table, constraint))
                    cur.execute("ALTER TABLE {} ADD CONSTRAINT {} CHECK(review_status IN ('pending_review','approved'))".format(table, constraint))
            cur.execute('INSERT INTO exam_papers(id,year,title,content_sha256,payload,source_files,review_status)'
                        ' VALUES(%(id)s,%(year)s,%(title)s,%(content_sha256)s,%(payload)s,%(source_files)s,%(status)s)',
                        {**PAPER, 'payload': Json(PAPER['payload']), 'source_files': Json(PAPER['source_files']), 'status': status})
            for q in (question(1, 'single_choice', ['A']), question(2, 'multiple_choice', ['A', 'B']), question(3, 'single_choice', [])):
                cur.execute('INSERT INTO exam_questions(paper_id,number,kind,answer_status,review_status,payload)'
                            ' VALUES(%s,%s,%s,%s,%s,%s)', (q['paper_id'], q['number'], q['kind'], q['answer_status'], q['review_status'], Json(q['payload'])))
        self.client.get('/api/learn/bootstrap')

    def start(self, paper='exam-2031'):
        r = self.post('learn/exam-papers/' + paper + '/start', {})
        return r

    def test_start_is_idempotent_and_snapshot_hides_solutions(self):
        self.prepare()
        r = self.start()
        self.assertEqual(r.status_code, 200, r.text)
        sid = r.json()['id']
        self.assertEqual(self.start().json()['id'], sid)
        first = self.client.get('/api/learn/exam-attempts/' + sid).json()
        self.assertEqual(len(first['questions']), 3)
        self.assertNotIn('solution', first['questions'][0])
        self.assertNotIn('correct', first['questions'][0])
        self.assertEqual(first['questions'][0]['selected'], [])

    def test_save_resume_submit_grading_and_history(self):
        self.prepare()
        sid = self.start().json()['id']
        url = 'exam-attempts/' + sid
        for revision, (number, selected) in enumerate([(1, [0]), (2, [1]), (3, [2])]):
            r = self.post('learn/' + url + '/answer', {'number': number, 'selected': selected, 'revision': revision})
            self.assertEqual(r.json(), {'revision': revision + 1})
        resumed = self.client.get('/api/learn/exam-attempts/' + sid).json()
        self.assertEqual(resumed['questions'][1]['selected'], [1])
        result = self.post('learn/' + url + '/submit', {'revision': 3})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['result'], {'correct': 1, 'total': 2, 'unresolved': 1, 'unanswered': 0, 'answered': 3})
        body = result.json()
        self.assertTrue(body['questions'][0]['correct'])
        self.assertFalse(body['questions'][1]['correct'])
        self.assertIsNone(body['questions'][2]['correct'])
        self.assertEqual(body['questions'][0]['solution']['answer'], ['A'])
        # idempotent resubmit, answers locked after submit
        self.assertEqual(self.post('learn/' + url + '/submit', {'revision': 0}).json(), body)
        self.assertEqual(self.post('learn/' + url + '/answer', {'number': 1, 'selected': [1], 'revision': 3}).status_code, 409)
        # new attempt after submit + history endpoint
        self.assertNotEqual(self.start().json()['id'], sid)
        history = self.client.get('/api/learn/exam-attempts?paper_id=exam-2031').json()
        self.assertEqual(len(history), 2)

    def test_invalid_selections_and_revision_conflicts(self):
        self.prepare()
        sid = self.start().json()['id']
        url = 'learn/exam-attempts/' + sid
        for selected in ([0, 0], [8], [-1], [True], ['0']):
            self.assertEqual(self.post(url + '/answer', {'number': 1, 'selected': selected, 'revision': 0}).status_code, 422)
        self.assertEqual(self.post(url + '/answer', {'number': 1, 'selected': [0, 1], 'revision': 0}).status_code, 422)  # 单选多选
        self.assertEqual(self.post(url + '/answer', {'number': 99, 'selected': [0], 'revision': 0}).status_code, 422)
        self.assertEqual(self.post(url + '/submit', {'revision': 5}).status_code, 409)
        self.assertEqual(self.post(url + '/answer', {'number': 2, 'selected': [1, 0], 'revision': 0}).status_code, 200)
        self.assertEqual(self.post(url + '/answer', {'number': 2, 'selected': [], 'revision': 0}).status_code, 409)
        self.assertEqual(self.post(url + '/answer', {'number': 2, 'selected': [0, 1], 'revision': 1}).status_code, 200)

    def test_pending_paper_and_missing_attempt(self):
        self.prepare(status='pending_review')
        self.assertEqual(self.start().status_code, 403)
        with transaction() as cur:
            cur.execute("UPDATE exam_papers SET review_status='approved'")
        self.assertEqual(self.start().status_code, 200)
        self.assertEqual(self.client.get('/api/learn/exam-attempts/missing').status_code, 404)

if __name__ == '__main__':
    unittest.main()
