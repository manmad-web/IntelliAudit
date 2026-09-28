#!/usr/bin/env python3
"""v0.4 evidence: contrastive supporting facts, balanced injections, no tells."""
import json, os, random, re, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import injector  # noqa: E402
from evidence import consistent_fact, supporting_facts, violating_fact  # noqa: E402
from normalize import normalize_statement  # noqa: E402

RULES = json.load(open(os.path.join(ROOT, "rulebook.json")))["rules"]


def _load(name):
    with open(os.path.join(ROOT, "data", "clean", name)) as f:
        return normalize_statement(json.load(f))


def _rule(prefix):
    return next(r for r in RULES if r["rule_id"].startswith(prefix))


def _facts(rec):
    t = rec["gt_transaction_data"]
    return t.split("Supporting facts", 1)[1] if "Supporting facts" in t else ""


def _record(name, prefix, seed=0):
    stmt = _load(name)
    rule = _rule(prefix)
    mod, meta = injector.inject(stmt, rule, random.Random(seed))
    if not isinstance(meta, dict):
        raise unittest.SkipTest(f"{prefix} not applicable to {name}: {meta}")
    return stmt, rule, mod, meta, injector.build_record(stmt, rule, mod, meta, f"t-{prefix}")


class BalancedInjection(unittest.TestCase):
    def test_citable_rules_keep_the_statement_footing(self):
        """Arithmetic must not locate a citable fault (it did for every v0.3 move)."""
        cases = [("320193_2015_BS.json", p) for p in ("R01", "R02", "R03", "R11", "R14", "R15", "R17", "R18")]
        cases += [("320193_2017_IS.json", "R09"), ("320193_2017_IS.json", "R21"),
                  ("320193_2017_CF.json", "R08"), ("320193_2017_CF.json", "R16"),
                  ("104169_2023_BS.json", "R19")]
        for name, prefix in cases:
            with self.subTest(rule=prefix):
                try:
                    _, _, mod, _, rec = _record(name, prefix)
                except unittest.SkipTest:
                    continue
                self.assertTrue(injector.check_reconciles(mod), prefix)
                self.assertFalse(rec["self_check"]["error_breaks_reconciliation"], prefix)

    def test_detection_only_rules_break_footing(self):
        for prefix in ("R04", "R05", "R06", "R07", "R12"):
            with self.subTest(rule=prefix):
                _, _, mod, _, rec = _record("320193_2015_BS.json", prefix, seed=3)
                self.assertTrue(rec["self_check"]["error_breaks_reconciliation"], prefix)

    def test_measurement_offset_goes_to_retained_earnings(self):
        stmt, _, mod, meta, _ = _record("320193_2015_BS.json", "R11", seed=1)
        re_c = "us-gaap:RetainedEarningsAccumulatedDeficit"
        before = next(r["value"] for r in stmt["rows"] if r.get("concept") == re_c)
        after = next(r["value"] for r in mod["rows"] if r.get("concept") == re_c)
        self.assertEqual(after - before, meta["erroneous_value"] - meta["original_value"])

    def test_covenant_rule_leaves_statement_as_filed(self):
        stmt, _, mod, meta, rec = _record("104169_2023_BS.json", "R19")
        self.assertEqual(rec["modified_statement_text"], injector.to_auditbench_text(stmt))
        self.assertNotEqual(rec["gt_table_text"], rec["modified_statement_text"])
        self.assertIn("Long-term debt", rec["gt_table_text"])


