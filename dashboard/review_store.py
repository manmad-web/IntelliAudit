"""Append-only local review records. Reviewer IDs separate work; they are not authentication."""
import json
import copy
import math
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCHEMA = 1
EXPORT_SCHEMA = 2
IMMEDIATE_PROTOCOL = 'immediate_reconciliation_v2'
LEGACY_PROTOCOL = 'delayed_repeat_v1'
IMMEDIATE_ROUNDING = 'No delayed repeats; reconciliation follows the complete initial pass'

def nonempty(value, name, limit=20000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"Invalid {name}")
    return value.strip()


def validate_annotation(annotation, detail, stage):
    required = {'judgement', 'error_type', 'rows', 'evidence_sufficiency', 'authority_disposition',
                'citations', 'authority_currency', 'authority_source', 'proof_sets', 'reasoning', 'confidence'}
    optional = {'evidence_quotes', 'supporting_evidence', 'missing_information',
                'case_quality_flags', 'case_quality_notes', 'alternative_treatments',
                'contradictions'} | ({'disposition'} if stage == 'verification' else set())
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
    supporting = annotation.get('supporting_evidence', [])
    if (not isinstance(supporting, list) or len(supporting) > 100
            or any(not isinstance(unit, str) or unit not in units for unit in supporting)
            or len(set(supporting)) != len(supporting)):
        raise ValueError('Supporting evidence must reference distinct supplied evidence units')
    for field in ('missing_information', 'case_quality_notes', 'alternative_treatments', 'contradictions'):
        value = annotation.get(field, '')
        if not isinstance(value, str) or len(value) > 10000:
            raise ValueError(f'Invalid {field}')
    quality_choices = {'statement_unclear', 'evidence_unclear', 'evidence_insufficient',
                       'evidence_contradictory', 'scenario_unrealistic', 'source_unclear', 'other'}
    quality_flags = annotation.get('case_quality_flags', [])
    if (not isinstance(quality_flags, list) or len(quality_flags) > len(quality_choices)
            or any(not isinstance(flag, str) or flag not in quality_choices for flag in quality_flags)
            or len(set(quality_flags)) != len(quality_flags)):
        raise ValueError('Invalid case quality flags')
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
            self._validate_plan(plan, cases)
            return plan
        # Plans are frozen per participant. Existing version-one plans keep their
        # original aliases and delay; only newly enrolled participants use v2.
        plan = {'version': 2, 'protocol_id': IMMEDIATE_PROTOCOL, 'case_ids': sorted(cases),
                'delay_days': 0, 'rounding': IMMEDIATE_ROUNDING, 'repeats': [],
                'reliability_status': 'reliability_not_measured'}
        con.execute('INSERT INTO protocol_plans VALUES (?,?,?,?)', (*key, json.dumps(plan, sort_keys=True)))
        return plan

    @staticmethod
    def _validate_plan(plan, cases):
        """Accept both frozen protocols without silently interpreting a new one."""
        common = {'version', 'case_ids', 'delay_days', 'rounding', 'repeats'}
        if not isinstance(plan, dict) or type(plan.get('version')) is not int or plan['version'] not in {1, 2}:
            raise ValueError('Unsupported frozen protocol version')
        expected = common if plan['version'] == 1 else common | {'protocol_id', 'reliability_status'}
        case_ids = plan.get('case_ids')
        if (not cases or set(plan) != expected or not isinstance(case_ids, list)
                or any(not isinstance(case_id, str) for case_id in case_ids)
                or len(case_ids) != len(cases) or set(case_ids) != set(cases)
                or type(plan.get('delay_days')) is not int
                or not isinstance(plan.get('rounding'), str) or not plan['rounding'].strip()
                or not isinstance(plan.get('repeats'), list)):
            raise ValueError('Invalid frozen protocol plan or corpus mismatch')
        if plan['version'] == 2:
            if (plan['protocol_id'] != IMMEDIATE_PROTOCOL or plan['delay_days'] != 0
                    or plan['repeats'] or plan['rounding'] != IMMEDIATE_ROUNDING
                    or plan['reliability_status'] != 'reliability_not_measured'):
                raise ValueError('Invalid immediate reconciliation protocol')
            return
        repeats = plan['repeats']
        import re
        if (plan['delay_days'] != 7 or len(repeats) != math.floor(len(cases) * .15 + .5)
                or any(not isinstance(repeat, dict) or set(repeat) != {'alias', 'case_id'}
                       or not isinstance(repeat['case_id'], str) or repeat['case_id'] not in cases
                       or not isinstance(repeat['alias'], str)
                       or not re.fullmatch(r'repeat_[0-9a-f]{24}', repeat['alias']) for repeat in repeats)
                or len({repeat['alias'] for repeat in repeats}) != len(repeats)
                or len({repeat['case_id'] for repeat in repeats}) != len(repeats)):
            raise ValueError('Invalid legacy delayed repeat subset')

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
        reliability = ('reliability_not_measured' if plan['version'] == 2 else
                       'repeat_assessments_collected' if not pending and complete else 'delayed_repeat_pending')
        return {'phase': phase, 'plan_version': plan['version'],
                'protocol_id': plan.get('protocol_id', LEGACY_PROTOCOL), 'reliability_status': reliability,
                'initial_completed': len(initial), 'initial_total': len(plan['case_ids']),
                'repeat_required': len(plan['repeats']), 'repeat_completed': len(plan['repeats']) - len(pending),
                'repeat_ready_at': eligible.isoformat() if eligible else None, 'delay_days': plan['delay_days'],
                'repeat_fraction': len(plan['repeats']) / len(plan['case_ids']), 'rounding': plan['rounding'],
                'completed_case_ids': sorted(initial) if phase != 'repeat' else [],
                'verification_completed_case_ids': sorted({event['case_id'] for event in events if event['stage'] == 'verification'}) if phase != 'repeat' else [],
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
            plan = self._plan(con, scope)
            envelope = {'schema_version': EXPORT_SCHEMA, 'protocol_version': plan['version'],
                        'scope': scope, 'events': [json.loads(r[0]) for r in rows]}
            if 'case_id' not in scope and (plan['version'] == 2 or protocol['phase'] == 'reconciliation' or allow_during_repeat):
                envelope['protocol_plan'] = plan
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
            requirement = ' and the frozen delayed repeat subset' if plan['version'] == 1 else ''
            raise ValueError(f'Complete every initial review{requirement} before revealing proposals')
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
            if stage == 'reveal':
                if self._protocol(con, event)['phase'] != 'reconciliation':
                    raise ValueError('Complete every initial review and any repeats required by your frozen protocol before revealing proposals')
                ident = tuple(event[key] for key in ('fingerprint', 'dataset', 'case_id', 'reviewer_id'))
                prior = con.execute("SELECT payload FROM events WHERE fingerprint=? AND dataset=? AND case_id=? AND reviewer_id=? AND stage='reveal'", ident).fetchone()
                if prior:
                    return json.loads(prior[0])
            self._insert(con, event)
        return event

    def import_events(self, envelope, dataset, detail_fn):
        if not isinstance(envelope, dict) or type(envelope.get('schema_version')) is not int or envelope['schema_version'] not in {1, EXPORT_SCHEMA}:
            raise ValueError('Unsupported or stale export schema')
        required = {'schema_version', 'scope', 'events'} | ({'protocol_version'} if envelope['schema_version'] == EXPORT_SCHEMA else set())
        if not required <= set(envelope) or set(envelope) - required - {'protocol_plan'}:
            raise ValueError('Unsupported or stale export schema')
        protocol_version = envelope.get('protocol_version', 1)
        if type(protocol_version) is not int or protocol_version not in {1, 2}:
            raise ValueError('Unsupported export protocol version')
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
            row = con.execute('SELECT payload FROM protocol_plans WHERE dataset=? AND fingerprint=? AND reviewer_id=?', self._key(scope)).fetchone()
            existing_plan = json.loads(row[0]) if row else None
            if 'protocol_plan' in envelope:
                plan = envelope['protocol_plan']
                cases = self.protocol_cases.get((scope['dataset'], scope['fingerprint']), {})
                self._validate_plan(plan, cases)
                if plan['version'] != protocol_version:
                    raise ValueError('Export and frozen protocol versions disagree')
                if existing_plan is not None and existing_plan != plan:
                    raise ValueError('Imported protocol conflicts with the already frozen review plan')
                if not row:
                    con.execute('INSERT INTO protocol_plans VALUES (?,?,?,?)', (*self._key(scope), json.dumps(plan, sort_keys=True)))
            elif existing_plan is None or existing_plan.get('version') != protocol_version:
                # Earlier exports could omit the hidden repeat plan. Recreating
                # it would change the participant's random subset and aliases.
                raise ValueError('A complete frozen protocol plan is required to restore this export into a new store')
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
