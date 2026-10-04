"""Append-only local review records. Reviewer IDs separate work; they are not authentication."""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1

def nonempty(value, name, limit=20000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"Invalid {name}")
    return value.strip()


def validate_annotation(annotation, detail, stage):
    required = {'judgement', 'error_type', 'rows', 'evidence_sufficiency', 'authority_disposition',
                'citations', 'authority_currency', 'authority_source', 'proof_sets', 'reasoning', 'confidence'}
    optional = {'evidence_quotes'} | ({'disposition'} if stage == 'verification' else set())
    if not isinstance(annotation, dict) or not required <= annotation.keys() or annotation.keys() - required - optional:
        raise ValueError('Annotation fields are missing or unknown')
    choices = {
        'judgement': {'correct', 'incorrect', 'insufficient_evidence', 'ambiguous'},
        'evidence_sufficiency': {'sufficient', 'insufficient', 'uncertain'},
        'authority_disposition': {'governing_paragraph', 'no_governing_paragraph', 'insufficient_evidence', 'unresolved'},
        'authority_currency': {'verified', 'unresolved', 'not_applicable'},
        'confidence': {'high', 'medium', 'low'},
    }
    if stage == 'verification':
        choices['disposition'] = {'agree', 'revise', 'unresolved', 'exclude'}
    for field, options in choices.items():
        if not isinstance(annotation.get(field), str) or annotation[field] not in options:
            raise ValueError(f'Invalid {field}')
    if annotation['error_type'] is not None:
        nonempty(annotation['error_type'], 'error_type', 200)
    rows = annotation['rows']
    if not isinstance(rows, list) or len(rows) > 100 or any(type(r) is not int or r < 0 for r in rows) or len(set(rows)) != len(rows):
        raise ValueError('Rows must be distinct nonnegative integer labels')
    # Only explicit statement row labels are valid; no assumptions about row numbering.
    import re
    row_labels = {int(r) for r in re.findall(r'\[row\s+(\d+)\]', detail['exam']['statement_text'], re.I)}
    if not set(rows) <= row_labels:
        raise ValueError('Unknown statement row')
    citations = annotation['citations']
    if not isinstance(citations, list) or len(citations) > 30:
        raise ValueError('Invalid citations')
    for citation in citations:
        nonempty(citation, 'citation', 300)
    if annotation['authority_disposition'] == 'governing_paragraph' and not citations:
        raise ValueError('Governing paragraph requires a citation')
    if not isinstance(annotation['authority_source'], str) or len(annotation['authority_source']) > 10000:
        raise ValueError('Invalid authority_source')
    if annotation['authority_currency'] == 'verified' and not annotation['authority_source'].strip():
        raise ValueError('Verified authority requires source and effective-date rationale')
    nonempty(annotation['reasoning'], 'reasoning')
    units = {u['id']: u['text'] for u in detail['evidence_units']}
    proofs = annotation['proof_sets']
    if not isinstance(proofs, list) or len(proofs) > 50:
        raise ValueError('Invalid proof_sets')
    for proof in proofs:
        if not isinstance(proof, list) or not proof or any(not isinstance(p, str) or p not in units for p in proof) or len(set(proof)) != len(proof):
            raise ValueError('Unknown or duplicate evidence unit in proof')
    quotes = annotation.get('evidence_quotes', [])
    if not isinstance(quotes, list) or len(quotes) > 100:
        raise ValueError('Invalid evidence_quotes')
    for quote in quotes:
        if not isinstance(quote, dict) or set(quote) != {'unit_id', 'quote'} or quote['unit_id'] not in units:
            raise ValueError('Invalid quote unit')
        nonempty(quote['quote'], 'quote')
        if quote['quote'] not in units[quote['unit_id']]:
            raise ValueError('Quote is not present verbatim in evidence')
    return annotation


class ReviewStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, dataset TEXT NOT NULL, case_id TEXT NOT NULL, reviewer_id TEXT NOT NULL, stage TEXT NOT NULL, payload TEXT NOT NULL)')
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_blind ON events(fingerprint, dataset, case_id, reviewer_id) WHERE stage='blind'")
            con.execute("CREATE TRIGGER IF NOT EXISTS immutable_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'Events are immutable'); END")
            con.execute("CREATE TRIGGER IF NOT EXISTS immutable_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'Events are immutable'); END")

    def connect(self):
        return sqlite3.connect(self.path)

    @staticmethod
    def identity(dataset, fingerprint, case_id, reviewer_id):
        return {'dataset': dataset, 'fingerprint': fingerprint, 'case_id': nonempty(case_id, 'case_id', 200), 'reviewer_id': nonempty(reviewer_id, 'reviewer_id', 200)}

    def history(self, scope):
        with self.connect() as con:
            rows = con.execute('SELECT payload FROM events WHERE dataset=? AND fingerprint=? AND reviewer_id=?' + (' AND case_id=?' if 'case_id' in scope else '') + ' ORDER BY rowid', tuple(scope[k] for k in ('dataset', 'fingerprint', 'reviewer_id')) + ((scope['case_id'],) if 'case_id' in scope else ())).fetchall()
        return {'schema_version': SCHEMA, 'scope': scope, 'events': [json.loads(r[0]) for r in rows]}

    @staticmethod
    def _insert(con, event):
        old = con.execute('SELECT payload FROM events WHERE event_id=?', (event['event_id'],)).fetchone()
        encoded = json.dumps(event, sort_keys=True, ensure_ascii=False)
        if old:
            if json.loads(old[0]) != event:
                raise ValueError('Conflicting immutable event ID')
            return False
        ident = tuple(event[k] for k in ('fingerprint', 'dataset', 'case_id', 'reviewer_id'))
        stages = {r[0] for r in con.execute('SELECT stage FROM events WHERE fingerprint=? AND dataset=? AND case_id=? AND reviewer_id=?', ident)}
        if event['stage'] == 'blind' and ('blind' in stages or 'reveal' in stages):
            raise ValueError('Blind submission is immutable; use verification for revisions')
        if event['stage'] == 'reveal' and 'blind' not in stages:
            raise ValueError('Submit a blind review before revealing the proposal')
        if event['stage'] == 'verification' and 'reveal' not in stages:
            raise ValueError('Reveal the proposal before verification')
        con.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?)', (event['event_id'], event['fingerprint'], event['dataset'], event['case_id'], event['reviewer_id'], event['stage'], encoded))
        return True

    def append(self, scope, stage, reviewer_name='', qualification='', annotation=None):
        if stage not in {'blind', 'verification', 'reveal'}:
            raise ValueError('Unknown review stage')
        event = {**scope, 'event_id': str(uuid.uuid4()), 'schema_version': SCHEMA,
                 'created_at': datetime.now(timezone.utc).isoformat(), 'stage': stage,
                 'reviewer_name': reviewer_name, 'qualification': qualification, 'annotation': annotation}
        with self.lock, self.connect() as con:
            self._insert(con, event)
        return event

    def import_events(self, envelope, dataset, detail_fn):
        if not isinstance(envelope, dict) or set(envelope) != {'schema_version', 'scope', 'events'} or type(envelope['schema_version']) is not int or envelope['schema_version'] != SCHEMA:
            raise ValueError('Unsupported or stale export schema')
        scope = envelope['scope']
        if not isinstance(scope, dict) or set(scope) != {'dataset', 'fingerprint', 'reviewer_id'} or scope['fingerprint'] != dataset.fingerprint:
            raise ValueError('Dataset fingerprint or export scope mismatch')
        nonempty(scope['reviewer_id'], 'reviewer_id', 200)
        events = envelope['events']
        if not isinstance(events, list) or len(events) > 10000:
            raise ValueError('Invalid event collection')
        fields = {'dataset', 'fingerprint', 'case_id', 'reviewer_id', 'event_id', 'schema_version', 'created_at', 'stage', 'reviewer_name', 'qualification', 'annotation'}
        count = 0
        with self.lock, self.connect() as con:
            for event in events:
                if not isinstance(event, dict) or set(event) != fields or type(event['schema_version']) is not int or event['schema_version'] != SCHEMA or any(event[k] != scope[k] for k in scope):
                    raise ValueError('Event identity or schema mismatch')
                nonempty(event['event_id'], 'event_id', 200)
                nonempty(event['created_at'], 'created_at', 100)
                try:
                    datetime.fromisoformat(event['created_at'])
                except ValueError:
                    raise ValueError('Invalid event timestamp') from None
                detail = detail_fn(event['case_id'])
                if event['stage'] in {'blind', 'verification'}:
                    nonempty(event['reviewer_name'], 'reviewer_name', 300)
                    nonempty(event['qualification'], 'qualification', 2000)
                    validate_annotation(event['annotation'], detail, event['stage'])
                elif event['stage'] != 'reveal' or event['annotation'] is not None:
                    raise ValueError('Invalid event stage')
                count += self._insert(con, event)
        return {'imported': count, 'unchanged': len(events) - count}
