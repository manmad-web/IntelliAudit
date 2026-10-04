#!/usr/bin/env python3
"""Serve the review UI and the committed benchmark splits; stdlib only.

Run from any directory: python /path/to/IntelliAudit/dashboard/server.py
Blind reviews are append-only local SQLite records. Curator mode must be explicit.
"""
import argparse
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
try:
    from .review_store import ReviewStore, nonempty, validate_annotation
except ImportError:
    from review_store import ReviewStore, nonempty, validate_annotation

ROOT = Path(__file__).resolve().parents[1]
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
                digest.update(line)
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
        if dataset_id == 'pilot':
            directory = store.root / 'data/review_pilot'
            raw = (directory / 'public_cases.jsonl').read_bytes()
            proposal_raw = (directory / 'curator/proposals.jsonl').read_bytes()
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
        return {field: exam.get('metadata', {}).get(field) for field in ('company', 'fiscal_year', 'statement_type', 'period', 'unit', 'currency', 'reporting_date') if field in exam.get('metadata', {})}

    def detail(self, case_id):
        exam = self.exams[case_id]
        public = {'exam_id': case_id, 'metadata': self.metadata(exam),
                  'statement_text': exam.get('statement_text', ''), 'transaction_data': exam.get('transaction_data', '')}
        units = []
        for source, field in (('statement', 'statement_text'), ('transactions', 'transaction_data')):
            for number, line in enumerate(public[field].splitlines(), 1):
                if line.strip():
                    units.append({'id': f'{source}:L{number:04d}', 'source': source, 'text': line})
        return {'exam': public, 'evidence_units': units}

    def reveal(self, case_id):
        if self.legacy:
            detail = self.legacy.detail(self.proposals[case_id])
            return {'answer': detail['answer'], 'errors': detail['errors'], 'status': 'unvalidated_proposal'}
        proposal = self.proposals[case_id]
        answer = proposal['answer']
        return {'answer': answer, 'errors': faults(answer), 'status': 'unvalidated_proposal'}


def handler_for(store, curator=False, reviews=None):
    reviews = reviews or ReviewStore(store.root / 'reviews/reviews.sqlite3')
    blind_cache = {}
    blind_lock = threading.Lock()
    def blind(dataset_id):
        if dataset_id not in DATASETS and dataset_id != 'pilot':
            raise ValueError('Unknown dataset')
        with blind_lock:
            if dataset_id not in blind_cache:
                blind_cache[dataset_id] = BlindDataset(store, dataset_id)
            return blind_cache[dataset_id]

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def local_request(self, mutation=False):
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            host = self.headers.get('Host', '')
            if host not in allowed:
                raise PermissionError('Use the localhost URL printed by the server')
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + host:
                raise PermissionError('Cross-origin requests are forbidden')
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise PermissionError('Cross-site requests are forbidden')

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
            except (ValueError, TypeError, AttributeError) as error:
                self.send(400, {'error': str(error)})
            except KeyError:
                self.send(404, {'error': 'Case or required field not found'})
            except FileNotFoundError:
                self.send(404, {'error': 'Dataset or asset files are missing; build the pilot first.'})
            except OSError as error:
                self.log_error('Read failed: %s', error)
                self.send(500, {'error': 'Could not read local data'})

        def do_GET(self):
            self.guard(self.get)

        def get(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query, keep_blank_values=True)
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
                dataset_id = q.get('dataset', 'pilot')
                dataset = blind(dataset_id)
                if url.path.endswith('/index'):
                    self.send(200, {'dataset': dataset_id, 'name': 'Revenue review pilot' if dataset_id == 'pilot' else DATASETS[dataset_id][0],
                                    'fingerprint': dataset.fingerprint, 'facets': dataset.facets, 'cases': dataset.entries})
                else:
                    self.send(200, dataset.detail(q.get('id', '')))
                return
            if url.path in ('/api/review/history', '/api/review/export'):
                q = self.parameters(query, {'dataset', 'case_id', 'reviewer_id'})
                dataset_id = q.get('dataset', 'pilot')
                dataset = blind(dataset_id)
                scope = {'dataset': dataset_id, 'fingerprint': dataset.fingerprint,
                         'reviewer_id': nonempty(q.get('reviewer_id'), 'reviewer_id', 200)}
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
            if url.query or url.path not in {'/api/review/submit', '/api/review/reveal', '/api/review/import'}:
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
            if url.path.endswith('/import'):
                dataset_id = body.get('scope', {}).get('dataset', '')
                dataset = blind(dataset_id)
                self.send(200, reviews.import_events(body, dataset, dataset.detail))
                return
            allowed = {'dataset', 'case_id', 'reviewer_id'}
            if url.path.endswith('/submit'):
                allowed |= {'reviewer_name', 'qualification', 'stage', 'annotation'}
            if set(body) - allowed:
                raise ValueError('Unknown request field')
            dataset_id = body.get('dataset', 'pilot')
            dataset = blind(dataset_id)
            scope = reviews.identity(dataset_id, dataset.fingerprint, body.get('case_id'), body.get('reviewer_id'))
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--curator', action='store_true', help='Expose proposal keys and the legacy verification dashboard (never use for blind review)')
    args = parser.parse_args()
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(Store(), curator=args.curator)) as server:
        print(f"IntelliAudit {'CURATOR (answers visible)' if args.curator else 'BLIND review'}: http://127.0.0.1:{args.port}", flush=True)
        print('Local workspace only; reviewer IDs are not authentication. Reviews persist in reviews/reviews.sqlite3.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
