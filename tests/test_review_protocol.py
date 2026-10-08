"""Immediate reconciliation for new plans; frozen legacy repeat plans stay intact."""
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


def legacy_plan(entries):
    """The old persisted shape, with deterministic aliases for migration checks."""
    return {'version': 1, 'case_ids': sorted(entry['id'] for entry in entries), 'delay_days': 7,
            'rounding': '15% rounded to nearest integer, half up; public company strata',
            'repeats': [{'alias': f'repeat_{i:024x}', 'case_id': entry['id']}
                        for i, entry in enumerate(entries[::4][:3])]}


class ProtocolFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.path = Path(self.tmp.name) / 'reviews.sqlite3'
        self.store = ReviewStore(self.path, clock=lambda: self.now)
        self.entries = [{'id': f'case_{i:02d}', 'company': f'Company {i // 4}',
                         'fiscal_year': 2024, 'statement_type': 'IncomeStatement'} for i in range(20)]
        self.scope = {'dataset': 'pilot', 'fingerprint': 'frozen-corpus', 'reviewer_id': 'accountant-a'}
        self.store.register_protocol('pilot', 'frozen-corpus', self.entries)
        self.dataset = type('Dataset', (), {'fingerprint': 'frozen-corpus'})()

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

    def restored_store(self, name='restored'):
        store = ReviewStore(Path(self.tmp.name) / f'{name}.sqlite3', clock=lambda: self.now)
        store.register_protocol('pilot', 'frozen-corpus', self.entries)
        return store

    def freeze_legacy(self):
        plan = legacy_plan(self.entries)
        with self.store.connect() as con:
            con.execute('INSERT INTO protocol_plans VALUES (?,?,?,?)',
                        (*self.store._key(self.scope), json.dumps(plan, sort_keys=True)))
        return plan


