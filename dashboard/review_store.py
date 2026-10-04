"""Append-only local review records. Reviewer IDs separate work; they are not authentication."""
import json
import copy
import math
import random
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
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
    def __init__(self, path, clock=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.protocol_cases = {}
        with self.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, dataset TEXT NOT NULL, case_id TEXT NOT NULL, reviewer_id TEXT NOT NULL, stage TEXT NOT NULL, payload TEXT NOT NULL)')
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_blind ON events(fingerprint, dataset, case_id, reviewer_id) WHERE stage='blind'")
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_repeat ON events(fingerprint, dataset, case_id, reviewer_id) WHERE stage='repeat'")
            con.execute('CREATE TABLE IF NOT EXISTS protocol_plans (dataset TEXT NOT NULL, fingerprint TEXT NOT NULL, reviewer_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(dataset, fingerprint, reviewer_id))')
            con.execute("CREATE TRIGGER IF NOT EXISTS immutable_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'Events are immutable'); END")
            con.execute("CREATE TRIGGER IF NOT EXISTS immutable_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'Events are immutable'); END")

    @contextmanager
    def connect(self):
        # sqlite3's transaction context manager does not close its connection.
        con = sqlite3.connect(self.path, timeout=30)
        try:
            with con:
                yield con
        finally:
            con.close()

    def register_protocol(self, dataset, fingerprint, entries):
        """Register the complete immutable corpus; called before any review routes."""
        cases = {entry['id']: {k: entry[k] for k in ('company', 'fiscal_year', 'statement_type') if k in entry}
                 for entry in entries}
        if not cases or len(cases) != len(entries):
            raise ValueError('Protocol requires distinct case IDs')
        with self.lock:
            existing = self.protocol_cases.get((dataset, fingerprint))
            if existing is not None and existing != cases:
                raise ValueError('Protocol corpus changed without a new fingerprint')
            self.protocol_cases[(dataset, fingerprint)] = cases

    @staticmethod
    def _key(scope):
        return tuple(scope[k] for k in ('dataset', 'fingerprint', 'reviewer_id'))

    def _plan(self, con, scope):
        key = self._key(scope)
        cases = self.protocol_cases.get(key[:2])
        if cases is None:
            raise ValueError('Review protocol is not registered')
        row = con.execute('SELECT payload FROM protocol_plans WHERE dataset=? AND fingerprint=? AND reviewer_id=?', key).fetchone()
        if row:
            plan = json.loads(row[0])
            if set(plan['case_ids']) != set(cases):
                raise ValueError('Frozen protocol corpus mismatch')
            return plan
        # Round 15% to the nearest case (half up). A twenty-case pilot repeats three.
        # Tiny development fixtures may round to zero; this is disclosed in status.
        count = math.floor(len(cases) * .15 + .5)
        rng = random.SystemRandom()
        strata = {}
        for case_id, meta in cases.items():
            strata.setdefault(meta.get('company', ''), []).append(case_id)
        groups = list(strata.values())
        rng.shuffle(groups)
        for group in groups:
            rng.shuffle(group)
        chosen = []
        while len(chosen) < count:
            for group in groups:
                if group and len(chosen) < count:
                    chosen.append(group.pop())
        rng.shuffle(chosen)
        plan = {'version': 1, 'case_ids': sorted(cases), 'delay_days': 7,
                'rounding': '15% rounded to nearest integer, half up; public company strata',
                'repeats': [{'alias': 'repeat_' + secrets.token_hex(12), 'case_id': case_id} for case_id in chosen]}
        con.execute('INSERT INTO protocol_plans VALUES (?,?,?,?)', (*key, json.dumps(plan, sort_keys=True)))
        return plan

    def _protocol(self, con, scope):
        plan = self._plan(con, scope)
        rows = con.execute('SELECT payload FROM events WHERE dataset=? AND fingerprint=? AND reviewer_id=? ORDER BY rowid', self._key(scope)).fetchall()
        events = [json.loads(row[0]) for row in rows]
        initial = {event['case_id']: event for event in events if event['stage'] == 'blind' and event['case_id'] in plan['case_ids']}
        repeats = {event['case_id'] for event in events if event['stage'] == 'repeat'}
        complete = len(initial) == len(plan['case_ids'])
        eligible = None
        if complete and plan['repeats']:
            eligible = max(datetime.fromisoformat(event['created_at']) for event in initial.values()) + timedelta(days=plan['delay_days'])
        pending = [repeat for repeat in plan['repeats'] if repeat['case_id'] not in repeats]
        phase = ('initial' if not complete else 'waiting' if pending and self.clock() < eligible
                 else 'repeat' if pending else 'reconciliation')
        cases = self.protocol_cases[(scope['dataset'], scope['fingerprint'])]
        return {'phase': phase, 'initial_completed': len(initial), 'initial_total': len(plan['case_ids']),
                'repeat_required': len(plan['repeats']), 'repeat_completed': len(plan['repeats']) - len(pending),
                'repeat_ready_at': eligible.isoformat() if eligible else None, 'delay_days': plan['delay_days'],
                'repeat_fraction': len(plan['repeats']) / len(plan['case_ids']), 'rounding': plan['rounding'],
                'repeat_cases': [{'id': repeat['alias'], **cases[repeat['case_id']]} for repeat in pending] if phase == 'repeat' else []}

    def protocol(self, scope):
        with self.lock, self.connect() as con:
            return self._protocol(con, scope)

    def _repeat_target(self, con, scope, alias):
        if self._protocol(con, scope)['phase'] != 'repeat':
            raise ValueError('Delayed repeat review is not currently open')
        plan = self._plan(con, scope)
        for repeat in plan['repeats']:
            if repeat['alias'] == alias:
                return repeat['case_id']
        raise ValueError('Unknown repeat alias')

    def repeat_detail(self, scope, alias, detail_fn):
        with self.lock, self.connect() as con:
            case_id = self._repeat_target(con, scope, alias)
        detail = copy.deepcopy(detail_fn(case_id))
        detail['exam']['exam_id'] = alias
        return detail

    def append_repeat(self, scope, alias, reviewer_name, qualification, annotation, detail_fn):
        with self.lock, self.connect() as con:
            case_id = self._repeat_target(con, scope, alias)
            validate_annotation(annotation, detail_fn(case_id), 'repeat')
            event = self._event({**scope, 'case_id': case_id}, 'repeat', reviewer_name, qualification, annotation)
            event['repeat_alias'] = alias
            self._insert(con, event)
        # Never send the canonical case ID or the first assessment during a repeat.
        return {**event, 'case_id': alias}

    @staticmethod
    def identity(dataset, fingerprint, case_id, reviewer_id):
        return {'dataset': dataset, 'fingerprint': fingerprint, 'case_id': nonempty(case_id, 'case_id', 200), 'reviewer_id': nonempty(reviewer_id, 'reviewer_id', 200)}

    def history(self, scope, *, allow_during_repeat=False):
        with self.lock, self.connect() as con:
            protocol = self._protocol(con, scope)
            if protocol['phase'] == 'repeat' and not allow_during_repeat:
                raise PermissionError('Prior assessments are hidden while delayed repeat review is open')
            rows = con.execute('SELECT payload FROM events WHERE dataset=? AND fingerprint=? AND reviewer_id=?' + (' AND case_id=?' if 'case_id' in scope else '') + ' ORDER BY rowid', tuple(scope[k] for k in ('dataset', 'fingerprint', 'reviewer_id')) + ((scope['case_id'],) if 'case_id' in scope else ())).fetchall()
            envelope = {'schema_version': SCHEMA, 'scope': scope, 'events': [json.loads(r[0]) for r in rows]}
            if 'case_id' not in scope and protocol['phase'] == 'reconciliation':
                envelope['protocol_plan'] = self._plan(con, scope)
        return envelope

    def _insert(self, con, event):
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
        plan = self._plan(con, event)
        if event['case_id'] not in plan['case_ids']:
            raise ValueError('Case is not in the frozen review corpus')
        if event['stage'] == 'repeat':
            if 'repeat' in stages:
                raise ValueError('Repeat submission is immutable')
            target = self._repeat_target(con, event, event.get('repeat_alias'))
            if target != event['case_id']:
                raise ValueError('Repeat alias does not match the frozen protocol')
            ready_at = datetime.fromisoformat(self._protocol(con, event)['repeat_ready_at'])
            if datetime.fromisoformat(event['created_at']) < ready_at:
                raise ValueError('Repeat timestamp predates the seven-day delay')
        if event['stage'] in {'reveal', 'verification'} and self._protocol(con, event)['phase'] != 'reconciliation':
            raise ValueError('Complete every initial review and the delayed repeat subset before revealing proposals')
        if event['stage'] == 'reveal' and 'blind' not in stages:
            raise ValueError('Submit a blind review before revealing the proposal')
        if event['stage'] == 'verification' and 'reveal' not in stages:
            raise ValueError('Reveal the proposal before verification')
        con.execute('INSERT INTO events(event_id,fingerprint,dataset,case_id,reviewer_id,stage,payload) VALUES (?,?,?,?,?,?,?)', (event['event_id'], event['fingerprint'], event['dataset'], event['case_id'], event['reviewer_id'], event['stage'], encoded))
        return True

    def _event(self, scope, stage, reviewer_name, qualification, annotation):
        return {**scope, 'event_id': str(uuid.uuid4()), 'schema_version': SCHEMA,
                 'created_at': self.clock().isoformat(), 'stage': stage,
                 'reviewer_name': reviewer_name, 'qualification': qualification, 'annotation': annotation}

    def append(self, scope, stage, reviewer_name='', qualification='', annotation=None):
        if stage not in {'blind', 'verification', 'reveal'}:
            raise ValueError('Unknown review stage')
        event = self._event(scope, stage, reviewer_name, qualification, annotation)
        with self.lock, self.connect() as con:
            self._insert(con, event)
        return event

    def import_events(self, envelope, dataset, detail_fn):
        if not isinstance(envelope, dict) or not {'schema_version', 'scope', 'events'} <= set(envelope) or set(envelope) - {'schema_version', 'scope', 'events', 'protocol_plan'} or type(envelope['schema_version']) is not int or envelope['schema_version'] != SCHEMA:
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
            if 'protocol_plan' in envelope:
                plan = envelope['protocol_plan']
                cases = self.protocol_cases.get((scope['dataset'], scope['fingerprint']), {})
                if not isinstance(plan, dict) or set(plan) != {'version', 'case_ids', 'delay_days', 'rounding', 'repeats'} or plan['version'] != 1 or plan['delay_days'] != 7 or set(plan['case_ids']) != set(cases) or len(plan['case_ids']) != len(cases):
                    raise ValueError('Invalid frozen protocol plan')
                repeats = plan['repeats']
                if not isinstance(repeats, list) or len(repeats) != math.floor(len(cases) * .15 + .5) or any(not isinstance(r, dict) or set(r) != {'alias', 'case_id'} or r['case_id'] not in cases or not isinstance(r['alias'], str) or not r['alias'].startswith('repeat_') or len(r['alias']) != 31 for r in repeats) or len({r['alias'] for r in repeats}) != len(repeats) or len({r['case_id'] for r in repeats}) != len(repeats):
                    raise ValueError('Invalid repeat subset')
                row = con.execute('SELECT payload FROM protocol_plans WHERE dataset=? AND fingerprint=? AND reviewer_id=?', self._key(scope)).fetchone()
                if row and json.loads(row[0]) != plan:
                    raise ValueError('Imported protocol conflicts with the already frozen repeat subset')
                if not row:
                    con.execute('INSERT INTO protocol_plans VALUES (?,?,?,?)', (*self._key(scope), json.dumps(plan, sort_keys=True)))
            for event in events:
                expected = fields | ({'repeat_alias'} if isinstance(event, dict) and event.get('stage') == 'repeat' else set())
                if not isinstance(event, dict) or set(event) != expected or type(event['schema_version']) is not int or event['schema_version'] != SCHEMA or any(event[k] != scope[k] for k in scope):
                    raise ValueError('Event identity or schema mismatch')
                nonempty(event['event_id'], 'event_id', 200)
                nonempty(event['created_at'], 'created_at', 100)
                try:
                    timestamp = datetime.fromisoformat(event['created_at'])
                    if timestamp.tzinfo is None or timestamp > self.clock():
                        raise ValueError('Timestamp must be timezone-aware and cannot be in the future')
                except ValueError:
                    raise ValueError('Invalid event timestamp') from None
                detail = detail_fn(event['case_id'])
                if event['stage'] in {'blind', 'repeat', 'verification'}:
                    nonempty(event['reviewer_name'], 'reviewer_name', 300)
                    nonempty(event['qualification'], 'qualification', 2000)
                    validate_annotation(event['annotation'], detail, event['stage'])
                elif event['stage'] != 'reveal' or event['annotation'] is not None:
                    raise ValueError('Invalid event stage')
                count += self._insert(con, event)
        return {'imported': count, 'unchanged': len(events) - count}
