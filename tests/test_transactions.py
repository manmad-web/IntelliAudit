#!/usr/bin/env python3
"""Issue #3: transactions are bookkeeping, not an answer leak."""
import json, os, random, re, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from transactions import (  # noqa: E402
    generate_for_statement, parse_signed_parts, _EVENTS, _fmt, _pair, _forbidden,
)


def _apple_bs():
    p = os.path.join(ROOT, "data", "clean", "320193_2015_BS.json")
    with open(p) as f:
        return json.load(f)


def _stmt(rows, **kw):
    base = {
        "company": "Test Co", "fiscal_year": 2015, "statement_type": "BalanceSheet",
        "rows": rows,
    }
    base.update(kw)
    return base


class TransactionsTest(unittest.TestCase):
    def test_dividends_decrease_retained_earnings(self):
        events = _EVENTS["us-gaap:RetainedEarningsAccumulatedDeficit"]
        self.assertEqual(events[1], ("dividends declared", -1))
        self.assertEqual(events[0][1], +1)
        self.assertIn("decrease", _fmt(-1, 100))
        self.assertIn("increase", _fmt(+1, 100))

    def test_writeoff_and_depreciation_decrease(self):
        self.assertEqual(_EVENTS["us-gaap:AccountsReceivableNetCurrent"][1][1], -1)
        self.assertEqual(_EVENTS["us-gaap:PropertyPlantAndEquipmentNet"][1][1], -1)
        self.assertIn("write-off", _EVENTS["us-gaap:AccountsReceivableNetCurrent"][1][0])
        self.assertIn("depreciation", _EVENTS["us-gaap:PropertyPlantAndEquipmentNet"][1][0])

    def test_components_sum_to_line_not_equal_the_total(self):
        stmt = _stmt([
            {"idx": 0, "label": "Cash", "kind": "line", "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
             "value": 21120, "section": "CurrentAssets"},
            {"idx": 1, "label": "AR", "kind": "line", "concept": "us-gaap:AccountsReceivableNetCurrent",
             "value": 16849, "section": "CurrentAssets"},
            {"idx": 2, "label": "RE", "kind": "line", "concept": "us-gaap:RetainedEarningsAccumulatedDeficit",
             "value": 92284, "section": "Equity"},
        ])
        # force full coverage by sampling seed until RE is present, or generate many seeds
        seen_re = False
        for seed in range(50):
            tx = generate_for_statement(stmt, seed=seed)
            self.assertNotIn("+- ", tx)
            self.assertNotRegex(tx, r"\+\-")
            totals = {21120, 16849, 92284}
            for line in tx.splitlines():
                if not line.startswith("[row"):
                    continue
                parts = parse_signed_parts(line)
                self.assertGreaterEqual(len(parts), 2, line)
                for p in parts:
                    self.assertNotIn(abs(p), totals, f"component {p} equals a line total in {line}")
                m = re.match(r"\[row (\d+)\]", line)
                idx = int(m.group(1))
                want = next(r["value"] for r in stmt["rows"] if r["idx"] == idx)
                self.assertEqual(sum(parts), want, line)
                if "Retained earnings" in line or idx == 2:
                    seen_re = True
                    self.assertIn("dividends declared", line)
                    self.assertIn("decrease", line)
                    self.assertIn("net income for the period", line)
        self.assertTrue(seen_re)

    def test_negative_residual_uses_real_signs(self):
        stmt = _stmt([
            {"idx": 0, "label": "Other equity, net (residual)", "kind": "line",
             "concept": None, "value": -400, "section": "Equity", "residual": True},
        ])
        tx = generate_for_statement(stmt, seed=1)
        self.assertIn("[row 0]", tx)
        line = [ln for ln in tx.splitlines() if ln.startswith("[row 0]")][0]
        self.assertEqual(sum(parse_signed_parts(line)), -400)
        self.assertIn("decrease", line)
        self.assertNotIn("+-", line)

    def test_zero_lines_are_not_covered(self):
        stmt = _stmt([
            {"idx": 0, "label": "Empty", "kind": "line", "concept": "us-gaap:Goodwill",
             "value": 0, "section": "NoncurrentAssets"},
            {"idx": 1, "label": "Cash", "kind": "line",
             "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
             "value": 50, "section": "CurrentAssets"},
        ])
        tx = generate_for_statement(stmt, seed=0)
        self.assertNotIn("[row 0]", tx)

    def test_apple_re_block_is_bookkeeping(self):
        stmt = _apple_bs()
        tx = generate_for_statement(stmt, seed=stmt["fiscal_year"])
        self.assertIn("component movements", tx)
        self.assertNotRegex(tx, r"\+\-")
        re_lines = [ln for ln in tx.splitlines() if "Retained earnings" in ln]
        if not re_lines:
            # 65% coverage may omit it on this seed; generate with a forced cover check via _pair
            self.skipTest("RE not in the 65% sample for this seed")
        line = re_lines[0]
        self.assertIn("dividends declared", line)
        self.assertIn("decrease", line)
        re_row = next(r for r in stmt["rows"] if r.get("concept") == "us-gaap:RetainedEarningsAccumulatedDeficit")
        self.assertEqual(sum(parse_signed_parts(line)), re_row["value"])

    def test_no_component_equals_any_apple_line_total(self):
        stmt = _apple_bs()
        forbidden = _forbidden(stmt)
        tx = generate_for_statement(stmt, seed=stmt["fiscal_year"])
        for line in tx.splitlines():
            if not line.startswith("[row"):
                continue
            for p in parse_signed_parts(line):
                self.assertNotIn(abs(p), forbidden)

    def test_zero_percent_real_numeric_leak_on_clean_folder(self):
        """A component amount must never equal the clean line that would be the answer.

        The old gate used a substring search, so orig=0 hit 'FY2020' and orig=10
        hit '[row 10]'. This test counts actual printed amounts.
        """
        import glob
        leaks = 0
        n = 0
        amt = re.compile(r"[+−-]([\d,]+) \((?:increase|decrease)\)")
        for path in glob.glob(os.path.join(ROOT, "data", "clean", "*_BS.json"))[:40]:
            with open(path) as f:
                stmt = json.load(f)
            tx = generate_for_statement(stmt, seed=stmt["fiscal_year"])
            printed = {int(m.replace(",", "")) for m in amt.findall(tx)}
            for r in stmt["rows"]:
                if r.get("kind") != "line" or r.get("value") in (None, 0):
                    continue
                n += 1
                if abs(int(r["value"])) in printed:
                    leaks += 1
        self.assertGreater(n, 50)
        self.assertEqual(leaks, 0, f"{leaks}/{n} line totals appear as a component amount")

    def test_header_states_amounts_are_not_totals(self):
        tx = generate_for_statement(_apple_bs(), seed=2015)
        self.assertIn("NOT the reported line totals", tx)

    def test_pair_never_returns_the_total(self):
        rng = random.Random(0)
        for total in (100, 92284, -400, 1, 12):
            got = _pair(total, +1, -1, rng, forbidden={abs(total), total, 50, 12})
            if got is None:
                continue
            a, b = got
            self.assertEqual(a - b, total)
            self.assertNotEqual(a, abs(total))
            self.assertNotEqual(b, abs(total))


if __name__ == "__main__":
    unittest.main()
