#!/usr/bin/env python3
"""Issue #4: R09/R11/R14/R10 facts on the exam; R06 ≠ residual."""
import json, os, random, re, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import injector  # noqa: E402
from evidence import facts_for_exam  # noqa: E402

RULES = json.load(open(os.path.join(ROOT, "rulebook.json")))["rules"]
RULE = {r["rule_id"]: r for r in RULES}


def _load(*parts):
    with open(os.path.join(ROOT, "data", "clean", *parts)) as f:
        return json.load(f)


def _rule(prefix):
    return next(r for r in RULES if r["rule_id"].startswith(prefix))


class EvidenceTest(unittest.TestCase):
    def test_r09_names_unsatisfied_obligation_not_the_clean_total(self):
        stmt = _load("320193_2017_IS.json")
        rule = _rule("R09")
        mod, meta = injector.inject(stmt, rule, random.Random(0))
        self.assertIsInstance(meta, dict, meta)
        rec = injector.build_record(stmt, rule, mod, meta, "t")
        tx = rec["gt_transaction_data"]
        orig = meta["original_value"]
        delta = abs(meta["erroneous_value"] - orig)
        self.assertIn("performance obligation unsatisfied", tx)
        self.assertIn(f"{delta:,}", tx)
        self.assertNotIn("ASC", tx)
        # clean total is not given as a supporting fact
        facts = [ln for ln in tx.splitlines() if ln.startswith("Supporting facts")]
        self.assertTrue(facts)
        self.assertNotIn(f"{orig:,}", facts[0])

    def test_r11_gives_nrv_below_carrying(self):
        stmt = _load("320193_2015_BS.json")
        rule = _rule("R11")
        mod, meta = injector.inject(stmt, rule, random.Random(1))
        self.assertIsInstance(meta, dict, meta)
        rec = injector.build_record(stmt, rule, mod, meta, "t")
        facts = [ln for ln in rec["gt_transaction_data"].splitlines()
                 if ln.startswith("Supporting facts")]
        self.assertTrue(facts)
        m = re.search(r"net realizable value is ([\d,]+)", facts[0])
        self.assertIsNotNone(m, facts[0])
        nrv = int(m.group(1).replace(",", ""))
        self.assertLess(nrv, meta["erroneous_value"])
        self.assertNotEqual(nrv, meta["original_value"])
        self.assertNotIn("ASC", facts[0])

    def test_r14_trigger_event(self):
        stmt = _load("320193_2015_BS.json")
        rule = _rule("R14")
        mod, meta = injector.inject(stmt, rule, random.Random(2))
        if not isinstance(meta, dict):
            self.skipTest(f"no goodwill: {meta}")
        rec = injector.build_record(stmt, rule, mod, meta, "t")
        self.assertIn("triggering event", rec["gt_transaction_data"])
        self.assertIn("implied fair value", rec["gt_transaction_data"])
        facts = [ln for ln in rec["gt_transaction_data"].splitlines()
                 if ln.startswith("Supporting facts")][0]
        self.assertNotIn(f"{meta['original_value']:,}", facts)

    def test_r10_lease_class_fact(self):
        stmt = _load("789019_2021_BS.json")
        rule = _rule("R10")
        mod, meta = injector.inject(stmt, rule, random.Random(3))
        if not isinstance(meta, dict):
            self.skipTest(f"no lease line: {meta}")
        rec = injector.build_record(stmt, rule, mod, meta, "t")
        self.assertIn("Classification indicated by these tests", rec["gt_transaction_data"])
        self.assertNotIn("ASC", rec["gt_transaction_data"])

    def test_r06_not_a_residual_and_has_its_own_txs(self):
        stmt = _load("320193_2015_BS.json")
        rule = _rule("R06")
        mod, meta = injector.inject(stmt, rule, random.Random(4))
        self.assertIsInstance(meta, dict, meta)
        self.assertTrue(meta.get("fabricated"))
        self.assertNotIn("residual", meta["row_label"].lower())
        fab = next(r for r in mod["rows"] if r.get("fabricated"))
        self.assertEqual(fab["concept"], "us-gaap:FABRICATED")
        self.assertFalse(fab.get("residual"))
        residuals = [r for r in mod["rows"] if r.get("residual")]
        for r in residuals:
            self.assertIn("residual", r["label"].lower())
            self.assertNotEqual(r.get("concept"), "us-gaap:FABRICATED")
        rec = injector.build_record(stmt, rule, mod, meta, "t")
        self.assertIn(meta["row_label"], rec["gt_transaction_data"])
        self.assertIn("posting to this caption", rec["gt_transaction_data"])

    def test_facts_reject_citation_strings(self):
        with self.assertRaises(RuntimeError):
            # sanity: the helper itself refuses ASC if a future edit adds one
            from evidence import facts_for_exam as f
            text = f({"rule_id": "R09_x"}, None, None,
                     {"original_value": 100, "erroneous_value": 110, "row_label": "ASC 606-10-25-1 revenue"})
            # label can mention numbers; the citation regex is on ASC / 606-
            self.assertNotIn("ASC 606", text)


if __name__ == "__main__":
    unittest.main()
