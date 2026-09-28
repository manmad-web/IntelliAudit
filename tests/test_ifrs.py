#!/usr/bin/env python3
"""IFRS scaffolding: citation grammar, resolver on a fixture linkbase, scoring, rulebook."""
import io, json, os, sys, tempfile, unittest, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from citation_resolver import (IfrsCitationResolver, ifrs_code_from_parts,  # noqa: E402
                               ifrs_paragraph_of, ifrs_standard_of)
from scorer import score_citation  # noqa: E402


class Grammar(unittest.TestCase):
    def test_parts(self):
        self.assertEqual(ifrs_code_from_parts([("Name", "IAS"), ("Number", "1"), ("Paragraph", "66"),
                                               ("Subparagraph", "a")]), "IAS 1.66(a)")
        self.assertEqual(ifrs_code_from_parts([("Name", "IFRS"), ("Number", "15"), ("Paragraph", "31")]),
                         "IFRS 15.31")
        self.assertIsNone(ifrs_code_from_parts([("Name", "FASB"), ("Number", "1")]))

    def test_paragraph_forms(self):
        for t in ("IAS 1.66", "IAS 1 paragraph 66(a)", "see IAS 1, para. 66", "IAS 01.66"):
            self.assertEqual(ifrs_paragraph_of(t), "IAS 1.66", t)
        self.assertIsNone(ifrs_paragraph_of("IAS 1"))
        self.assertEqual(ifrs_paragraph_of("IFRS 9.5.5.15"), "IFRS 9.5.5.15")
        self.assertEqual(ifrs_paragraph_of("IFRS 9 paragraph 4.1.2A(b)"), "IFRS 9.4.1.2A")
        self.assertEqual(ifrs_paragraph_of("IAS 36.59."), "IAS 36.59")
        self.assertEqual(ifrs_standard_of("under IFRS 15 control transfers"), "IFRS 15")


