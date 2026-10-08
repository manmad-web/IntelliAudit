"""Leakage boundaries and append-only, atomic review lifecycle regression tests."""
import copy
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dashboard.server import Store, handler_for, BlindDataset, faults


def annotation():
    return {'judgement': 'insufficient_evidence', 'error_type': None, 'rows': [],
            'evidence_sufficiency': 'insufficient', 'authority_disposition': 'unresolved',
            'citations': [], 'authority_currency': 'unresolved', 'authority_source': '',
            'proof_sets': [['statement:L0001']], 'reasoning': 'Shipment timing evidence is absent.',
            'confidence': 'medium'}


class BlindReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        folder = root / 'data/review_pilot'
        (folder / 'curator').mkdir(parents=True)
        exam = {'exam_id': 'case_opaque', 'metadata': {'company': 'Example', 'fiscal_year': 2024,
                'statement_type': 'IncomeStatement', 'rule_id': 'SECRET_RULE'},
                'statement_text': '[row 0]: Revenue | $500', 'transaction_data': 'Invoice total $500', 'form': 1}
        (folder / 'public_cases.jsonl').write_text(json.dumps(exam) + '\n')
        current_folder = root / 'data/review_pilot_v2'
        (current_folder / 'curator').mkdir(parents=True)
        (current_folder / 'public_cases.jsonl').write_text(json.dumps(exam) + '\n')
        (folder / 'curator/proposals.jsonl').write_text(json.dumps({'exam_id': 'case_opaque',
                'answer': {'exam_id': 'case_opaque', 'record_type': 'injected',
                'rule_id': 'SECRET_RULE', 'corrected_statement_text': 'SECRET_CORRECTION'}}) + '\n')
        (current_folder / 'curator/proposals.jsonl').write_bytes((folder / 'curator/proposals.jsonl').read_bytes())
        handler = handler_for(Store(root))
        handler.log_message = lambda *args: None
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.scope = {'dataset': 'pilot', 'case_id': 'case_opaque', 'reviewer_id': 'reviewer-a'}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, body=None, headers=None):
        request = Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                          headers={'Content-Type': 'application/json', **(headers or {})})
        with urlopen(request) as response:
            return json.load(response)

    def fails(self, path, body=None, status=400, headers=None):
        with self.assertRaises(HTTPError) as error:
            self.request(path, body, headers)
        self.assertEqual(error.exception.code, status)

    def submit(self, reviewer='reviewer-a', stage='blind', ann=None):
        body = {**self.scope, 'reviewer_id': reviewer, 'reviewer_name': 'Accountant',
                'qualification': 'Qualified accountant; not a case author', 'stage': stage,
                'annotation': ann or annotation()}
        return self.request('/api/review/submit', body)

    def test_real_pilot_proposals_reveal_without_invented_errors(self):
        dataset = BlindDataset(Store(), 'pilot')
        self.assertEqual(len(dataset.entries), 20)
        for entry in dataset.entries:
            proposal = dataset.reveal(entry['id'])
            if proposal['answer']['general_judgement'] in {'Insufficient evidence', 'Correct'}:
                self.assertEqual(proposal['errors'], [])
        self.assertEqual(faults({'record_type': 'proposed_evidence_withheld',
                                 'error_identification': None, 'error_type': None}), [])

    def test_default_endpoints_exclude_keys_and_direct_bypasses(self):
        for path in ('/api/blind/index', '/api/blind/case?id=case_opaque'):
            value = json.dumps(self.request(path))
            for forbidden in ('SECRET_', 'rule_id', 'corrected_statement', '"form":', 'citation_tier'):
                self.assertNotIn(forbidden, value)
        for path in ('/api/index', '/api/case?id=case_opaque', '/api/search?q=SECRET_RULE',
                     '/index.html', '/app.js', '/data/review_pilot/curator/proposals.jsonl',
                     '/api/review/reveal', '/api/blind/case?id=case_opaque&reveal=true'):
            self.fails(path, status=400 if 'reveal=true' in path else 404)

    def test_submit_then_reveal_then_verify_and_blind_immutable(self):
        self.fails('/api/review/reveal', self.scope)
        changed = {**annotation(), 'disposition': 'agree'}
        self.fails('/api/review/submit', {**self.scope, 'reviewer_name': 'A', 'qualification': 'CPA', 'stage': 'verification', 'annotation': changed})
        first = self.submit()['record']
        self.fails('/api/review/submit', {**self.scope, 'reviewer_name': 'A', 'qualification': 'CPA', 'stage': 'blind', 'annotation': annotation()})
        reveal = self.request('/api/review/reveal', self.scope)
        self.assertIn('SECRET_CORRECTION', json.dumps(reveal))
        self.submit(stage='verification', ann=changed)
        history = self.request('/api/review/history?dataset=pilot&case_id=case_opaque&reviewer_id=reviewer-a')
        self.assertEqual([e['stage'] for e in history['events']], ['blind', 'reveal', 'verification'])
        self.assertEqual(history['events'][0], first)
        self.assertNotIn('SECRET_', json.dumps(history))
        other = self.request('/api/review/history?dataset=pilot&case_id=case_opaque&reviewer_id=reviewer-b')
        self.assertEqual(other['events'], [])
        self.fails('/api/review/reveal', {**self.scope, 'reviewer_id': 'reviewer-b'})

    def test_host_origin_and_input_validation(self):
        self.fails('/api/blind/index', status=403, headers={'Host': 'evil.example'})
        self.fails('/api/review/reveal', self.scope, 403, {'Origin': 'https://evil.example'})
        self.fails('/api/blind/index?dataset=pilot&dataset=us-gaap')
        for replacement in ({'rows': [True]}, {'rows': [999]}, {'proof_sets': [['not-a-unit']]},
                            {'citations': [False]}, {'reasoning': ''}, {'authority_currency': 'verified'},
                            {'evidence_quotes': [{'unit_id': 'statement:L0001', 'quote': 'not in evidence'}]}):
            body = {**self.scope, 'reviewer_name': 'A', 'qualification': 'CPA', 'stage': 'blind',
                    'annotation': {**annotation(), **replacement}}
            self.fails('/api/review/submit', body)

    def test_exports_imports_preserve_separate_reviewers_and_atomic_conflicts(self):
        self.submit()
        export = self.request('/api/review/export?dataset=pilot&reviewer_id=reviewer-a')
        self.assertNotIn('SECRET_', json.dumps(export))
        self.assertEqual(self.request('/api/review/import', export), {'imported': 0, 'unchanged': 1})
        second = copy.deepcopy(export)
        second['scope']['reviewer_id'] = 'reviewer-b'
        second['events'][0].update(reviewer_id='reviewer-b', event_id='second-reviewer-event')
        self.assertEqual(self.request('/api/review/import', second)['imported'], 1)
        conflicting = copy.deepcopy(export)
        conflicting['events'][0]['annotation']['reasoning'] = 'Overwriting original'
        self.fails('/api/review/import', conflicting)
        stale = copy.deepcopy(export)
        stale['schema_version'] = 0
        self.fails('/api/review/import', stale)
        stale = copy.deepcopy(export)
        stale['scope']['fingerprint'] = 'old-version'
        self.fails('/api/review/import', stale)
        atomic = copy.deepcopy(second)
        atomic['scope']['reviewer_id'] = 'reviewer-c'
        atomic['events'][0].update(reviewer_id='reviewer-c', event_id='first-valid')
        invalid = copy.deepcopy(atomic['events'][0])
        invalid.update(event_id='later-invalid', stage='verification')
        invalid['annotation']['disposition'] = 'agree'
        atomic['events'].append(invalid)
        self.fails('/api/review/import', atomic)
        after = self.request('/api/review/export?dataset=pilot&reviewer_id=reviewer-c')
        self.assertEqual(after['events'], [])


if __name__ == '__main__':
    unittest.main()
