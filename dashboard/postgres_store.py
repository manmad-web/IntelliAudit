"""Durable review storage for a small hosted pilot.

The PostgreSQL driver is optional: local SQLite use remains standard-library-only.
All application tables live in a private schema, outside Supabase's public API.
"""
import hashlib
import importlib
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

try:
    from .review_store import ReviewStore
except ImportError:
    from review_store import ReviewStore


class _Connection:
    """Translate the shared store's fixed SQL, never user-provided SQL."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=None):
        query = re.sub(r'\browid\b', 'event_seq', query, flags=re.I).replace('?', '%s')
        return self.connection.execute(query, params)


class PostgresReviewStore(ReviewStore):
    def __init__(self, database_url, clock=None, schema='intelliaudit'):
        if not isinstance(database_url, str) or not database_url:
            raise ValueError('DATABASE_URL is required for hosted review storage')
        try:
            url = urlsplit(database_url)
            valid = url.scheme in {'postgres', 'postgresql'} and bool(url.hostname) and bool(url.path.strip('/'))
            # Parse the port here so malformed URLs fail without leaking a secret.
            url.port
        except ValueError:
            valid = False
        if not valid:
            raise ValueError('DATABASE_URL must be a PostgreSQL connection URL')
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema) or schema in {'public', 'pg_catalog', 'information_schema'}:
            raise ValueError('Use a distinct private PostgreSQL schema')
        sslmodes = parse_qs(url.query).get('sslmode', ['require'])
        if len(sslmodes) != 1 or sslmodes[0] not in {'require', 'verify-ca', 'verify-full'}:
            raise ValueError('Hosted database connections must require TLS')
        try:
            self.driver = importlib.import_module('psycopg')
        except ImportError:
            raise RuntimeError('Install requirements-hosted.txt for PostgreSQL storage') from None
        self.database_url = database_url
        self.sslmode = sslmodes[0]
        self.schema = schema
        self.lock = threading.RLock()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.protocol_cases = {}
        self.advisory_key = int.from_bytes(hashlib.sha256(('IntelliAudit:' + schema).encode()).digest()[:8], 'big', signed=True)
        with self._transaction(initializing=True) as con:
            con.execute('CREATE TABLE IF NOT EXISTS events ('
                        'event_seq BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE, '
                        'event_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, dataset TEXT NOT NULL, '
                        'case_id TEXT NOT NULL, reviewer_id TEXT NOT NULL, stage TEXT NOT NULL, payload TEXT NOT NULL)')
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_blind ON events(fingerprint,dataset,case_id,reviewer_id) WHERE stage='blind'")
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_repeat ON events(fingerprint,dataset,case_id,reviewer_id) WHERE stage='repeat'")
            con.execute('CREATE TABLE IF NOT EXISTS protocol_plans (dataset TEXT NOT NULL, fingerprint TEXT NOT NULL, '
                        'reviewer_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(dataset,fingerprint,reviewer_id))')
            con.execute('CREATE OR REPLACE FUNCTION immutable_event() RETURNS trigger '
                        "LANGUAGE plpgsql SET search_path = pg_catalog AS $$ BEGIN RAISE EXCEPTION 'Events are immutable'; END; $$")
            con.execute('DROP TRIGGER IF EXISTS immutable_update ON events')
            con.execute('DROP TRIGGER IF EXISTS immutable_delete ON events')
            con.execute('DROP TRIGGER IF EXISTS immutable_truncate ON events')
            con.execute('CREATE TRIGGER immutable_update BEFORE UPDATE ON events FOR EACH ROW EXECUTE FUNCTION immutable_event()')
            con.execute('CREATE TRIGGER immutable_delete BEFORE DELETE ON events FOR EACH ROW EXECUTE FUNCTION immutable_event()')
            con.execute('CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON events FOR EACH STATEMENT EXECUTE FUNCTION immutable_event()')
            con.execute('ALTER TABLE events ENABLE ROW LEVEL SECURITY')
            con.execute('ALTER TABLE protocol_plans ENABLE ROW LEVEL SECURITY')

    @contextmanager
    def _transaction(self, initializing=False):
        try:
            # Disable prepared statements for transaction-pooler compatibility.
            # psycopg's context manager commits/rolls back AND closes the connection.
            with self.driver.connect(self.database_url, connect_timeout=10,
                                     sslmode=self.sslmode, prepare_threshold=None) as raw:
                raw.execute("SET LOCAL statement_timeout = '30s'")
                raw.execute("SET LOCAL lock_timeout = '30s'")
                # A transaction-scoped DB lock also protects frozen plans and stage
                # transitions across different server processes, not only threads.
                raw.execute('SELECT pg_advisory_xact_lock(%s)', (self.advisory_key,))
                if initializing:
                    raw.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
                    raw.execute(f'REVOKE ALL ON SCHEMA "{self.schema}" FROM PUBLIC')
                raw.execute(f'SET LOCAL search_path TO "{self.schema}", pg_catalog')
                yield _Connection(raw)
        except self.driver.Error:
            # SQL diagnostics can contain submitted personal data. Keep them out
            # of HTTP responses and ordinary deployment logs.
            raise OSError('Persistent database operation failed; try again shortly') from None

    @contextmanager
    def connect(self):
        with self._transaction() as con:
            yield con
