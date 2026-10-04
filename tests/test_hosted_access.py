"""Authenticated identity, CSRF, role boundaries and durable invitation sessions."""
import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dashboard.auth_store import AuthStore, digest
from dashboard.review_store import ReviewStore
from dashboard.server import Store, handler_for


def annotation():
    return {'judgement': 'insufficient_evidence', 'error_type': None, 'rows': [],
            'evidence_sufficiency': 'insufficient', 'authority_disposition': 'unresolved',
            'citations': [], 'authority_currency': 'unresolved', 'authority_source': '',
            'proof_sets': [['statement:L0001']], 'reasoning': 'Acceptance evidence is missing.',
            'confidence': 'medium'}


class HostedAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        folder = self.root / 'data/review_pilot'
        (folder / 'curator').mkdir(parents=True)
        exams = [{'exam_id': f'case_{i:02d}', 'metadata': {'company': f'Company {i // 4}', 'fiscal_year': 2024, 'statement_type': 'IncomeStatement'}, 'statement_text': '[row 0]: Revenue | $500', 'transaction_data': 'Invoice $500'} for i in range(20)]
        (folder / 'public_cases.jsonl').write_text(''.join(json.dumps(exam) + '\n' for exam in exams), encoding='utf-8')
        (folder / 'curator/proposals.jsonl').write_text(''.join(json.dumps({'exam_id': exam['exam_id'], 'answer': {'exam_id': exam['exam_id'], 'record_type': 'control', 'corrected_statement_text': 'SECRET_PROPOSAL'}}) + '\n' for exam in exams), encoding='utf-8')
        self.now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        self.reviews = ReviewStore(self.root / 'reviews.sqlite3', clock=lambda: self.now)
        self.admin_code = 'test-admin-secret-' * 3
        self.auth = AuthStore(self.reviews.connect, self.admin_code)
        self.invite_a = self.auth.invite('Accountant A', 'CPA; independent reviewer')
        self.invite_b = self.auth.invite('Accountant B', 'CPA; independent reviewer')
        handler = handler_for(Store(self.root), reviews=self.reviews, auth=self.auth, public_origin='https://review.example')
        handler.log_message = lambda *args: None
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, body=None, session=None, extras=None):
        headers = {'Host': 'review.example', 'Origin': 'https://review.example', 'Content-Type': 'application/json'}
        if session:
            headers.update({'Cookie': session['cookie'], 'X-CSRF-Token': session['csrf_token']})
        headers.update(extras or {})
        req = Request(self.base + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        with urlopen(req) as response:
            data = json.load(response)
            if response.headers.get('Set-Cookie'):
                data['cookie_header'] = response.headers['Set-Cookie']
                data['cookie'] = data['cookie_header'].split(';')[0]
            return data

    def fails(self, status, path, body=None, session=None, extras=None):
        with self.assertRaises(HTTPError) as caught:
            self.request(path, body, session, extras)
        self.assertEqual(caught.exception.code, status)
        return json.load(caught.exception)

    def login(self, invitation=None):
        return self.request('/api/auth/login', {'invite_code': (invitation or self.invite_a)['invite_code']})

    def submit(self, session, case_id='case_00', **changes):
        return self.request('/api/review/submit', {'dataset': 'pilot', 'case_id': case_id, 'stage': 'blind', 'annotation': annotation(), **changes}, session)

    def test_unauthenticated_requests_and_secure_cookie(self):
        self.fails(401, '/api/blind/index')
        self.fails(401, '/api/review/submit', {'dataset': 'pilot'})
        self.fails(403, '/api/auth/login', {'invite_code': self.invite_a['invite_code']}, extras={'Origin': 'https://evil.example'})
        session = self.login()
        for flag in ('__Host-intelliaudit=', 'Secure', 'HttpOnly', 'SameSite=Strict', 'Path=/'):
            self.assertIn(flag, session['cookie_header'])
        self.assertEqual(self.request('/api/auth/session', session=session)['reviewer']['id'], self.invite_a['reviewer']['id'])
        self.fails(403, '/api/blind/index', session=session, extras={'Host': 'evil.example'})

    def test_identity_csrf_role_and_import_boundaries(self):
        session = self.login()
        body = {'dataset': 'pilot', 'case_id': 'case_00', 'stage': 'blind', 'annotation': annotation()}
        self.fails(403, '/api/review/submit', body, session, {'X-CSRF-Token': 'wrong'})
        self.fails(403, '/api/review/submit', {**body, 'reviewer_id': self.invite_b['reviewer']['id']}, session)
        self.fails(403, '/api/review/submit', {**body, 'reviewer_name': 'Impersonated'}, session)
        self.fails(403, '/api/admin/reviewers', session=session)
        self.fails(403, '/api/admin/invite', {'name': 'Unauthorized', 'qualification': 'CPA'}, session)
        self.fails(403, '/api/review/import', {'scope': {'dataset': 'pilot'}}, session)
        record = self.submit(session)['record']
        self.assertEqual(record['reviewer_id'], self.invite_a['reviewer']['id'])
        self.assertEqual(record['reviewer_name'], 'Accountant A')
        other = self.login(self.invite_b)
        self.assertEqual(self.request('/api/review/export?dataset=pilot', session=other)['events'], [])
        self.fails(403, '/api/review/history?dataset=pilot&case_id=case_00&reviewer_id=' + record['reviewer_id'], session=other)

    def test_restarts_logout_and_revocation(self):
        session = self.login()
        self.submit(session)
        restarted = AuthStore(self.reviews.connect, self.admin_code)
        token = session['cookie'].split('=', 1)[1]
        self.assertEqual(restarted.session(token)['reviewer']['id'], self.invite_a['reviewer']['id'])
        with self.reviews.connect() as con:
            hashed = con.execute('SELECT code_hash FROM review_accounts WHERE id=?', (self.invite_a['reviewer']['id'],)).fetchone()[0]
        self.assertEqual(hashed, digest(self.invite_a['invite_code']))
        self.assertNotEqual(hashed, self.invite_a['invite_code'])
        self.request('/api/auth/logout', {}, session)
        self.fails(401, '/api/blind/index', session=session)
        session = self.login()
        admin = self.request('/api/auth/login', {'invite_code': self.admin_code})
        self.request('/api/admin/revoke', {'reviewer_id': self.invite_a['reviewer']['id']}, admin)
        self.fails(401, '/api/blind/index', session=session)
        self.fails(403, '/api/auth/login', {'invite_code': self.invite_a['invite_code']})
        export = self.request('/api/admin/export', session=admin)
        self.assertEqual(len(export['events']), 1)

    def test_global_reveal_repeat_and_curator_embargo(self):
        session = self.login()
        admin = self.request('/api/auth/login', {'invite_code': self.admin_code})
        self.submit(session)
        self.fails(400, '/api/review/reveal', {'dataset': 'pilot', 'case_id': 'case_00'}, session)
        resolution = {'dataset': 'pilot', 'case_id': 'case_00', 'annotation': annotation(), 'reason': 'Evidence remains unresolved.'}
        self.fails(403, '/api/admin/adjudicate', resolution, admin)
        for i in range(1, 20):
            self.submit(session, f'case_{i:02d}')
        self.assertEqual(self.request('/api/review/protocol', session=session)['phase'], 'waiting')
        self.now += timedelta(days=7)
        repeats = self.request('/api/review/protocol', session=session)['repeat_cases']
        self.assertEqual(len(repeats), 3)
        self.fails(403, '/api/review/export', session=session)
        self.fails(403, '/api/blind/case?id=case_00', session=session)
        repeat_index = self.request('/api/blind/index', session=session)
        self.assertTrue(all(case['id'].startswith('repeat_') for case in repeat_index['cases']))
        # Curators can monitor completion without exposing prior answers to reviewers.
        self.assertEqual(self.request('/api/admin/comparison', session=admin)['reviewer_count'], 1)
        for repeat in repeats:
            detail = self.request('/api/review/repeat-case?id=' + repeat['id'], session=session)
            self.assertEqual(detail['exam']['exam_id'], repeat['id'])
            self.request('/api/review/repeat-submit', {'dataset': 'pilot', 'case_id': repeat['id'], 'annotation': annotation()}, session)
        self.assertEqual(self.request('/api/review/protocol', session=session)['phase'], 'reconciliation')
        proposal = self.request('/api/review/reveal', {'dataset': 'pilot', 'case_id': 'case_00'}, session)
        self.assertIn('SECRET_PROPOSAL', json.dumps(proposal))
        saved = self.request('/api/admin/adjudicate', resolution, admin)['record']
        self.assertEqual(len(saved['source_event_ids']), 1)
        self.assertEqual(saved['status'], 'curator_resolution_not_publication_gold')

    def test_bad_logins_are_limited_without_storing_codes(self):
        for _ in range(15):
            self.fails(403, '/api/auth/login', {'invite_code': 'invalid-code'})
        blocked = self.fails(403, '/api/auth/login', {'invite_code': self.invite_a['invite_code']})
        self.assertIn('Too many', blocked['error'])


if __name__ == '__main__':
    unittest.main()
