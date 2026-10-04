"""Dataset join and HTTP contracts for the local accountant review dashboard."""
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from dashboard.server import Dataset, Store, faults, handler_for


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.directory = self.root / "data" / "benchmark"
        self.directory.mkdir(parents=True)
        self.exams = [
            {"exam_id": "EX-control", "form": 0, "metadata": {
                "company": "Café & Co", "cik": "0000320193", "fiscal_year": 2024, "statement_type": "BalanceSheet"},
             "statement_text": "[row 0]: Inventories | $400 [SEP]", "transaction_data": "Valuation memo"},
            {"exam_id": "EX-multi", "form": 1, "metadata": {
                "company": "Café & Co", "cik": "0000320193", "fiscal_year": 2023, "statement_type": "IncomeStatement"},
             "statement_text": "[row 0]: Revenue | $800 [SEP]", "transaction_data": "Cut-off review"},
        ]
        self.keys = [
            {"exam_id": "EX-multi", "record_type": "injected", "errors": [
                {"rule_id": "R09", "error_type": "Numerical Error", "problematic_entry": 0,
                 "post_inject_row": 0, "pre_inject_row": 0,
                 "ground_truth_citations": {"asc_full": "ASC 606-10-25-23", "citable": True,
                                            "citation_tier": "expert-authored-UNVALIDATED"}},
                {"rule_id": "R04", "error_type": "Missing Row", "post_inject_row": None,
                 "pre_inject_row": 1, "ground_truth_citations": {"citable": False}},
            ], "corrected_statement_text": "[row 0]: Revenue | $700 [SEP]"},
            {"exam_id": "EX-control", "record_type": "control", "general_judgement": "Correct"},
        ]
        self.write("exam.jsonl", self.exams)
        self.write("answer_key.jsonl", self.keys)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, records):
        (self.directory / name).write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in records), encoding="utf-8")

    def test_joins_by_id_instead_of_file_position_and_reads_utf8_offsets(self):
        data = Dataset(self.directory)
        self.assertEqual(data.detail("EX-control")["exam"]["metadata"]["company"], "Café & Co")
        self.assertEqual(data.detail("EX-control")["answer"]["general_judgement"], "Correct")
        detail = data.detail("EX-multi")
        self.assertEqual(detail["exam"]["form"], 1)
        self.assertEqual(len(detail["errors"]), 2)
        self.assertIsNone(detail["errors"][1]["post_inject_row"])

    def test_multi_fault_facets_and_control_do_not_invent_citations(self):
        data = Dataset(self.directory)
        self.assertEqual(data.entries[0]["error_count"], 0)
        self.assertFalse(data.entries[0]["citable"])
        self.assertEqual(data.entries[1]["error_count"], 2)
        self.assertTrue(data.entries[1]["citable"])
        self.assertEqual(data.facets["rules"], ["R04", "R09"])
        self.assertEqual(data.facets["citations"], ["ASC 606-10-25-23"])

    def test_single_key_preserves_explicit_missing_row(self):
        errors = faults({"rule_id": "R04", "error_type": "Missing Row",
                         "error_identification": {"post_inject_row": None, "pre_inject_row": 3}})
        self.assertIsNone(errors[0]["post_inject_row"])
        self.assertEqual(errors[0]["pre_inject_row"], 3)

    def test_review_scope_excludes_unselected_companies_from_all_endpoints(self):
        excluded = {**self.exams[0], "exam_id": "EX-excluded", "metadata": {
            **self.exams[0]["metadata"], "company": "Outside cohort", "cik": "0000000042"}}
        self.write("exam.jsonl", self.exams + [excluded])
        self.write("answer_key.jsonl", self.keys + [{"exam_id": "EX-excluded", "record_type": "control"}])
        data = Store(self.root).get("us-gaap")
        self.assertEqual(len(data.entries), 2)
        self.assertEqual(data.facets["company"], ["Café & Co"])
        self.assertNotIn("EX-excluded", data.search)
        with self.assertRaises(KeyError):
            data.detail("EX-excluded")
        self.assertEqual(data.detail("EX-control")["exam"]["exam_id"], "EX-control")

    def test_data_version_changes_if_only_the_answer_key_changes(self):
        before = Dataset(self.directory).fingerprint
        self.keys[0]["corrected_statement_text"] += " corrected"
        self.write("answer_key.jsonl", self.keys)
        self.assertNotEqual(Dataset(self.directory).fingerprint, before)

    def test_duplicate_and_unpaired_items_are_rejected(self):
        self.write("exam.jsonl", self.exams + self.exams[:1])
        with self.assertRaisesRegex(ValueError, "Duplicate exam"):
            Dataset(self.directory)
        self.write("exam.jsonl", self.exams[:1])
        with self.assertRaisesRegex(ValueError, "no matching exam"):
            Dataset(self.directory)
        self.write("exam.jsonl", self.exams)
        self.write("answer_key.jsonl", self.keys[:1])
        with self.assertRaisesRegex(ValueError, "no matching answer key"):
            Dataset(self.directory)

    def test_http_search_errors_and_static_allowlist(self):
        handler = handler_for(Store(self.root), curator=True)
        handler.log_message = lambda *args: None
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/api/search?q=revenue+800") as response:
                self.assertEqual(json.load(response)["ids"], ["EX-multi"])
            with urlopen(base + "/api/index") as response:
                index = json.load(response)
                self.assertEqual(len(index["cases"]), 2)
                self.assertNotIn("statement_text", index["cases"][0])
            with urlopen(base + "/") as response:
                self.assertIn(b"Accountant review", response.read())
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            for path, status in [("/api/index?dataset=../", 400), ("/api/case?id=absent", 404),
                                  ("/../README.md", 404), ("/.git/config", 404)]:
                with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                    urlopen(base + path)
                self.assertEqual(error.exception.code, status)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
