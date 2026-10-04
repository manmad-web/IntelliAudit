"""Whole-corpus embargo, delayed repeats, durable aliases and immutable records."""
import copy
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dashboard.review_store import ReviewStore


def assessment():
    return {'judgement': 'insufficient_evidence', 'error_type': None, 'rows': [],
            'evidence_sufficiency': 'insufficient', 'authority_disposition': 'unresolved',
            'citations': [], 'authority_currency': 'unresolved', 'authority_source': '',
            'proof_sets': [['statement:L0001']], 'reasoning': 'Contract evidence is missing.',
            'confidence': 'medium'}


class ReviewProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.path = Path(self.tmp.name) / 'reviews.sqlite3'
        self.store = ReviewStore(self.path, clock=lambda: self.now)
        self.entries = [{'id': f'case_{i:02d}', 'company': f'Company {i // 4}',
                         'fiscal_year': 2024, 'statement_type': 'IncomeStatement'} for i in range(20)]
        self.scope = {'dataset': 'pilot', 'fingerprint': 'frozen-v1', 'reviewer_id': 'accountant-a'}
        self.store.register_protocol('pilot', 'frozen-v1', self.entries)

    def tearDown(self):
        # This also catches accidentally open SQLite handles on Windows.
        self.tmp.cleanup()

    def detail(self, case_id):
        return {'exam': {'exam_id': case_id, 'metadata': {'company': 'Example'},
                         'statement_text': '[row 0]: Revenue | $500', 'transaction_data': 'Invoice'},
                'evidence_units': [{'id': 'statement:L0001', 'text': '[row 0]: Revenue | $500', 'source': 'statement'}]}

    def submit_initial(self, count=20):
        for entry in self.entries[:count]:
            self.store.append({**self.scope, 'case_id': entry['id']}, 'blind', 'A', 'CPA', assessment())

    def complete_repeat(self):
        self.now += timedelta(days=7)
        aliases = self.store.protocol(self.scope)['repeat_cases']
        for case in aliases:
            self.store.append_repeat(self.scope, case['id'], 'A', 'CPA', assessment(), self.detail)
        return aliases

    def test_all_cases_and_seven_day_delay_are_required(self):
        self.submit_initial(19)
        case_scope = {**self.scope, 'case_id': 'case_00'}
        with self.assertRaisesRegex(ValueError, 'every initial'):
            self.store.append(case_scope, 'reveal')
        self.now += timedelta(hours=3)
        self.store.append({**self.scope, 'case_id': 'case_19'}, 'blind', 'A', 'CPA', assessment())
        protocol = self.store.protocol(self.scope)
        self.assertEqual(protocol['phase'], 'waiting')
        self.assertEqual(protocol['repeat_required'], 3)
        self.assertEqual(protocol['repeat_fraction'], .15)
        self.assertEqual(protocol['repeat_cases'], [])
        self.assertEqual(datetime.fromisoformat(protocol['repeat_ready_at']), self.now + timedelta(days=7))
        self.now += timedelta(days=7, seconds=-1)
        self.assertEqual(self.store.protocol(self.scope)['phase'], 'waiting')
        with self.assertRaises(ValueError):
            self.store.append(case_scope, 'reveal')
        self.now += timedelta(seconds=1)
        self.assertEqual(self.store.protocol(self.scope)['phase'], 'repeat')
        with self.assertRaises(ValueError):
            self.store.append(case_scope, 'reveal')

    def test_fresh_shuffled_repeat_aliases_hide_prior_answers(self):
        self.submit_initial()
        initial = self.store.history(self.scope)['events']
        self.now += timedelta(days=7)
        cases = self.store.protocol(self.scope)['repeat_cases']
        self.assertEqual(len(cases), 3)
        self.assertEqual(len({c['company'] for c in cases}), 3)
        self.assertTrue(all(c['id'].startswith('repeat_') for c in cases))
        self.assertFalse({c['id'] for c in cases} & {c['id'] for c in self.entries})
        with self.assertRaises(PermissionError):
            self.store.history(self.scope)
        for case in cases:
            detail = self.store.repeat_detail(self.scope, case['id'], self.detail)
            self.assertEqual(detail['exam']['exam_id'], case['id'])
            self.assertNotIn('case_', json.dumps(detail))
            record = self.store.append_repeat(self.scope, case['id'], 'A', 'CPA', assessment(), self.detail)
            self.assertEqual(record['case_id'], case['id'])
        history = self.store.history(self.scope)['events']
        self.assertEqual(history[:20], initial)
        self.assertEqual([e['stage'] for e in history[20:]], ['repeat'] * 3)
        self.assertEqual(self.store.protocol(self.scope)['phase'], 'reconciliation')

    def test_repeat_subset_survives_restart_and_is_reviewer_scoped(self):
        self.submit_initial()
        self.now += timedelta(days=7)
        first = self.store.protocol(self.scope)
        restarted = ReviewStore(self.path, clock=lambda: self.now)
        restarted.register_protocol('pilot', 'frozen-v1', self.entries)
        self.assertEqual(restarted.protocol(self.scope), first)
        other_scope = {**self.scope, 'reviewer_id': 'accountant-b'}
        self.assertEqual(restarted.protocol(other_scope)['phase'], 'initial')
        with self.assertRaises(ValueError):
            restarted.repeat_detail(other_scope, first['repeat_cases'][0]['id'], self.detail)

    def test_repeat_is_immutable_and_wrong_or_early_alias_is_rejected(self):
        self.submit_initial()
        with self.assertRaises(ValueError):
            self.store.append_repeat(self.scope, 'repeat_early', 'A', 'CPA', assessment(), self.detail)
        self.now += timedelta(days=7)
        alias = self.store.protocol(self.scope)['repeat_cases'][0]['id']
        with self.assertRaises(ValueError):
            self.store.repeat_detail(self.scope, 'case_00', self.detail)
        self.store.append_repeat(self.scope, alias, 'A', 'CPA', assessment(), self.detail)
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.store.append_repeat(self.scope, alias, 'A', 'CPA', assessment(), self.detail)

    def test_reconciliation_and_export_restore_keep_both_passes(self):
        self.submit_initial()
        self.complete_repeat()
        scope = {**self.scope, 'case_id': 'case_00'}
        with self.assertRaisesRegex(ValueError, 'Reveal'):
            self.store.append(scope, 'verification', 'A', 'CPA', {**assessment(), 'disposition': 'agree'})
        self.store.append(scope, 'reveal')
        self.store.append(scope, 'verification', 'A', 'CPA', {**assessment(), 'disposition': 'agree'})
        backup = self.store.history(self.scope)
        self.assertIn('protocol_plan', backup)
        restored = ReviewStore(Path(self.tmp.name) / 'restored.sqlite3', clock=lambda: self.now)
        restored.register_protocol('pilot', 'frozen-v1', self.entries)
        dataset = type('Dataset', (), {'fingerprint': 'frozen-v1'})()
        result = restored.import_events(backup, dataset, self.detail)
        self.assertEqual(result['imported'], 25)
        self.assertEqual(restored.history(self.scope), backup)
        with self.store.connect() as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute('UPDATE events SET stage=?', ('verification',))

    def test_future_and_early_repeat_imports_roll_back_atomically(self):
        self.submit_initial()
        self.complete_repeat()
        backup = self.store.history(self.scope)
        tampered = copy.deepcopy(backup)
        tampered['events'][20]['created_at'] = tampered['events'][0]['created_at']
        restored = ReviewStore(Path(self.tmp.name) / 'tampered.sqlite3', clock=lambda: self.now)
        restored.register_protocol('pilot', 'frozen-v1', self.entries)
        dataset = type('Dataset', (), {'fingerprint': 'frozen-v1'})()
        with self.assertRaisesRegex(ValueError, 'seven-day'):
            restored.import_events(tampered, dataset, self.detail)
        self.assertEqual(restored.history(self.scope)['events'], [])
        with self.store.connect() as con:
            con.execute('SELECT payload FROM events').fetchall()


if __name__ == '__main__':
    unittest.main()
