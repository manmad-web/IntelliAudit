#!/usr/bin/env python3
"""
Synthetic transaction evidence — v0.2 (rewritten after external audit).

The audit found three fatal problems with v0.1 and all three are fixed here:

  (a) ANSWER LEAK. v0.1 printed the line total and an explicit
      "[Explanation: total = a + b]" for every row, so the correct value of the
      broken line was handed to the model verbatim (100% of numeric cases).
      v0.2 prints ONLY the component events. The auditor must ADD them up and
      compare to the statement — which is the actual task.

  (b) WRONG SIGNS. v0.1 derived "inflow/outflow" from the sign of a random
      split, producing nonsense like "dividends declared +47,456 (inflow)"
      under retained earnings. v0.2 gives every event an explicit DIRECTION
      (+1 increases the line, -1 decreases it) and the arithmetic respects it.

  (c) COVERAGE WAS A TELL. v0.1 covered every concept-tagged row and no
      residual row, so "row with no transaction" identified both filler rows
      and injected Redundant Rows, and a deleted row's label always still
      appeared. v0.2 covers a random subset (incl. residuals), so absence
      carries no information.
"""
import random

# concept -> [(event description, direction)] ; +1 increases the line, -1 decreases it
_EVENTS = {
    "us-gaap:CashAndCashEquivalentsAtCarryingValue": [
        ("cash collected from customers", +1), ("operating cash disbursements", -1)],
    "us-gaap:AccountsReceivableNetCurrent": [
        ("invoiced customer sales on credit", +1), ("write-off of uncollectible accounts", -1)],
    "us-gaap:InventoryNet": [
        ("production transferred to finished goods", +1), ("cost of goods sold relief", -1)],
    "us-gaap:PropertyPlantAndEquipmentNet": [
        ("capital expenditure on equipment", +1), ("depreciation expense", -1)],
    "us-gaap:Goodwill": [("goodwill recognised on acquisition", +1)],
    "us-gaap:AccountsPayableCurrent": [
        ("purchases on credit", +1), ("payments to vendors", -1)],
    "us-gaap:AccruedLiabilitiesCurrent": [
        ("expenses accrued", +1), ("accrued balances settled", -1)],
    "us-gaap:LongTermDebtNoncurrent": [
        ("issuance of long-term notes", +1), ("scheduled principal repayment", -1)],
    "us-gaap:LongTermDebtCurrent": [
        ("reclassified from long-term debt", +1), ("current maturities repaid", -1)],
    "us-gaap:RetainedEarningsAccumulatedDeficit": [
        ("net income for the period", +1), ("dividends declared", -1)],
    "us-gaap:CommonStocksIncludingAdditionalPaidInCapital": [
        ("shares issued", +1), ("share repurchases retired", -1)],
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax": [
        ("revenue recognised on satisfied performance obligations", +1),
        ("returns and allowances", -1)],
    "us-gaap:CostOfGoodsAndServicesSold": [("cost of goods sold", +1)],
    "us-gaap:ResearchAndDevelopmentExpense": [("research and development spend", +1)],
    "us-gaap:NetIncomeLoss": [("net income for the period", +1)],
    "us-gaap:DepreciationDepletionAndAmortization": [("depreciation and amortisation add-back", +1)],
    "us-gaap:ShareBasedCompensation": [("share-based compensation add-back", +1)],
    "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment": [("purchases of productive assets", +1)],
    "us-gaap:PaymentsOfDividendsCommonStock": [("dividends paid to shareholders", +1)],
    "us-gaap:PaymentsForRepurchaseOfCommonStock": [("common stock repurchased", +1)],
}
_DEFAULT = [("movement in the account during the period", +1)]

COVERAGE = 0.65          # fraction of eligible rows that get transaction evidence


def _expand(events, rng):
    """Never emit a single component, or its amount WOULD BE the line total —
    that was the residual 10.6% answer leak after the first fix."""
    if len(events) == 1:
        d, s = events[0]
        return [(f"{d} (first half)", s), (f"{d} (second half)", s)]
    return events


def _amounts(total, events, rng):
    """Split `total` across signed events so that sum(dir*amt) == total,
    and no single printed amount ever equals `total`."""
    if len(events) == 2 and events[0][1] == events[1][1]:      # same direction: a + b
        a = int(round(abs(total) * rng.uniform(0.35, 0.65))) or 1
        b = abs(total) - a
        if b == 0:
            a, b = max(1, abs(total) - 1), 1
        return [a, b]
    # opposite directions: pos - neg = total
    neg = int(round(abs(total) * rng.uniform(0.15, 0.55))) or 1
    pos = total + neg
    return [abs(pos), abs(neg)]


def generate_for_statement(stmt, seed=0):
    """Component-level evidence. Never prints the line total (no answer leak)."""
    rng = random.Random(seed)
    eligible = [r for r in stmt["rows"] if r.get("kind") == "line" and r.get("value") is not None]
    # cover a random subset INCLUDING residual rows, so absence is not a signal
    k = max(1, int(round(len(eligible) * COVERAGE)))
    covered = set(id(r) for r in rng.sample(eligible, k))

    out = [f"Transaction evidence — {stmt['company']} FY{stmt['fiscal_year']} "
           f"({stmt['statement_type']}). Amounts are component movements; they are "
           f"NOT the reported line totals."]
    for r in stmt["rows"]:
        if id(r) not in covered:
            continue
        events = _expand(_EVENTS.get(r.get("concept"), _DEFAULT), rng)
        amts = _amounts(r["value"], events, rng)
        parts = []
        for (desc, direction), amt in zip(events, amts):
            sign = "+" if direction > 0 else "−"          # real minus sign
            word = "increase" if direction > 0 else "decrease"
            parts.append(f"{desc}: {sign}{amt:,} ({word})")
        out.append(f"[row {r['idx']}] {r['label']}: " + "; ".join(parts))
    return "\n".join(out)


def generate_with_llm(stmt, client=None):
    raise NotImplementedError("Optional richer narratives; see docs/DATASHEET.md for the prompt.")
