#!/usr/bin/env python3
"""Serve the review UI and the committed benchmark splits; stdlib only.

Run from any directory: python /path/to/IntelliAudit/dashboard/server.py
Blind reviews are append-only local SQLite records. Curator mode must be explicit.
"""
import argparse
import hashlib
import json
import os
import copy
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
try:
    from .review_store import ReviewStore, nonempty, validate_annotation
    from .presentation import build_presentation
except ImportError:
    from review_store import ReviewStore, nonempty, validate_annotation
    from presentation import build_presentation

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW_DATASET = 'pilot-v2'
PILOT_DIRECTORIES = {'pilot': 'data/review_pilot', 'pilot-v2': 'data/review_pilot_v2'}
DATASETS = {
    "us-gaap": ("US GAAP", "data/benchmark"),
    "multi": ("US GAAP · Multi-error", "data/benchmark_multi"),
    "ifrs": ("IFRS", "data/ifrs/benchmark"),
}
# Stable review cohorts, keyed by SEC CIK so filing captions can change safely.
REVIEW_COMPANIES = {
    "us-gaap": frozenset({"320193", "789019", "1045810", "1652044",
                          "1326801", "21344", "200406", "104169"}),
    "ifrs": frozenset({"1000184", "1114448", "901832", "1131399",
                       "1121404", "353278", "217410", "835403"}),
}
REVIEW_COMPANIES["multi"] = REVIEW_COMPANIES["us-gaap"]
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


def faults(key):
    """Normalize single- and multi-error keys without inventing control faults."""
    if key.get("record_type") == "control" or (not key.get("error_type") and not key.get("error_identification") and not key.get("errors")):
        return []
    if "errors" in key:
        return key["errors"]
    return [{**(key.get("error_identification") or {}),
             "rule_id": key.get("rule_id"), "error_type": key.get("error_type"),
             "ground_truth_citations": key.get("ground_truth_citations", {}),
             "injection_detail": key.get("injection_detail", {})}]


def values(errors, field):
    return sorted({e[field] for e in errors if e.get(field) is not None})


class Dataset:
    """Compact list index with byte offsets for full case details."""
    def __init__(self, directory, company_ciks=None):
        self.directory = Path(directory)
        self.entries, self.offsets, self.search = [], {}, {}
        allowed = None if company_ciks is None else {str(cik).lstrip("0") for cik in company_ciks}
        seen = set()
        digest = hashlib.sha256()
        keys = {}
        for offset, key in self._lines("answer_key.jsonl", digest):
            case_id = key["exam_id"]
            if case_id in keys:
                raise ValueError(f"Duplicate answer key: {case_id}")
            errors = faults(key)
            citations = [e.get("ground_truth_citations", {}) for e in errors]
            keys[case_id] = (offset, {
                "kind": key.get("record_type", "injected"),
                "error_count": len(errors),
                "error_types": values(errors, "error_type"),
                "rules": values(errors, "rule_id"),
                "labels": values(errors, "affected_label"),
                "citations": values(citations, "asc_full"),
                "tiers": values(citations, "citation_tier"),
                "citable": any(c.get("citable", False) for c in citations),
            })
        for offset, exam in self._lines("exam.jsonl", digest):
            case_id = exam["exam_id"]
            if case_id in seen:
                raise ValueError(f"Duplicate exam: {case_id}")
            seen.add(case_id)
            if case_id not in keys:
                raise ValueError(f"Exam has no matching answer key: {case_id}")
            key_offset, info = keys.pop(case_id)
            meta = exam["metadata"]
            if allowed is not None and str(meta.get("cik", "")).lstrip("0") not in allowed:
                continue
            self.offsets[case_id] = (offset, key_offset)
            self.entries.append({"id": case_id, **meta, "form": exam.get("form"), **info})
            self.search[case_id] = " ".join([
                case_id, json.dumps(meta, ensure_ascii=False),
                json.dumps(info, ensure_ascii=False),
                exam.get("statement_text", ""), exam.get("transaction_data", ""),
            ]).casefold()
        if keys:
            raise ValueError("Answer keys have no matching exam items")
        self.fingerprint = digest.hexdigest()[:16]
        self.facets = {}
        for field in ("company", "fiscal_year", "statement_type", "form", "kind"):
            self.facets[field] = sorted({e[field] for e in self.entries if e.get(field) is not None})
        for field in ("rules", "error_types", "citations", "tiers"):
            self.facets[field] = sorted({v for e in self.entries for v in e[field]})

    def _lines(self, filename, digest):
        with (self.directory / filename).open("rb") as stream:
            while True:
                offset = stream.tell()
                line = stream.readline()
                if not line:
                    return
                digest.update(line.replace(b'\r\n', b'\n'))
                if line.strip():
                    yield offset, json.loads(line)

    def detail(self, case_id):
        exam_offset, key_offset = self.offsets[case_id]
        result = {}
        for field, filename, offset in (("exam", "exam.jsonl", exam_offset),
                                         ("answer", "answer_key.jsonl", key_offset)):
            with (self.directory / filename).open("rb") as stream:
                stream.seek(offset)
                result[field] = json.loads(stream.readline())
        result["errors"] = faults(result["answer"])
        return result


