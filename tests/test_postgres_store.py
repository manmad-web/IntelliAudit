"""Hosted storage regression tests plus opt-in, isolated live PostgreSQL checks."""
import os
import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dashboard.postgres_store import PostgresReviewStore
from dashboard.auth_store import AuthStore


class DatabaseFailure(Exception):
    pass


class FakeConnection:
    def __init__(self):
        self.execute = Mock()
        self.closed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, kind, value, trace):
        self.rolled_back = kind is not None
        self.closed = True


class PostgresBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.connections = []

        def connect(*args, **kwargs):
            con = FakeConnection()
            self.connections.append(con)
            return con

        self.driver = SimpleNamespace(connect=Mock(side_effect=connect), Error=DatabaseFailure)
        self.driver_patch = patch.dict('sys.modules', {'psycopg': self.driver})
        self.driver_patch.start()
        self.addCleanup(self.driver_patch.stop)

    def test_refuses_bad_database_urls_public_schema_and_unencrypted_connections(self):
        for url in ('', 'sqlite:///reviews.db', 'postgresql://host', 'postgresql://host:wrong/db',
                    'postgresql://host/db?sslmode=disable', 'postgresql://host/db?sslmode=prefer'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                PostgresReviewStore(url)
        for schema in ('public', 'pg_catalog', 'bad; DROP SCHEMA public', 'bad-name'):
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                PostgresReviewStore('postgresql://example/db', schema=schema)
        self.driver.connect.assert_not_called()

    def test_tls_pooler_compatibility_and_closed_transaction_on_error(self):
        store = PostgresReviewStore('postgresql://example/db?sslmode=verify-full')
        call = self.driver.connect.call_args
        self.assertEqual(call.kwargs['sslmode'], 'verify-full')
        self.assertIsNone(call.kwargs['prepare_threshold'])
        with self.assertRaisesRegex(OSError, '^Persistent database operation failed') as error:
            with store.connect():
                raise DatabaseFailure('secret password and private review details')
        self.assertNotIn('secret', str(error.exception))
        self.assertTrue(self.connections[-1].closed)
        self.assertTrue(self.connections[-1].rolled_back)
        self.assertTrue(self.connections[0].closed)

    def test_bound_values_remain_parameters_and_event_order_is_stable(self):
        store = PostgresReviewStore('postgresql://example/db')
        value = "reviewer'; DROP TABLE events; --"
        with store.connect() as con:
            con.execute('SELECT payload FROM events WHERE reviewer_id=? ORDER BY rowid', (value,))
        sql, params = self.connections[-1].execute.call_args.args
        self.assertEqual(sql, 'SELECT payload FROM events WHERE reviewer_id=%s ORDER BY event_seq')
        self.assertEqual(params, (value,))
        self.assertNotIn(value, sql)


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL for isolated PostgreSQL integration checks')
class PostgresIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.database_url = os.environ['TEST_DATABASE_URL']
        self.schema = 'intelliaudit_test_' + uuid.uuid4().hex
        self.store = PostgresReviewStore(self.database_url, schema=self.schema)
        self.entries = [{'id': 'case_a', 'company': 'Example'}, {'id': 'case_b', 'company': 'Example'}]
        self.store.register_protocol('pilot', 'fixed-fingerprint', self.entries)
        self.scope = {'dataset': 'pilot', 'fingerprint': 'fixed-fingerprint', 'reviewer_id': 'accountant_a'}

    def tearDown(self):
        # This unique schema belongs only to this test; production schema is untouched.
        with self.store.connect() as con:
            con.execute(f'DROP SCHEMA "{self.schema}" CASCADE')

    def test_restart_preserves_frozen_plan_order_and_reviewer_isolation(self):
        first = self.store.append({**self.scope, 'case_id': 'case_a'}, 'blind', 'A', 'CPA', {'reasoning': 'First decision'})
        second = self.store.append({**self.scope, 'case_id': 'case_b'}, 'blind', 'A', 'CPA', {'reasoning': 'Second decision'})
        restarted = PostgresReviewStore(self.database_url, schema=self.schema)
        restarted.register_protocol('pilot', 'fixed-fingerprint', self.entries)
        self.assertEqual(restarted.history(self.scope)['events'], [first, second])
        self.assertEqual(restarted.protocol(self.scope)['phase'], 'reconciliation')
        self.assertEqual(restarted.history({**self.scope, 'reviewer_id': 'accountant_b'})['events'], [])
        for sql in ("UPDATE events SET stage='reveal'", 'DELETE FROM events', 'TRUNCATE events'):
            with self.subTest(sql=sql), self.assertRaises(OSError):
                with restarted.connect() as con:
                    con.execute(sql)
        self.assertEqual(restarted.history(self.scope)['events'], [first, second])

    def test_rollback_and_cross_instance_duplicate_submission(self):
        with self.assertRaisesRegex(ValueError, 'abort test transaction'):
            with self.store.connect() as con:
                event = self.store._event({**self.scope, 'case_id': 'case_a'}, 'blind', 'A', 'CPA', None)
                self.store._insert(con, event)
                raise ValueError('abort test transaction')
        self.assertEqual(self.store.history(self.scope)['events'], [])
        second_store = PostgresReviewStore(self.database_url, schema=self.schema)
        second_store.register_protocol('pilot', 'fixed-fingerprint', self.entries)
        outcomes = []

        def submit(store):
            try:
                store.append({**self.scope, 'case_id': 'case_a'}, 'blind', 'A', 'CPA', None)
                outcomes.append('saved')
            except ValueError:
                outcomes.append('duplicate')

        threads = [threading.Thread(target=submit, args=(store,)) for store in (self.store, second_store)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=45)
            self.assertFalse(thread.is_alive(), 'Database mutation did not finish')
        self.assertCountEqual(outcomes, ['saved', 'duplicate'])
        self.assertEqual(len(self.store.history(self.scope)['events']), 1)

    def test_accounts_and_resolution_immutability_survive_restart(self):
        code = 'isolated-test-curator-access-code-2026'
        auth = AuthStore(self.store.connect, code)
        invitation = auth.invite('Synthetic accountant', 'Test fixture only')
        token, _ = auth.login(invitation['invite_code'], '127.0.0.1')
        restarted = AuthStore(self.store.connect, code)
        self.assertEqual(restarted.session(token)['reviewer']['id'], invitation['reviewer']['id'])
        scope = {**self.scope, 'case_id': 'case_a'}
        record = auth.resolve(scope, 'curator', {}, 'Synthetic resolution only', ['test-source-id'])
        self.assertEqual(restarted.resolutions(scope), [record])
        for statement in ('DELETE FROM review_adjudications', 'TRUNCATE review_adjudications'):
            with self.assertRaises(OSError):
                with self.store.connect() as con:
                    con.execute(statement)
        restarted.revoke(invitation['reviewer']['id'])
        self.assertIsNone(auth.session(token))

    def test_full_delayed_repeat_protocol_on_postgresql(self):
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        self.store.clock = lambda: now
        entries = [{'id': f'full_case_{i}', 'company': f'Company {i // 4}'} for i in range(20)]
        self.store.register_protocol('full-pilot', 'fixed-full-fingerprint', entries)
        scope = {'dataset': 'full-pilot', 'fingerprint': 'fixed-full-fingerprint', 'reviewer_id': 'test-a'}
        annotation = {'judgement': 'insufficient_evidence', 'error_type': None, 'rows': [], 'evidence_sufficiency': 'insufficient', 'authority_disposition': 'unresolved', 'citations': [], 'authority_currency': 'unresolved', 'authority_source': '', 'proof_sets': [], 'reasoning': 'Synthetic database check only', 'confidence': 'low'}
        detail = lambda case_id: {'exam': {'exam_id': case_id, 'statement_text': '[row 0]: Revenue | $500'}, 'evidence_units': []}
        for case in entries:
            self.store.append({**scope, 'case_id': case['id']}, 'blind', 'Test A', 'Test fixture', annotation)
        self.assertEqual(self.store.protocol(scope)['phase'], 'waiting')
        with self.assertRaises(ValueError):
            self.store.append({**scope, 'case_id': entries[0]['id']}, 'reveal')
        now += timedelta(days=7)
        repeats = self.store.protocol(scope)['repeat_cases']
        self.assertEqual(len(repeats), 3)
        for case in repeats:
            self.store.append_repeat(scope, case['id'], 'Test A', 'Test fixture', annotation, detail)
        self.assertEqual(self.store.protocol(scope)['phase'], 'reconciliation')
        self.store.append({**scope, 'case_id': entries[0]['id']}, 'reveal')
        self.assertEqual(len(self.store.history(scope)['events']), 24)


if __name__ == '__main__':
    unittest.main()