class ImmediateReviewProtocolTests(ProtocolFixture):
    def test_all_twenty_locked_assessments_open_reconciliation_immediately(self):
        protocol = self.store.protocol(self.scope)
        self.assertEqual(protocol['plan_version'], 2)
        self.assertEqual(protocol['protocol_id'], 'immediate_reconciliation_v2')
        self.assertEqual(protocol['reliability_status'], 'reliability_not_measured')
        self.submit_initial(19)
        case_scope = {**self.scope, 'case_id': 'case_00'}
        with self.assertRaisesRegex(ValueError, 'every initial'):
            self.store.append(case_scope, 'reveal')
        before = self.store.history(self.scope)['events']
        self.store.append({**self.scope, 'case_id': 'case_19'}, 'blind', 'A', 'CPA', assessment())
        protocol = self.store.protocol(self.scope)
        self.assertEqual(protocol['phase'], 'reconciliation')
        self.assertEqual(protocol['repeat_required'], 0)
        self.assertEqual(protocol['repeat_completed'], 0)
        self.assertEqual(protocol['repeat_fraction'], 0)
        self.assertEqual(protocol['delay_days'], 0)
        self.assertIsNone(protocol['repeat_ready_at'])
        self.assertEqual(protocol['repeat_cases'], [])
        self.assertEqual(len(protocol['completed_case_ids']), 20)
        self.store.append(case_scope, 'reveal')
        self.store.append(case_scope, 'verification', 'A', 'CPA', {**assessment(), 'disposition': 'agree'})
        self.assertEqual(self.store.history(self.scope)['events'][:19], before)
        self.assertEqual(self.store.protocol(self.scope)['verification_completed_case_ids'], ['case_00'])
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.store.append(case_scope, 'blind', 'A', 'CPA', assessment())
        with self.store.connect() as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute('UPDATE events SET stage=?', ('verification',))
        with self.assertRaisesRegex(ValueError, 'not currently open'):
            self.store.append_repeat(self.scope, 'repeat_000000000000000000000000', 'A', 'CPA', assessment(), self.detail)

    def test_partial_and_complete_v2_exports_restore_the_exact_protocol(self):
        self.submit_initial(19)
        backup = self.store.history(self.scope)
        self.assertEqual(backup['schema_version'], 2)
        self.assertEqual(backup['protocol_version'], 2)
        self.assertEqual(backup['protocol_plan']['reliability_status'], 'reliability_not_measured')
        restored = self.restored_store()
        self.assertEqual(restored.import_events(backup, self.dataset, self.detail), {'imported': 19, 'unchanged': 0})
        self.assertEqual(restored.history(self.scope), backup)
        self.assertEqual(restored.protocol(self.scope)['phase'], 'initial')
        self.assertEqual(restored.import_events(backup, self.dataset, self.detail), {'imported': 0, 'unchanged': 19})
        self.store.append({**self.scope, 'case_id': 'case_19'}, 'blind', 'A', 'CPA', assessment())
        self.store.append({**self.scope, 'case_id': 'case_00'}, 'reveal')
        complete = self.store.history(self.scope)
        self.assertEqual(restored.import_events(complete, self.dataset, self.detail), {'imported': 2, 'unchanged': 19})
        self.assertEqual(restored.history(self.scope), complete)
        self.assertEqual(restored.protocol(self.scope)['phase'], 'reconciliation')

    def test_new_plans_survive_restart_and_are_isolated_from_other_reviewers(self):
        self.submit_initial()
        before = self.store.history(self.scope)
        restarted = ReviewStore(self.path, clock=lambda: self.now)
        restarted.register_protocol('pilot', 'frozen-corpus', self.entries)
        self.assertEqual(restarted.history(self.scope), before)
        self.assertEqual(restarted.protocol(self.scope)['phase'], 'reconciliation')
        other = {**self.scope, 'reviewer_id': 'accountant-b'}
        self.assertEqual(restarted.protocol(other)['phase'], 'initial')
        self.assertEqual(restarted.history(other)['events'], [])
        with self.assertRaises(ValueError):
            restarted.append({**other, 'case_id': 'case_00'}, 'reveal')

    def test_bad_plan_versions_and_changed_protocols_roll_back(self):
        self.submit_initial(1)
        backup = self.store.history(self.scope)
        variants = []
        unknown = copy.deepcopy(backup)
        unknown['protocol_version'] = 3
        variants.append(unknown)
        disguised = copy.deepcopy(backup)
        disguised['protocol_version'] = 1
        variants.append(disguised)
        bool_version = copy.deepcopy(backup)
        bool_version['protocol_plan']['version'] = True
        variants.append(bool_version)
        repeat = copy.deepcopy(backup)
        repeat['protocol_plan']['repeats'] = [{'alias': 'repeat_' + '0' * 24, 'case_id': 'case_00'}]
        variants.append(repeat)
        omitted = copy.deepcopy(backup)
        del omitted['protocol_plan']
        variants.append(omitted)
        for i, changed in enumerate(variants):
            restored = self.restored_store(f'invalid_{i}')
            with self.subTest(i=i), self.assertRaises(ValueError):
                restored.import_events(changed, self.dataset, self.detail)
            with restored.connect() as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
                self.assertEqual(con.execute('SELECT COUNT(*) FROM protocol_plans').fetchone()[0], 0)

    def test_future_timestamp_import_does_not_create_partial_plan_or_events(self):
        self.submit_initial(2)
        backup = self.store.history(self.scope)
        backup['events'][1]['created_at'] = (self.now + timedelta(seconds=1)).isoformat()
        restored = self.restored_store('future')
        with self.assertRaisesRegex(ValueError, 'Invalid event timestamp'):
            restored.import_events(backup, self.dataset, self.detail)
        with restored.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM protocol_plans').fetchone()[0], 0)


