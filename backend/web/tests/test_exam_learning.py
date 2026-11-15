"""Verify the legacy cloud app never exposes draft payload without staff identity."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app

class CloudExamLearningTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app, base_url='http://127.0.0.1:4312')
    def tearDown(self):self.client.close()
    def test_directory_and_detail_keep_anonymous_cloud_in_summary_mode(self):
        summary = {'id':'p','year':2026,'title':'年度真题','review_status':'pending_review','question_count':165,'answered_count':0,'unresolved_count':165,'card_count':0}
        with patch('exam_learning.rows', return_value=[summary]) as query:
            listing = self.client.get('/api/learn/exam-papers')
            self.assertEqual(listing.status_code,200)
            self.assertEqual(listing.json(),{'papers':[summary],'can_preview':False})
            detail = self.client.get('/api/learn/exam-papers/p').json()
            self.assertEqual(detail,{**summary,'can_preview':False})
            self.assertEqual(query.call_count,2)
    def test_draft_read_and_write_are_denied_before_loading_payload(self):
        with patch('exam_learning.one') as query:
            self.assertEqual(self.client.get('/api/learn/exam-papers/p/questions/1').status_code,403)
            query.assert_not_called()
        result=self.client.post('/api/learn/exam-papers/p',json={},headers={'X-CSRF-Token':app.CSRF})
        self.assertEqual(result.status_code,405)
    def test_missing_paper_is_not_a_blank_success(self):
        with patch('exam_learning.rows',return_value=[]):
            self.assertEqual(self.client.get('/api/learn/exam-papers/missing').status_code,404)
            self.assertEqual(self.client.get('/api/learn/exam-papers').json()['papers'],[])

if __name__=='__main__':unittest.main()
