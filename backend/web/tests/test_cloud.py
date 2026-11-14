import unittest
import test_app as base
from test_app import app
from unittest.mock import patch
class CloudBoundaryTests(unittest.TestCase):
    setUp=base.AppTests.setUp
    def test_cloud_origin_explicitly_allowed_without_opening_other_origins(self):
        headers={**self.headers,'Origin':'https://8.130.110.58:4312'}
        with patch.object(app,'ORIGINS',app.ORIGINS|{'https://8.130.110.58:4312'}):
            response=self.client.post('/api/learn/sessions',json={},headers=headers)
            self.assertEqual(response.status_code,401) # Passed origin/CSRF, requires learner profile.
            response=self.client.post('/api/learn/sessions',json={},headers={**headers,'Origin':'https://evil.example'})
            self.assertEqual(response.status_code,403)
    def test_tls_profile_cookie_is_secure(self):
        client=base.TestClient(app.app,base_url='https://127.0.0.1:4312')
        response=client.get('/api/learn/bootstrap')
        self.assertIn('Secure',response.headers['set-cookie'])
        self.assertIn('HttpOnly',response.headers['set-cookie'])