class Store:
    def __init__(self, root=ROOT):
        self.root, self.cache, self.lock = Path(root), {}, threading.Lock()

    def get(self, dataset):
        if dataset not in DATASETS:
            raise ValueError("Unknown dataset")
        with self.lock:
            if dataset not in self.cache:
                self.cache[dataset] = Dataset(self.root / DATASETS[dataset][1], REVIEW_COMPANIES[dataset])
            return self.cache[dataset]


class BlindDataset:
    """Whitelist-only public projection; answers are read solely on explicit reveal."""
    def __init__(self, store, dataset_id):
        self.dataset_id = dataset_id
        self.exams, self.proposals = {}, {}
        if dataset_id in PILOT_DIRECTORIES:
            directory = store.root / PILOT_DIRECTORIES[dataset_id]
            self.directory = directory
            raw = (directory / 'public_cases.jsonl').read_bytes().replace(b'\r\n', b'\n')
            proposal_raw = (directory / 'curator/proposals.jsonl').read_bytes().replace(b'\r\n', b'\n')
            self.fingerprint = hashlib.sha256(raw + b'\x00' + proposal_raw).hexdigest()
            for line in raw.splitlines():
                exam = json.loads(line)
                if exam['exam_id'] in self.exams:
                    raise ValueError('Duplicate public case ID')
                self.exams[exam['exam_id']] = exam
            for line in proposal_raw.splitlines():
                proposal = json.loads(line)
                self.proposals[proposal['exam_id']] = proposal
            if set(self.exams) != set(self.proposals):
                raise ValueError('Public cases and proposals do not match')
            self.legacy = None
        else:
            self.legacy = store.get(dataset_id)
            self.fingerprint = self.legacy.fingerprint
            for entry in self.legacy.entries:
                # Original IDs contain generator labels. Do not send them to annotators.
                opaque = 'case_' + hashlib.sha256((self.fingerprint + ':' + entry['id']).encode()).hexdigest()[:24]
                exam = self.legacy.detail(entry['id'])['exam']
                self.exams[opaque] = {**exam, 'exam_id': opaque}
                self.proposals[opaque] = entry['id']
        self.entries = [{'id': case_id, **self.metadata(exam)} for case_id, exam in self.exams.items()]
        self.entries.sort(key=lambda entry: entry['id'])
        self.facets = {field: sorted({e[field] for e in self.entries if e.get(field) is not None})
                       for field in ('company', 'fiscal_year', 'statement_type')}

    @staticmethod
    def metadata(exam):
        return {field: exam.get('metadata', {}).get(field) for field in ('company', 'fiscal_year', 'statement_type', 'period', 'unit', 'currency', 'reporting_date', 'derived_rows') if field in exam.get('metadata', {})}

    def detail(self, case_id):
        exam = self.exams[case_id]
        public = {'exam_id': case_id, 'metadata': self.metadata(exam),
                  'statement_text': exam.get('statement_text', ''), 'transaction_data': exam.get('transaction_data', '')}
        units = []
        for source, field in (('statement', 'statement_text'), ('transactions', 'transaction_data')):
            for number, line in enumerate(public[field].splitlines(), 1):
                if line.strip():
                    units.append({'id': f'{source}:L{number:04d}', 'source': source, 'text': line})
        return {'exam': public, 'evidence_units': units,
                'presentation': build_presentation(public, units, self.dataset_id)}

    def quality(self):
        path = getattr(self, 'directory', ROOT / 'not-a-pilot') / 'curator/quality_report.json'
        if path.is_file():
            return json.loads(path.read_text(encoding='utf-8'))
        return {'construction_error_count': None, 'publication_blockers': ['Legacy packet: no expert-ready quality report is supplied.'],
                'curator_only_case_findings': [], 'status': 'not_expert_validated'}

    def curator_detail(self, case_id):
        if self.legacy:
            context = self.legacy.detail(self.proposals[case_id])
        else:
            context = copy.deepcopy(self.proposals[case_id])
        findings = self.quality().get('curator_only_case_findings', [])
        if isinstance(findings, dict):
            quality = findings.get(case_id, {})
        else:
            quality = next((finding for finding in findings if finding.get('case_id', finding.get('exam_id')) == case_id), {})
        return {'detail': self.detail(case_id), 'source_context': context, 'quality': quality}

    def reveal(self, case_id):
        if self.legacy:
            detail = self.legacy.detail(self.proposals[case_id])
            return {'answer': detail['answer'], 'errors': detail['errors'], 'status': 'unvalidated_proposal'}
        proposal = self.proposals[case_id]
        answer = proposal['answer']
        return {'answer': answer, 'errors': faults(answer), 'status': 'unvalidated_proposal'}