class Resolver(unittest.TestCase):
    def test_fixture_linkbase(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.write(os.path.join(ROOT, "tests", "fixtures", "ifrs_ref_fixture.xml"),
                    "IFRSAT/full_ifrs/linkbases/ias_2/ref_ias_2.xml")
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            f.write(buf.getvalue())
        cr = IfrsCitationResolver(f.name)
        self.assertEqual(cr.citations("Inventories"), ["IAS 1.54(g)", "IAS 2.36(b)"])
        self.assertTrue(cr.paragraph_verified("ifrs-full:Inventories", "IAS 2.36"))
        self.assertFalse(cr.paragraph_verified("ifrs-full:Inventories", "IAS 2.9"))
        os.unlink(f.name)


class Scoring(unittest.TestCase):
    gt = {"citable": True, "asc_full": "IAS 36.59"}

    def test_levels(self):
        self.assertEqual(score_citation("IAS 36 paragraph 59 applies", self.gt),
                         {"em_topic": 1, "em_subtopic": 1, "em_full": 1})
        self.assertEqual(score_citation("IAS 36.90", self.gt), {"em_topic": 1, "em_subtopic": 1, "em_full": 0})
        self.assertEqual(score_citation("ASC 360-10-35-17", self.gt), {"em_topic": 0, "em_subtopic": 0, "em_full": 0})

    def test_us_gaap_unchanged(self):
        gt = {"citable": True, "asc_full": "ASC 360-10-35-17", "linkbase_reference_set": []}
        self.assertEqual(score_citation("ASC 360-10-35-17", gt, credit_linkbase_set=False)["em_full"], 1)


class GroundTruth(unittest.TestCase):
    def test_ifrs_citation_fields_and_subparagraph_verification(self):
        import injector
        with open(os.path.join(ROOT, "rulebook_ifrs.json")) as fh:
            rb = {r["rule_id"].split("_")[0]: r for r in json.load(fh)["rules"]}

        class Fake:
            def citations(self, c):
                return ["IAS 1.54(g)", "IAS 2.9(a)"]
        saved, injector._RESOLVER = injector._RESOLVER, Fake()
        try:
            g = injector._citation_gt(rb["I11"], "BalanceSheet", "ifrs-full:Inventories")
        finally:
            injector._RESOLVER = saved
        self.assertEqual((g["asc_full"], g["asc_topic"], g["asc_subtopic"]), ("IAS 2.9", "IAS 2", "IAS 2"))
        self.assertTrue(g["linkbase_verified"])
        self.assertEqual(g["citation_tier"], "linkbase-verified")


class Rulebook(unittest.TestCase):
    def test_ifrs_rulebook_is_separate_and_parallel(self):
        with open(os.path.join(ROOT, "rulebook_ifrs.json")) as f:
            rb = json.load(f)
        self.assertEqual(rb["_meta"]["framework"], "ifrs")
        for r in rb["rules"]:
            asc = r["citation"]["asc"]
            if asc:
                self.assertIsNotNone(ifrs_paragraph_of(asc), r["rule_id"])
                self.assertNotIn("ASC", asc)
            for c in r.get("eligible_concepts", []):
                self.assertTrue(c.startswith("ifrs-full:") or c.startswith("*"), c)

    def test_framework_flips_are_documented(self):
        with open(os.path.join(ROOT, "rulebook_ifrs.json")) as f:
            rb = json.load(f)
        flips = [r for r in rb["rules"] if r.get("framework_contrast")]
        self.assertGreaterEqual(len(flips), 4)


if __name__ == "__main__":
    unittest.main()


class SyntheticIfrsFiling(unittest.TestCase):
    """End-to-end on a mocked 20-F: ifrs-full facts + a calculation tree.

    Real IFRS filings have not been fetched in this environment (no SEC access);
    this exercises the code path so the first online run fails on data, not code.
    """

    def _facts(self):
        vals = {"Assets": 1000, "CurrentAssets": 400, "Inventories": 150, "TradeAndOtherCurrentReceivables": 120,
                "CashAndCashEquivalents": 130, "PropertyPlantAndEquipment": 350, "Goodwill": 250,
                "EquityAndLiabilities": 1000, "CurrentLiabilities": 200, "TradeAndOtherCurrentPayables": 200,
                "NoncurrentPortionOfNoncurrentBorrowings": 300, "Equity": 500, "IssuedCapital": 100,
                "RetainedEarnings": 450, "TreasuryShares": 50}
        f = lambda v: {"EUR": [{"val": v * 1_000_000, "fy": 2023, "fp": "FY", "form": "20-F",
                                "end": "2023-12-31", "accn": "0000000000-24-000001"}]}
        return {"entityName": "Example SE", "cik": 1, "facts": {"ifrs-full": {k: {"units": f(v)} for k, v in vals.items()}}}

    def test_build_inject_record(self):
        import random as _r
        import filing_structure, injector, normalize, statement_builder
        tree = {"Assets": [("CurrentAssets", 1), ("PropertyPlantAndEquipment", 1), ("Goodwill", 1)],
                "CurrentAssets": [("Inventories", 1), ("TradeAndOtherCurrentReceivables", 1), ("CashAndCashEquivalents", 1)],
                "EquityAndLiabilities": [("CurrentLiabilities", 1), ("NoncurrentPortionOfNoncurrentBorrowings", 1), ("Equity", 1)],
                "CurrentLiabilities": [("TradeAndOtherCurrentPayables", 1)],
                "Equity": [("IssuedCapital", 1), ("RetainedEarnings", 1), ("TreasuryShares", -1)]}
        orig = filing_structure.balance_sheet_tree
        filing_structure.balance_sheet_tree = lambda cik, accn, framework="us-gaap": tree
        try:
            bs = statement_builder.build_balance_sheet_from_filing(self._facts(), 2023, "1", framework="ifrs")
        finally:
            filing_structure.balance_sheet_tree = orig
        self.assertIsNotNone(bs)
        self.assertEqual(bs["unit"], "EUR millions")
        bs = normalize.normalize_statement(bs)
        self.assertTrue(injector.check_reconciles(bs), bs["rows"])
        ts = next(r for r in bs["rows"] if r["concept"] == "ifrs-full:TreasuryShares")
        self.assertEqual(ts["value"], -50)
        debt = next(r for r in bs["rows"] if r["concept"] == "ifrs-full:NoncurrentPortionOfNoncurrentBorrowings")
        self.assertEqual(debt["section"], "NoncurrentLiabilities")

        with open(os.path.join(ROOT, "rulebook_ifrs.json")) as fh:
            rules = {r["rule_id"].split("_")[0]: r for r in json.load(fh)["rules"]}
        saved, injector._RESOLVER = injector._RESOLVER, None
        try:
            for rid in ("I01", "I11"):
                mod, meta = injector.inject(bs, rules[rid], _r.Random(0))
                self.assertIsInstance(meta, dict, meta)
                self.assertTrue(injector.check_reconciles(mod), rid)
                rec = injector.build_record(bs, rules[rid], mod, meta, f"IFRS-{rid}")
                self.assertEqual(rec["ground_truth_citations"]["asc_full"], rules[rid]["citation"]["asc"])
                self.assertNotIn("ASC", rec["gt_transaction_data"])
                self.assertIn("iso4217:EUR", json.dumps(rec["gt_xbrl_json"]))
        finally:
            injector._RESOLVER = saved


class Snapshot(unittest.TestCase):
    def test_trim_keeps_only_annual_forms_and_years(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from fetch_raw import trim
        facts = {"cik": 1, "entityName": "X", "facts": {"ifrs-full": {"Assets": {"units": {"EUR": [
            {"val": 1, "fy": 2022, "fp": "FY", "form": "20-F", "end": "2022-12-31"},
            {"val": 2, "fy": 2022, "fp": "Q2", "form": "6-K", "end": "2022-06-30"},
            {"val": 3, "fy": 2015, "fp": "FY", "form": "20-F", "end": "2015-12-31"}]}}}}}
        got = trim(facts, ("20-F", "40-F"), [2021, 2022, 2023])
        self.assertEqual([f["val"] for f in got["facts"]["ifrs-full"]["Assets"]["units"]["EUR"]], [1])

    def test_ingest_reads_the_committed_snapshot(self):
        import edgar_ingest
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "raw_snapshot"))
        with open(os.path.join(d, "raw_snapshot", "companyfacts_CIK0000000042.json"), "w") as f:
            json.dump({"entityName": "Snap Co", "facts": {}}, f)
        saved, edgar_ingest.CACHE = edgar_ingest.CACHE, os.path.join(d, "raw")
        try:
            self.assertEqual(edgar_ingest.get_company_facts("42")["entityName"], "Snap Co")
        finally:
            edgar_ingest.CACHE = saved
