#!/usr/bin/env python3
"""Multi-error composition: distinct rows, faults don't repair each other, single split untouched."""
import json, os, random, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import injector  # noqa: E402
from multi_error import build_multi_record  # noqa: E402
from normalize import normalize_statement  # noqa: E402

RULES = json.load(open(os.path.join(ROOT, "rulebook.json")))["rules"]
DET = ("R04", "R05", "R06", "R07", "R12")


def _clean(name):
    with open(os.path.join(ROOT, "data", "clean", name)) as f:
        return normalize_statement(json.load(f))


class MultiError(unittest.TestCase):
    def test_properties_hold_over_many_draws(self):
        for name in ("320193_2019_BS.json", "104169_2023_BS.json", "789019_2020_IS.json", "1652044_2021_CF.json"):
            clean = _clean(name)
            rules = [r for r in RULES if clean["statement_type"] in r["statements"]]
            rng = random.Random(7)
            for i in range(12):
                rec = build_multi_record(clean, rules, 3, rng, f"t-{name}-{i}")
                if rec is None:
                    continue
                ids = {(e["affected_xbrl_concept"], e["affected_label"]) for e in rec["errors"]}
                self.assertEqual(len(ids), len(rec["errors"]))
                self.assertLessEqual(len(rec["errors"]), 3)
                has_det = any(e["rule_id"].startswith(DET) for e in rec["errors"])
                self.assertEqual(rec["self_check"]["error_breaks_reconciliation"], has_det,
                                 [e["rule_id"] for e in rec["errors"]])
                self.assertNotRegex(rec["gt_transaction_data"], r"ASC\s*\d|\[row \d+\]")

    def test_two_balanced_faults_accumulate_in_retained_earnings(self):
        clean = _clean("320193_2019_BS.json")
        rules = [r for r in RULES if r["rule_id"][:3] in ("R11", "R14")]
        rec = build_multi_record(clean, rules, 2, random.Random(1), "t-re")
        deltas = sum(e["injection_detail"]["offset_delta"] for e in rec["errors"])
        re_c = "us-gaap:RetainedEarningsAccumulatedDeficit"
        before = next(r["value"] for r in clean["rows"] if r.get("concept") == re_c)
        label = next(r["label"] for r in clean["rows"] if r.get("concept") == re_c)
        line = next(l for l in rec["modified_statement_text"].splitlines() if f": {label} |" in l)
        self.assertIn(f"{before + deltas:,}", line)
        self.assertFalse(rec["self_check"]["error_breaks_reconciliation"])


if __name__ == "__main__":
    unittest.main()