class LegacyReviewProtocolTests(ProtocolFixture):
    def setUp(self):
        super().setUp()
        self.frozen = self.freeze_legacy()

    def complete_repeat(self):
        self.now += timedelta(days=7)
        aliases = self.store.protocol(self.scope)['repeat_cases']
        for case in aliases:
            self.store.append_repeat(self.scope, case['id'], 'A', 'CPA', assessment(), self.detail)
        return aliases

    def test_existing_v1_plan_retains_all_cases_and_seven_day_delay(self):
        self.submit_initial(19)
        case_scope = {**self.scope, 'case_id': 'case_00'}
        with self.assertRaisesRegex(ValueError, 'every initial'):
            self.store.append(case_scope, 'reveal')
        self.now += timedelta(hours=3)
        self.store.append({**self.scope, 'case_id': 'case_19'}, 'blind', 'A', 'CPA', assessment())
        protocol = self.store.protocol(self.scope)
        self.assertEqual(protocol['plan_version'], 1)
        self.assertEqual(protocol['protocol_id'], 'delayed_repeat_v1')
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
        self.assertEqual(self.store.protocol(self.scope)['completed_case_ids'], [])
        self.assertEqual(self.store.protocol(self.scope)['verification_completed_case_ids'], [])
        with self.assertRaises(ValueError):
            self.store.append(case_scope, 'reveal')
        with self.store.connect() as con:
            self.assertEqual(json.loads(con.execute('SELECT payload FROM protocol_plans').fetchone()[0]), self.frozen)

    def test_frozen_repeat_aliases_hide_prior_answers_and_preserve_initial_records(self):
        self.submit_initial()
        initial = self.store.history(self.scope)['events']
        self.now += timedelta(days=7)
        cases = self.store.protocol(self.scope)['repeat_cases']
        self.assertEqual(len(cases), 3)
        self.assertEqual(len({c['company'] for c in cases}), 3)
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

    def test_v1_restart_keeps_subset_while_new_reviewer_gets_v2(self):
        self.submit_initial()
        self.now += timedelta(days=7)
        first = self.store.protocol(self.scope)
        restarted = ReviewStore(self.path, clock=lambda: self.now)
        restarted.register_protocol('pilot', 'frozen-corpus', self.entries)
        self.assertEqual(restarted.protocol(self.scope), first)
        other_scope = {**self.scope, 'reviewer_id': 'accountant-b'}
        self.assertEqual(restarted.protocol(other_scope)['phase'], 'initial')
        self.assertEqual(restarted.protocol(other_scope)['plan_version'], 2)
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

    def test_v1_exports_restore_both_passes_and_legacy_schema_one(self):
        self.submit_initial()
        self.complete_repeat()
        scope = {**self.scope, 'case_id': 'case_00'}
        self.store.append(scope, 'reveal')
        self.store.append(scope, 'verification', 'A', 'CPA', {**assessment(), 'disposition': 'agree'})
        backup = self.store.history(self.scope)
        self.assertEqual(backup['protocol_plan'], self.frozen)
        self.assertEqual(backup['protocol_version'], 1)
        for old_schema in (False, True):
            envelope = copy.deepcopy(backup)
            if old_schema:
                envelope['schema_version'] = 1
                del envelope['protocol_version']
            restored = self.restored_store(f'restored_{old_schema}')
            self.assertEqual(restored.import_events(envelope, self.dataset, self.detail)['imported'], 25)
            self.assertEqual(restored.history(self.scope), backup)

    def test_partial_v1_backup_requires_frozen_plan_to_avoid_silent_migration(self):
        self.submit_initial(19)
        reviewer_export = self.store.history(self.scope)
        self.assertNotIn('protocol_plan', reviewer_export)
        self.assertNotIn('repeat_', json.dumps(reviewer_export))
        self.assertEqual(self.store.import_events(reviewer_export, self.dataset, self.detail), {'imported': 0, 'unchanged': 19})
        old_export = copy.deepcopy(reviewer_export)
        old_export['schema_version'] = 1
        del old_export['protocol_version']
        self.assertEqual(self.store.import_events(old_export, self.dataset, self.detail), {'imported': 0, 'unchanged': 19})
        restored = self.restored_store('partial')
        with self.assertRaisesRegex(ValueError, 'complete frozen protocol plan'):
            restored.import_events(reviewer_export, self.dataset, self.detail)
        with self.assertRaisesRegex(ValueError, 'complete frozen protocol plan'):
            restored.import_events(old_export, self.dataset, self.detail)
        curator_backup = self.store.history(self.scope, allow_during_repeat=True)
        self.assertEqual(curator_backup['protocol_plan'], self.frozen)
        self.assertEqual(restored.import_events(curator_backup, self.dataset, self.detail)['imported'], 19)
        self.assertEqual(restored.protocol(self.scope)['plan_version'], 1)
        with self.assertRaisesRegex(ValueError, 'already frozen'):
            immediate = copy.deepcopy(curator_backup)
            immediate['protocol_version'] = 2
            immediate['protocol_plan'] = self.restored_store('new').history(self.scope)['protocol_plan']
            restored.import_events(immediate, self.dataset, self.detail)

    def test_early_repeat_import_rolls_back_plan_and_events_atomically(self):
        self.submit_initial()
        self.complete_repeat()
        backup = self.store.history(self.scope)
        tampered = copy.deepcopy(backup)
        tampered['events'][20]['created_at'] = tampered['events'][0]['created_at']
        restored = self.restored_store('tampered')
        with self.assertRaisesRegex(ValueError, 'seven-day'):
            restored.import_events(tampered, self.dataset, self.detail)
        with restored.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM protocol_plans').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
