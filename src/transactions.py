#!/usr/bin/env python3
"""
Synthetic transaction generation (AuditBench-style). Real 10-Ks never publish
transaction-level ledgers, so we synthesize events that sum to each real line
value. This is DETERMINISTIC/template-based by default; set an LLM hook to make
the narratives richer.

Transactions are OPTIONAL for the citation task; they exist so numerical errors
are "detectable from evidence" and for AuditBench comparability.
"""
import random

_EVENTS = {
    "us-gaap:CashAndCashEquivalentsAtCarryingValue": ["cash collected from customers", "proceeds from investment sales", "operating cash outflows"],
    "us-gaap:AccountsReceivableNetCurrent": ["invoiced customer sales on credit", "write-off of uncollectible accounts"],
    "us-gaap:InventoryNet": ["production added to inventory", "cost of goods sold relief"],
    "us-gaap:PropertyPlantAndEquipmentNet": ["capital expenditure on equipment", "depreciation"],
    "us-gaap:AccountsPayableCurrent": ["purchases on credit", "payments to vendors"],
    "us-gaap:LongTermDebtNoncurrent": ["issuance of long-term notes", "scheduled principal repayment"],
    "us-gaap:RetainedEarningsAccumulatedDeficit": ["net income for the period", "dividends declared"],
}


def generate_for_statement(stmt, seed=0):
    rng = random.Random(seed)
    out = [f"Transactions for FY{stmt['fiscal_year']} ({stmt['company']}):"]
    for r in stmt["rows"]:
        if r.get("kind") != "line" or r.get("value") is None or not r.get("concept"):
            continue
        total = r["value"]
        events = _EVENTS.get(r["concept"], ["business activity contributing to the balance"])
        n = min(len(events), 2 + (abs(total) % 2))
        # split total into n plausible parts
        parts, rem = [], total
        for i in range(n - 1):
            p = int(rem * rng.uniform(0.3, 0.7)); parts.append(p); rem -= p
        parts.append(rem)
        lines = []
        for ev, amt in zip(events, parts):
            sign = "inflow" if amt >= 0 else "outflow"
            lines.append(f"{ev}: {amt:+,} ({sign})")
        out.append(f"[contributing to row {r['idx']}] {r['label']} | {total:,} [SEP] "
                   + "; ".join(lines) + f" [Explanation: {total:,} = " + " + ".join(str(p) for p in parts) + "]")
    return "\n".join(out)


# Hook: replace with a Claude/GPT call for richer narratives.
def generate_with_llm(stmt, client=None):
    raise NotImplementedError("Wire an LLM client here to produce richer transaction narratives.")