class ContrastiveFacts(unittest.TestCase):
    def test_violation_and_decoy_share_a_template(self):
        """The violating fact must not be recognisable by wording alone."""
        rng = random.Random(0)
        row = {"idx": 1, "label": "Inventories", "value": 1000, "concept": "us-gaap:InventoryNet"}
        ok = consistent_fact("inventory", row, rng, "Inventories")
        bad = violating_fact("inventory", {"original_value": 900, "erroneous_value": 1000}, row, rng, "Inventories")
        strip = lambda t: re.sub(r"[\d,]+", "#", t)
        templates = {strip(consistent_fact("inventory", row, random.Random(s), "Inventories")) for s in range(20)}
        self.assertIn(strip(bad), templates)
        self.assertIn(strip(ok), templates)

    def test_inventory_fact_numbers(self):
        _, _, _, meta, rec = _record("320193_2015_BS.json", "R11", seed=1)
        line = next(l for l in _facts(rec).splitlines() if l.startswith("- Inventories"))
        nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", line)]
        self.assertEqual(nums[-2:], [meta["erroneous_value"], meta["original_value"]])

    def test_consistent_facts_are_not_violations(self):
        rng = random.Random(5)
        for _ in range(200):
            v = rng.randint(10, 10 ** 6)
            inv = consistent_fact("inventory", {"value": v}, rng, "I")
            c, n = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", inv)][-2:]
            self.assertLessEqual(c, n)
            gw = consistent_fact("goodwill", {"value": v}, rng, "G")
            nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", gw)]
            if "fair value of the reporting unit" in gw:
                self.assertGreater(nums[1], nums[0])
            else:
                self.assertGreater(nums[0], nums[1])

    def test_controls_carry_facts_too(self):
        stmt = _load("320193_2015_BS.json")
        rec = injector.build_control(stmt, "IA-AAPL-2015-BS-CONTROL-00")
        self.assertEqual(rec["general_judgement"], "Correct")
        self.assertIn("Supporting facts", rec["gt_transaction_data"])

    def test_no_citation_strings(self):
        stmt = _load("320193_2015_BS.json")
        caps = {r["idx"]: "ASC 606-10-25-1 revenue" for r in stmt["rows"]}
        with self.assertRaises(RuntimeError):
            for s in range(10):
                supporting_facts(stmt, random.Random(s), caps)


class NoGeneratorTells(unittest.TestCase):
    def test_fabricated_row_has_no_special_evidence(self):
        _, _, mod, meta, rec = _record("320193_2015_BS.json", "R06", seed=4)
        self.assertNotIn("posting to this caption", rec["gt_transaction_data"])
        self.assertNotIn(f"[{meta['row_label']}]", rec["gt_transaction_data"])
        self.assertEqual(meta["row_label"], meta["row_label"][:1].upper() + meta["row_label"][1:].lower())

    def test_captions_do_not_say_current(self):
        _, _, mod, meta, rec = _record("320193_2015_BS.json", "R01", seed=2)
        moved = next(r for r in mod["rows"] if r["label"] == meta["row_label"])
        self.assertEqual(moved["section"], "NoncurrentAssets")
        self.assertNotRegex(moved["label"].lower(), r"current")

    def test_no_residual_suffix_on_the_exam(self):
        _, _, _, _, rec = _record("320193_2017_IS.json", "R05", seed=0)
        self.assertNotIn("(residual)", rec["modified_statement_text"])
        self.assertNotIn("(residual)", rec["gt_transaction_data"])


class Normalization(unittest.TestCase):
    def test_treasury_sign_and_plug(self):
        s = _load("200406_2023_BS.json")
        ts = next(r for r in s["rows"] if r.get("concept") == "us-gaap:TreasuryStockValue")
        self.assertLess(ts["value"], 0)
        self.assertFalse(any(r.get("residual") and r["section"] == "Equity" for r in s["rows"]))
        self.assertTrue(injector.check_reconciles(s))

    def test_walmart_debt_is_under_non_current_liabilities(self):
        s = _load("104169_2023_BS.json")
        ltd = next(r for r in s["rows"] if r.get("concept") == "us-gaap:LongTermDebtNoncurrent")
        self.assertEqual(ltd["section"], "NoncurrentLiabilities")
        eq_header = next(i for i, r in enumerate(s["rows"]) if r.get("kind") == "header" and r["section"] == "Equity")
        self.assertLess(s["rows"].index(ltd), eq_header)

    def test_idempotent(self):
        a = _load("1045810_2016_BS.json")
        b = normalize_statement(json.loads(json.dumps(a)))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
