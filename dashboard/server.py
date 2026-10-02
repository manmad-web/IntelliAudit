#!/usr/bin/env python3
"""Serve the review UI and the committed benchmark splits; stdlib only.

Run from any directory: python /path/to/IntelliAudit/dashboard/server.py
Reviews live in the browser, never in the exam or answer key.
"""
import argparse
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

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
    if key.get("record_type") == "control":
        return []
    if "errors" in key:
        return key["errors"]
    return [{**key.get("error_identification", {}),
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


def handler_for(store):
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

        def do_GET(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            try:
                if url.path in ASSETS:
                    filename, mime = ASSETS[url.path]
                    self.send(200, (Path(__file__).parent / filename).read_bytes(), mime)
                    return
                if url.path not in ("/api/index", "/api/case", "/api/search"):
                    self.send(404, {"error": "Not found"})
                    return
                dataset_id = query.get("dataset", ["us-gaap"])[0]
                dataset = store.get(dataset_id)
                if url.path == "/api/index":
                    self.send(200, {"dataset": dataset_id, "name": DATASETS[dataset_id][0],
                                    "fingerprint": dataset.fingerprint,
                                    "facets": dataset.facets, "cases": dataset.entries})
                elif url.path == "/api/case":
                    self.send(200, dataset.detail(query.get("id", [""])[0]))
                else:
                    terms = query.get("q", [""])[0].casefold().split()
                    self.send(200, {"ids": [i for i, text in dataset.search.items()
                                             if all(t in text for t in terms)]})
            except ValueError as error:
                self.send(400, {"error": str(error)})
            except KeyError:
                self.send(404, {"error": "Case not found"})
            except FileNotFoundError:
                self.send(404, {"error": "Dataset files are missing. Build this dataset first."})
            except (OSError, TypeError) as error:
                self.log_error("Dataset read failed: %s", error)
                self.send(500, {"error": "Could not read the dataset. Check the server log."})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(Store())) as server:
        print(f"IntelliAudit accountant review: http://127.0.0.1:{args.port}", flush=True)
        print("Press Ctrl+C to stop. Notes are saved in this browser; export to back them up.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