def handler_for(store, curator=False, reviews=None, auth=None, public_origin=None):
    reviews = reviews or ReviewStore(store.root / 'reviews/reviews.sqlite3')
    if auth and curator:
        raise ValueError('Hosted curator access uses the authenticated admin workspace')
    if auth:
        parsed_origin = urlsplit(public_origin or '')
        if parsed_origin.scheme != 'https' or not parsed_origin.hostname or parsed_origin.path or parsed_origin.query or parsed_origin.fragment or parsed_origin.username:
            raise ValueError('Hosted APP_ORIGIN must be one exact HTTPS origin')
    blind_cache = {}
    blind_lock = threading.Lock()
    def blind(dataset_id):
        if dataset_id not in DATASETS and dataset_id not in PILOT_DIRECTORIES:
            raise ValueError('Unknown dataset')
        with blind_lock:
            if dataset_id not in blind_cache:
                blind_cache[dataset_id] = BlindDataset(store, dataset_id)
                reviews.register_protocol(dataset_id, blind_cache[dataset_id].fingerprint, blind_cache[dataset_id].entries)
            return blind_cache[dataset_id]

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def send(self, status, body, content_type="application/json; charset=utf-8", headers=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if auth:
                self.send_header('Strict-Transport-Security', 'max-age=31536000')
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def local_request(self, mutation=False):
            allowed = {parsed_origin.netloc} if auth else {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            host = self.headers.get('Host', '')
            if host not in allowed:
                raise PermissionError('Unrecognized request host')
            origin = self.headers.get('Origin')
            expected_origin = public_origin if auth else 'http://' + host
            if (origin and origin != expected_origin) or (auth and mutation and origin != expected_origin):
                raise PermissionError('Cross-origin requests are forbidden')
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise PermissionError('Cross-site requests are forbidden')

        def token(self):
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get('Cookie', ''))
            except Exception:
                return ''
            value = cookies.get('__Host-intelliaudit')
            return value.value if value else ''

        def current_session(self, required=True, curator_only=False, mutation=False):
            if not auth:
                return None
            session = auth.session(self.token())
            if not session:
                if required:
                    raise AuthenticationError('Sign in to continue')
                return None
            if curator_only and session['reviewer']['role'] != 'curator':
                raise PermissionError('Curator access required')
            if mutation and not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf_token']):
                raise PermissionError('Session security token is missing or invalid')
            return session

        def reviewer_id(self, supplied, session):
            if session:
                identity = session['reviewer']['id']
                if session['reviewer']['role'] != 'reviewer':
                    raise PermissionError('Use a separate accountant account for independent review')
                if supplied is not None and supplied != identity:
                    raise PermissionError('You can access only your own review records')
                return identity
            return nonempty(supplied, 'reviewer_id', 200)

        def scope(self, dataset_id, dataset, reviewer_id, case_id=None):
            result = {'dataset': dataset_id, 'fingerprint': dataset.fingerprint, 'reviewer_id': reviewer_id}
            if case_id is not None:
                result['case_id'] = case_id
            return result

        def all_reviews(self, dataset_id, dataset):
            events = []
            for user in auth.reviewers():
                if user['role'] == 'reviewer':
                    scope = self.scope(dataset_id, dataset, user['id'])
                    events.extend(reviews.history(scope, allow_during_repeat=True)['events'])
            return events

        def reviewer_exports(self, dataset_id, dataset):
            return [reviews.history(self.scope(dataset_id, dataset, user['id']), allow_during_repeat=True)
                    for user in auth.reviewers() if user['role'] == 'reviewer']

        @staticmethod
        def parameters(query, allowed):
            if set(query) - set(allowed) or any(len(v) != 1 for v in query.values()):
                raise ValueError('Unknown or duplicate parameter')
            return {k: v[0] for k, v in query.items()}

        def guard(self, action):
            try:
                self.local_request()
                action()
            except PermissionError as error:
                self.send(403, {'error': str(error)})
            except AuthenticationError as error:
                self.send(401, {'error': str(error)})
            except (ValueError, TypeError, AttributeError) as error:
                self.send(400, {'error': str(error)})
            except KeyError:
                self.send(404, {'error': 'Case or required field not found'})
            except FileNotFoundError:
                self.send(404, {'error': 'Dataset or asset files are missing; build the pilot first.'})
            except OSError as error:
                self.log_error('Storage operation failed (%s)', type(error).__name__)
                self.send(500, {'error': 'Storage is temporarily unavailable; your submission was not confirmed. Please retry.'})
            except Exception as error:
                self.log_error('Operation failed (%s)', type(error).__name__)
                self.send(500, {'error': 'The service could not complete this operation. Please retry.'})

        def do_GET(self):
            if self.path == '/healthz':
                self.send(200, {'status': 'ok'})
                return
            self.guard(self.get)

        def get(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query, keep_blank_values=True)
            session = self.current_session(required=False)
            if url.path == '/api/auth/session':
                self.parameters(query, set())
                self.send(200, {'hosted': bool(auth), 'authenticated': bool(session), **(session or {})})
                return
            login_assets = {'/login.html': ('login.html', 'text/html; charset=utf-8'), '/login.js': ('login.js', 'text/javascript; charset=utf-8'), '/login.css': ('login.css', 'text/css; charset=utf-8')}
            if url.path in login_assets:
                filename, mime = login_assets[url.path]
                self.send(200, (Path(__file__).parent / filename).read_bytes(), mime)
                return
            if auth and not session:
                if not url.path.startswith('/api/'):
                    self.send(303, b'', headers={'Location': '/login.html'})
                    return
                raise AuthenticationError('Sign in to continue')
            if auth and url.path in {'/admin.html', '/admin.js', '/admin.css'}:
                self.current_session(curator_only=True)
                filename = url.path[1:]
                mime = 'text/html; charset=utf-8' if filename.endswith('.html') else 'text/javascript; charset=utf-8' if filename.endswith('.js') else 'text/css; charset=utf-8'
                self.send(200, (Path(__file__).parent / filename).read_bytes(), mime)
                return
            if auth and url.path.startswith('/api/admin/'):
                self.current_session(curator_only=True)
                q = self.parameters(query, {'dataset', 'id'} if url.path == '/api/admin/case' else {'dataset'})
                dataset_id = q.get('dataset', DEFAULT_REVIEW_DATASET)
                dataset = blind(dataset_id)
                if url.path == '/api/admin/reviewers':
                    users = auth.reviewers()
                    for user in users:
                        if user['role'] == 'reviewer':
                            user['protocol'] = reviews.protocol(self.scope(dataset_id, dataset, user['id']))
                    self.send(200, {'reviewers': users})
                elif url.path == '/api/admin/comparison':
                    from .agreement import build_comparison
                    self.send(200, build_comparison(dataset.entries, self.all_reviews(dataset_id, dataset), auth.resolutions({'dataset': dataset_id, 'fingerprint': dataset.fingerprint})))
                elif url.path == '/api/admin/export':
                    self.send(200, {'schema_version': 2, 'dataset': dataset_id, 'fingerprint': dataset.fingerprint,
                                    'events': self.all_reviews(dataset_id, dataset),
                                    'reviewer_exports': self.reviewer_exports(dataset_id, dataset),
                                    'adjudications': auth.resolutions({'dataset': dataset_id, 'fingerprint': dataset.fingerprint}),
                                    'status': 'operational_records_not_publication_gold'})
                elif url.path == '/api/admin/quality':
                    self.send(200, dataset.quality())
                elif url.path == '/api/admin/case':
                    self.send(200, dataset.curator_detail(q.get('id', '')))
                else:
                    self.send(404, {'error': 'Not found'})
                return
            assets = {'/': ('index.html' if curator else 'blind.html', 'text/html; charset=utf-8'),
                      '/blind.html': ('blind.html', 'text/html; charset=utf-8'),
                      '/blind.js': ('blind.js', 'text/javascript; charset=utf-8'),
                      '/blind.css': ('blind.css', 'text/css; charset=utf-8')}
            if curator:
                assets.update({k: v for k, v in ASSETS.items() if k != '/'})
                assets['/index.html'] = ('index.html', 'text/html; charset=utf-8')
            if url.path in assets:
                filename, mime = assets[url.path]
                self.send(200, (Path(__file__).parent / filename).read_bytes(), mime)
                return
            if url.path in ('/api/blind/index', '/api/blind/case'):
                q = self.parameters(query, {'dataset', 'id'})
                dataset_id = q.get('dataset', DEFAULT_REVIEW_DATASET)
                dataset = blind(dataset_id)
                if auth:
                    identity = self.reviewer_id(None, session)
                    protocol = reviews.protocol(self.scope(dataset_id, dataset, identity))
                    if protocol['phase'] == 'repeat' and url.path.endswith('/case'):
                        raise PermissionError('Complete the shuffled repeat packet before reopening the initial cases')
                if url.path.endswith('/index'):
                    self.send(200, {'dataset': dataset_id, 'name': ('Revenue review pilot v2' if dataset_id == 'pilot-v2' else 'Legacy revenue review pilot v1') if dataset_id in PILOT_DIRECTORIES else DATASETS[dataset_id][0],
                                    'fingerprint': dataset.fingerprint, 'facets': dataset.facets, 'cases': protocol['repeat_cases'] if auth and protocol['phase'] == 'repeat' else dataset.entries})
                else:
                    self.send(200, dataset.detail(q.get('id', '')))
                return
            if url.path in ('/api/review/history', '/api/review/export', '/api/review/protocol', '/api/review/repeat-case'):
                q = self.parameters(query, {'dataset', 'case_id', 'reviewer_id', 'id'})
                dataset_id = q.get('dataset', DEFAULT_REVIEW_DATASET)
                dataset = blind(dataset_id)
                scope = self.scope(dataset_id, dataset, self.reviewer_id(q.get('reviewer_id'), session))
                if url.path.endswith('/protocol'):
                    self.send(200, reviews.protocol(scope))
                    return
                if url.path.endswith('/repeat-case'):
                    self.send(200, reviews.repeat_detail(scope, q.get('id', ''), dataset.detail))
                    return
                if url.path.endswith('/history'):
                    scope['case_id'] = q.get('case_id', '')
                    dataset.detail(scope['case_id'])
                self.send(200, reviews.history(scope))
                return
            if curator and url.path in ('/api/index', '/api/case', '/api/search'):
                q = self.parameters(query, {'dataset', 'id', 'q'})
                dataset_id = q.get('dataset', 'us-gaap')
                dataset = store.get(dataset_id)
                if url.path == '/api/index':
                    self.send(200, {'dataset': dataset_id, 'name': DATASETS[dataset_id][0], 'fingerprint': dataset.fingerprint,
                                    'facets': dataset.facets, 'cases': dataset.entries})
                elif url.path == '/api/case':
                    self.send(200, dataset.detail(q.get('id', '')))
                else:
                    terms = q.get('q', '').casefold().split()
                    self.send(200, {'ids': [i for i, text in dataset.search.items() if all(t in text for t in terms)]})
                return
            self.send(404, {'error': 'Not found'})

        def do_POST(self):
            self.guard(self.post)

        def post(self):
            self.local_request(mutation=True)
            url = urlsplit(self.path)
            paths = {'/api/review/submit', '/api/review/reveal', '/api/review/import', '/api/review/repeat-submit', '/api/auth/login', '/api/auth/logout', '/api/admin/invite', '/api/admin/revoke', '/api/admin/adjudicate'}
            if url.query or url.path not in paths or (not auth and url.path.startswith(('/api/auth/', '/api/admin/'))):
                self.send(404, {'error': 'Not found'})
                return
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('Use application/json')
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 2_000_000 or self.headers.get('Transfer-Encoding'):
                raise ValueError('Request body missing or too large')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Expected JSON object')
            if url.path == '/api/auth/login':
                if not auth:
                    raise ValueError('Login is available only in hosted mode')
                if set(body) != {'invite_code'}:
                    raise ValueError('Expected a personal access code')
                # Render terminates TLS and sets X-Forwarded-For. The last hop is
                # controlled by the proxy; without it use the direct peer.
                client = self.headers.get('X-Forwarded-For', '').split(',')[-1].strip() or self.client_address[0]
                token, result = auth.login(body['invite_code'], client)
                self.send(200, result, headers={'Set-Cookie': f'__Host-intelliaudit={token}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=28800'})
                return
            session = self.current_session(mutation=True)
            if url.path == '/api/auth/logout':
                if not auth or body:
                    raise ValueError('Invalid logout request')
                auth.logout(self.token())
                self.send(200, {'signed_out': True}, headers={'Set-Cookie': '__Host-intelliaudit=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0'})
                return
            if url.path.startswith('/api/admin/'):
                self.current_session(curator_only=True, mutation=True)
                if url.path.endswith('/invite'):
                    if set(body) != {'name', 'qualification'}:
                        raise ValueError('Expected name and qualification')
                    self.send(200, auth.invite(body['name'], body['qualification']))
                elif url.path.endswith('/revoke'):
                    if set(body) != {'reviewer_id'}:
                        raise ValueError('Expected reviewer_id')
                    auth.revoke(nonempty(body['reviewer_id'], 'reviewer_id', 200))
                    self.send(200, {'revoked': True})
                else:
                    if set(body) != {'dataset', 'case_id', 'annotation', 'reason'}:
                        raise ValueError('Invalid curator resolution fields')
                    dataset_id = body['dataset']
                    dataset = blind(dataset_id)
                    detail = dataset.detail(body['case_id'])
                    annotation = validate_annotation(body['annotation'], detail, 'blind')
                    all_events = self.all_reviews(dataset_id, dataset)
                    events = [event for event in all_events if event['stage'] == 'blind' and event['case_id'] == body['case_id']]
                    for reviewer_id in {event['reviewer_id'] for event in all_events if event['stage'] == 'blind'}:
                        if reviews.protocol(self.scope(dataset_id, dataset, reviewer_id))['phase'] != 'reconciliation':
                            raise PermissionError('Curator resolution opens after every contributing reviewer completes their frozen review protocol')
                    scope = {'dataset': dataset_id, 'fingerprint': dataset.fingerprint, 'case_id': body['case_id']}
                    self.send(200, {'record': auth.resolve(scope, session['reviewer']['id'], annotation, body['reason'], [event['event_id'] for event in events])})
                return
            if url.path.endswith('/import'):
                if auth:
                    raise PermissionError('Hosted reviewer imports are disabled to preserve server-recorded identity and timestamps')
                dataset_id = body.get('scope', {}).get('dataset', '')
                dataset = blind(dataset_id)
                self.send(200, reviews.import_events(body, dataset, dataset.detail))
                return
            allowed = {'dataset', 'case_id', 'reviewer_id'}
            if url.path.endswith('/submit') or url.path.endswith('/repeat-submit'):
                allowed |= {'reviewer_name', 'qualification', 'stage', 'annotation'}
            if set(body) - allowed:
                raise ValueError('Unknown request field')
            dataset_id = body.get('dataset', DEFAULT_REVIEW_DATASET)
            dataset = blind(dataset_id)
            identity = self.reviewer_id(body.get('reviewer_id'), session)
            scope = reviews.identity(dataset_id, dataset.fingerprint, body.get('case_id'), identity)
            if session:
                for field, expected in (('reviewer_name', session['reviewer']['name']), ('qualification', session['reviewer']['qualification'])):
                    if field in body and body[field] != expected:
                        raise PermissionError('Reviewer details are controlled by your invitation account')
                    body[field] = expected
            if url.path.endswith('/repeat-submit'):
                name = nonempty(body.get('reviewer_name'), 'reviewer_name', 300)
                qualification = nonempty(body.get('qualification'), 'qualification', 2000)
                self.send(200, {'record': reviews.append_repeat(scope, scope['case_id'], name, qualification, body.get('annotation'), dataset.detail)})
                return
            detail = dataset.detail(scope['case_id'])
            if url.path.endswith('/reveal'):
                record = reviews.append(scope, 'reveal')
                self.send(200, {**dataset.reveal(scope['case_id']), 'record': record})
            else:
                stage = body.get('stage')
                if stage not in {'blind', 'verification'}:
                    raise ValueError('Unknown submission stage')
                name = nonempty(body.get('reviewer_name'), 'reviewer_name', 300)
                qualification = nonempty(body.get('qualification'), 'qualification', 2000)
                annotation = validate_annotation(body.get('annotation'), detail, stage)
                self.send(200, {'record': reviews.append(scope, stage, name, qualification, annotation)})

    return Handler


class AuthenticationError(Exception):
    """A valid session is required; distinct from authenticated authorization."""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--hosted', action='store_true', help='Require invitation authentication and durable PostgreSQL storage')
    parser.add_argument('--curator', action='store_true', help='Expose proposal keys and the legacy verification dashboard (never use for blind review)')
    args = parser.parse_args()
    auth = None
    public_origin = None
    if args.hosted:
        from .auth_store import AuthStore
        from .postgres_store import PostgresReviewStore
        database_url = os.environ.get('DATABASE_URL', '')
        public_origin = os.environ.get('APP_ORIGIN') or os.environ.get('RENDER_EXTERNAL_URL')
        if not database_url:
            parser.error('Hosted mode requires DATABASE_URL; ephemeral SQLite is not permitted')
        reviews = PostgresReviewStore(database_url)
        auth = AuthStore(reviews.connect, os.environ.get('ADMIN_ACCESS_CODE', ''))
    else:
        if args.host not in {'127.0.0.1', 'localhost', '::1'}:
            parser.error('Public interfaces require --hosted and authentication')
        reviews = ReviewStore(os.environ.get('REVIEW_DB_PATH', str(ROOT / 'reviews/reviews.sqlite3')))
    with ThreadingHTTPServer((args.host, args.port), handler_for(Store(), curator=args.curator, reviews=reviews, auth=auth, public_origin=public_origin)) as server:
        server.timeout = 30
        print(f"IntelliAudit {'CURATOR (answers visible)' if args.curator else 'BLIND review'}: {public_origin if auth else f'http://127.0.0.1:{args.port}'}", flush=True)
        print('Hosted access: invitation accounts and durable PostgreSQL.' if auth else 'Local workspace only; reviewer IDs are not authentication. Reviews persist in the configured SQLite file.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
