"""Invitation accounts, revocable sessions and curator resolutions.

Access codes and session cookies are random credentials; only SHA-256 digests
are stored. The connection factory can be local SQLite or hosted PostgreSQL.
"""
import hashlib
import json
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone

from .review_store import nonempty

SESSION_SECONDS = 8 * 60 * 60


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class AuthStore:
    def __init__(self, connect, admin_code, clock=time.time):
        if not isinstance(admin_code, str) or len(admin_code) < 32:
            raise ValueError('ADMIN_ACCESS_CODE must contain at least 32 characters')
        self.connect, self.clock = connect, clock
        self.lock = threading.RLock()
        with self.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS review_accounts (id TEXT PRIMARY KEY, name TEXT NOT NULL, qualification TEXT NOT NULL, role TEXT NOT NULL, code_hash TEXT NOT NULL UNIQUE, active INTEGER NOT NULL, created_at TEXT NOT NULL)')
            con.execute('CREATE TABLE IF NOT EXISTS review_sessions (token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL, csrf_token TEXT NOT NULL, expires_at INTEGER NOT NULL)')
            con.execute('CREATE TABLE IF NOT EXISTS review_login_attempts (client_hash TEXT PRIMARY KEY, window_start INTEGER NOT NULL, attempts INTEGER NOT NULL)')
            con.execute('CREATE TABLE IF NOT EXISTS review_adjudications (id TEXT PRIMARY KEY, dataset TEXT NOT NULL, fingerprint TEXT NOT NULL, case_id TEXT NOT NULL, curator_id TEXT NOT NULL, payload TEXT NOT NULL)')
            if isinstance(con, sqlite3.Connection):
                con.execute("CREATE TRIGGER IF NOT EXISTS immutable_resolution_update BEFORE UPDATE ON review_adjudications BEGIN SELECT RAISE(ABORT,'Resolutions are immutable'); END")
                con.execute("CREATE TRIGGER IF NOT EXISTS immutable_resolution_delete BEFORE DELETE ON review_adjudications BEGIN SELECT RAISE(ABORT,'Resolutions are immutable'); END")
            else:
                # The PostgreSQL store initializes this trigger function in the
                # same private schema before account tables are created.
                for action in ('update', 'delete', 'truncate'):
                    con.execute(f'DROP TRIGGER IF EXISTS immutable_resolution_{action} ON review_adjudications')
                    kind = 'STATEMENT' if action == 'truncate' else 'ROW'
                    con.execute(f'CREATE TRIGGER immutable_resolution_{action} BEFORE {action.upper()} ON review_adjudications FOR EACH {kind} EXECUTE FUNCTION immutable_event()')
                for table in ('review_accounts', 'review_sessions', 'review_login_attempts', 'review_adjudications'):
                    con.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
            existing = con.execute('SELECT code_hash FROM review_accounts WHERE id=?', ('curator',)).fetchone()
            hashed = digest(admin_code)
            if existing:
                if not secrets.compare_digest(existing[0], hashed):
                    con.execute('UPDATE review_accounts SET code_hash=? WHERE id=?', (hashed, 'curator'))
                    con.execute('DELETE FROM review_sessions WHERE account_id=?', ('curator',))
            else:
                con.execute('INSERT INTO review_accounts (id,name,qualification,role,code_hash,active,created_at) VALUES (?,?,?,?,?,?,?)', ('curator', 'Review curator', 'Study coordinator', 'curator', hashed, 1, self.now()))

    def now(self):
        return datetime.fromtimestamp(self.clock(), timezone.utc).isoformat()

    @staticmethod
    def account(row):
        return {'id': row[0], 'name': row[1], 'qualification': row[2], 'role': row[3], 'active': bool(row[4])}

    def reviewers(self):
        with self.connect() as con:
            rows = con.execute('SELECT id,name,qualification,role,active FROM review_accounts ORDER BY created_at,id').fetchall()
        return [self.account(row) for row in rows]

    def invite(self, name, qualification):
        name = nonempty(name, 'name', 300)
        qualification = nonempty(qualification, 'qualification', 2000)
        code = secrets.token_urlsafe(32)
        account_id = 'reviewer_' + uuid.uuid4().hex
        with self.lock, self.connect() as con:
            con.execute('INSERT INTO review_accounts (id,name,qualification,role,code_hash,active,created_at) VALUES (?,?,?,?,?,?,?)', (account_id, name, qualification, 'reviewer', digest(code), 1, self.now()))
        return {'reviewer': {'id': account_id, 'name': name, 'qualification': qualification, 'role': 'reviewer', 'active': True}, 'invite_code': code}

    def login(self, code, client):
        code = nonempty(code, 'invite_code', 200)
        current = int(self.clock())
        client_hash = digest(client)
        # Rate limiting is persisted, so restarts cannot reset the attempt budget.
        with self.lock, self.connect() as con:
            attempt = con.execute('SELECT window_start,attempts FROM review_login_attempts WHERE client_hash=?', (client_hash,)).fetchone()
            start, count = attempt if attempt and current - attempt[0] < 900 else (current, 0)
            if count >= 15:
                raise PermissionError('Too many login attempts. Try again in 15 minutes.')
            con.execute('INSERT INTO review_login_attempts (client_hash,window_start,attempts) VALUES (?,?,?) ON CONFLICT (client_hash) DO UPDATE SET window_start=excluded.window_start, attempts=excluded.attempts', (client_hash, start, count + 1))
            row = con.execute('SELECT id,name,qualification,role,active FROM review_accounts WHERE code_hash=? AND active=1', (digest(code),)).fetchone()
        if not row:
            raise PermissionError('Invalid or revoked access code')
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.lock, self.connect() as con:
            con.execute('DELETE FROM review_sessions WHERE expires_at<=?', (current,))
            con.execute('INSERT INTO review_sessions (token_hash,account_id,csrf_token,expires_at) VALUES (?,?,?,?)', (digest(token), row[0], csrf, current + SESSION_SECONDS))
            con.execute('DELETE FROM review_login_attempts WHERE client_hash=?', (client_hash,))
        return token, {'reviewer': self.account(row), 'csrf_token': csrf}

    def session(self, token):
        if not isinstance(token, str) or len(token) > 200 or not token:
            return None
        with self.connect() as con:
            row = con.execute('SELECT a.id,a.name,a.qualification,a.role,a.active,s.csrf_token FROM review_sessions s JOIN review_accounts a ON a.id=s.account_id WHERE s.token_hash=? AND s.expires_at>? AND a.active=1', (digest(token), int(self.clock()))).fetchone()
        return None if row is None else {'reviewer': self.account(row[:5]), 'csrf_token': row[5]}

    def logout(self, token):
        with self.lock, self.connect() as con:
            con.execute('DELETE FROM review_sessions WHERE token_hash=?', (digest(token),))

    def revoke(self, account_id):
        if account_id == 'curator':
            raise ValueError('Rotate the curator code through the hosting secret settings')
        with self.lock, self.connect() as con:
            updated = con.execute('UPDATE review_accounts SET active=0 WHERE id=?', (account_id,))
            if updated.rowcount != 1:
                raise ValueError('Unknown reviewer')
            con.execute('DELETE FROM review_sessions WHERE account_id=?', (account_id,))

    def resolutions(self, scope):
        with self.connect() as con:
            rows = con.execute('SELECT payload FROM review_adjudications WHERE dataset=? AND fingerprint=?', (scope['dataset'], scope['fingerprint'])).fetchall()
        return sorted([json.loads(row[0]) for row in rows], key=lambda item: (item['created_at'], item['id']))

    def resolve(self, scope, curator_id, annotation, reason, source_events):
        reason = nonempty(reason, 'reason', 20000)
        if not source_events:
            raise ValueError('At least one initial accountant assessment is required')
        record = {**scope, 'id': str(uuid.uuid4()), 'curator_id': curator_id, 'created_at': self.now(), 'annotation': annotation, 'reason': reason, 'source_event_ids': sorted(source_events), 'status': 'curator_resolution_not_publication_gold'}
        with self.lock, self.connect() as con:
            con.execute('INSERT INTO review_adjudications (id,dataset,fingerprint,case_id,curator_id,payload) VALUES (?,?,?,?,?,?)', (record['id'], scope['dataset'], scope['fingerprint'], scope['case_id'], curator_id, json.dumps(record, ensure_ascii=False, sort_keys=True)))
        return record
