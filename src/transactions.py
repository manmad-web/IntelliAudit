#!/usr/bin/env python3
"""
Synthetic transaction evidence.

The exam must not hand the auditor the line total, and every event must have a
real bookkeeping direction (+ increases the line, − decreases it).

Coverage is a random subset (including residual rows) so "no transaction" is
not a fingerprint for filler or for an injected row.
"""
import random
import re

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
    "us-gaap:Goodwill": [
        ("goodwill recognised on acquisition", +1), ("impairment / disposal of a reporting unit", -1)],
    "us-gaap:AccountsPayableCurrent": [
        ("purchases on credit", +1), ("payments to vendors", -1)],
    "us-gaap:AccruedLiabilitiesCurrent": [
        ("expenses accrued", +1), ("accrued balances settled", -1)],
    "us-gaap:LongTermDebtNoncurrent": [
        ("issuance of long-term notes", +1), ("scheduled principal repayment", -1)],
    "us-gaap:LongTermDebtCurrent": [
        ("reclassified from long-term debt", +1), ("current maturities repaid", -1)],
    "us-gaap:RetainedEarningsAccumulatedDeficit": [
        ("balance brought forward plus net income for the period", +1), ("dividends declared", -1)],
    "us-gaap:CommonStocksIncludingAdditionalPaidInCapital": [
        ("shares issued", +1), ("share repurchases retired", -1)],
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax": [
        ("revenue recognised on satisfied performance obligations", +1),
        ("returns and allowances", -1)],
    "us-gaap:SalesRevenueNet": [
        ("revenue recognised on satisfied performance obligations", +1),
        ("returns and allowances", -1)],
    "us-gaap:CostOfGoodsAndServicesSold": [
        ("cost of goods sold (purchases and conversion)", +1),
        ("inventory returned to stock / overhead credit", -1)],
    "us-gaap:CostOfRevenue": [
        ("cost of goods sold (purchases and conversion)", +1),
        ("inventory returned to stock / overhead credit", -1)],
    "us-gaap:ResearchAndDevelopmentExpense": [
        ("research and development spend", +1), ("grant / capitalisation credit", -1)],
    "us-gaap:SellingGeneralAndAdministrativeExpense": [
        ("selling, general and administrative spend", +1), ("cost recovery / reclass out", -1)],
    "us-gaap:NetIncomeLoss": [
        ("net income for the period", +1), ("loss components of the period", -1)],
    "us-gaap:DepreciationDepletionAndAmortization": [
        ("depreciation and amortisation add-back", +1), ("disposal-related reversal", -1)],
    "us-gaap:ShareBasedCompensation": [
        ("share-based compensation add-back", +1), ("forfeiture reversal", -1)],
    "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment": [
        ("purchases of productive assets", +1), ("proceeds reclassed against capex", -1)],
    "us-gaap:PaymentsOfDividendsCommonStock": [
        ("dividends paid to shareholders", +1), ("dividend payable reversal", -1)],
    "us-gaap:PaymentsForRepurchaseOfCommonStock": [
        ("common stock repurchased", +1), ("settlement / retire-share adjustment", -1)],
    "us-gaap:AvailableForSaleSecuritiesCurrent": [
        ("purchases of available-for-sale securities", +1), ("sales / maturities of AFS securities", -1)],
    "us-gaap:AvailableForSaleSecuritiesDebtSecuritiesCurrent": [
        ("purchases of available-for-sale securities", +1), ("sales / maturities of AFS securities", -1)],
    "us-gaap:MarketableSecuritiesCurrent": [
        ("purchases of marketable securities", +1), ("sales / maturities of marketable securities", -1)],
    "us-gaap:ReceivablesNetCurrent": [
        ("invoiced customer sales on credit", +1), ("write-off of uncollectible accounts", -1)],
    "us-gaap:AccountsPayableTradeCurrent": [
        ("purchases on credit", +1), ("payments to vendors", -1)],
    "us-gaap:Revenues": [
        ("revenue recognised on satisfied performance obligations", +1),
        ("returns and allowances", -1)],
    "us-gaap:IntangibleAssetsNetExcludingGoodwill": [
        ("intangible assets acquired", +1), ("amortization expense", -1)],
    "us-gaap:OperatingLeaseRightOfUseAsset": [
        ("right-of-use assets for new leases", +1), ("right-of-use asset amortization", -1)],
    "us-gaap:FinanceLeaseRightOfUseAsset": [
        ("right-of-use assets for new leases", +1), ("right-of-use asset amortization", -1)],
    "us-gaap:OperatingLeaseLiabilityNoncurrent": [
        ("lease liabilities for new leases", +1), ("reclassified to current portion", -1)],
    "us-gaap:OperatingLeaseLiabilityCurrent": [
        ("reclassified from non-current portion", +1), ("lease payments", -1)],
    "us-gaap:DeferredIncomeTaxAssetsNet": [
        ("deductible temporary differences originated", +1), ("temporary differences reversed", -1)],
    "us-gaap:TreasuryStockValue": [
        ("treasury shares reissued", +1), ("shares reacquired", -1)],
    "us-gaap:AccumulatedOtherComprehensiveIncomeLossNetOfTax": [
        ("unrealized gains and translation gains in other comprehensive income", +1),
        ("unrealized losses and translation losses in other comprehensive income", -1)],
    "us-gaap:ContractWithCustomerLiabilityCurrent": [
        ("cash collected in advance of transfer", +1), ("revenue recognised against deferred balances", -1)],
    "us-gaap:MarketableSecuritiesNoncurrent": [
        ("purchases of marketable securities", +1), ("sales / maturities of marketable securities", -1)],
    "us-gaap:AvailableForSaleSecuritiesNoncurrent": [
        ("purchases of available-for-sale securities", +1), ("sales / maturities of AFS securities", -1)],
    "us-gaap:IncomeTaxExpenseBenefit": [
        ("current and deferred tax expense", +1), ("tax credits and benefits", -1)],
    "us-gaap:DeferredRevenueCurrent": [
        ("cash collected in advance of transfer", +1), ("revenue recognised against deferred balances", -1)],
}

# Unknown / residual rows: a real credit and a real debit, never two +halves.
_DEFAULT = [
    ("other credits posted to the account", +1),
    ("other charges posted to the account", -1),
]

COVERAGE = 0.65
_PART = re.compile(r": ([+−-])([\d,]+) \((increase|decrease)\)")


def _expand(events, rng):
    """A single component would equal the line total — never emit just one."""
    if len(events) == 1:
        d, s = events[0]
        return [(f"{d} (first half)", s), (f"{d} (second half)", s)]
    return list(events)


def _forbidden(stmt):
    """Printed component amounts must not equal any line's reported value."""
    out = set()
    for r in stmt["rows"]:
        v = r.get("value")
        if r.get("kind") == "line" and v is not None:
            out.add(abs(int(v)))
            out.add(int(v))
    out.discard(0)
    return out


def _ok(amt, total, forbidden):
    if amt is None or amt <= 0:
        return False
    if amt == abs(int(total)):
        return False
    if amt in forbidden:
        return False
    return True


def _pair(total, d0, d1, rng, forbidden, contra=(0.15, 0.55)):
    """Positive a, b such that d0*a + d1*b == total, or None.

    contra bounds the smaller (offsetting) piece as a share of |total|.
    """
    total = int(total)
    bumps = [int(round(abs(total) * rng.uniform(*contra))) or 1 for _ in range(40)]
    bumps.extend(range(3, 60))

    if d0 == d1:
        if total == 0 or (total > 0) != (d0 > 0):
            return None
        mag = abs(total)
        for _ in range(40):
            a = int(round(mag * rng.uniform(0.35, 0.65))) or 1
            b = mag - a
            if _ok(a, total, forbidden) and _ok(b, total, forbidden):
                return [a, b]
        if mag > 2 and _ok(1, total, forbidden) and _ok(mag - 1, total, forbidden):
            return [1, mag - 1]
        return None

    # Mixed signs. Put the larger piece on the side that matches sign(total).
    # Identity: (+)*plus - minus = total  after mapping to event order.
    for bump in bumps:
        minus = abs(int(bump)) or 1
        plus = total + minus          # plus - minus = total
        if plus <= 0:
            minus = abs(total) + abs(int(bump))
            plus = total + minus
        plus, minus = abs(int(plus)), abs(int(minus))
        if not _ok(plus, total, forbidden) or not _ok(minus, total, forbidden):
            continue
        # d0=+1,d1=-1 => [plus, minus]; d0=-1,d1=+1 => [minus, plus]
        if d0 > 0:
            a, b = plus, minus
        else:
            a, b = minus, plus
        if d0 * a + d1 * b == total:
            return [a, b]
    return None


def _amounts(total, events, rng, forbidden, contra=(0.15, 0.55)):
    """Positive integer amounts, one per event, with sum(dir * amt) == total.

    No printed amount is 0, equals |total|, or equals another line total.
    Returns None if no safe split exists (caller skips the row).
    """
    if len(events) != 2:
        return None
    d0, d1 = events[0][1], events[1][1]
    return _pair(int(total), d0, d1, rng, forbidden, contra)


def _oriented(concept, value, events):
    """Expenses and cash outflows are presented as negative amounts.

    Their events are written for the magnitude ("cost of goods sold",
    "purchases of productive assets"). v0.3 applied them to the signed value,
    so a -214,137 cost of revenue became "+108,831 cost; -322,968 overhead
    credit". For a negative line the main event lowers the line and the
    contra event raises it.
    """
    if value < 0 and concept in _MAGNITUDE and events[0][1] > 0:
        return [(d, -s) for d, s in events]
    return events


# Concepts whose events describe the magnitude of an expense or outflow. Only
# these flip. Balances that are simply negative (AOCI, treasury stock, a net
# loss) keep their event directions.
_MAGNITUDE = {
    "us-gaap:CostOfGoodsAndServicesSold", "us-gaap:CostOfRevenue",
    "us-gaap:ResearchAndDevelopmentExpense", "us-gaap:SellingGeneralAndAdministrativeExpense",
    "us-gaap:IncomeTaxExpenseBenefit", "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
    "us-gaap:PaymentsOfDividendsCommonStock", "us-gaap:PaymentsForRepurchaseOfCommonStock",
}


def _fmt(direction, amt):
    sign = "+" if direction > 0 else "−"  # unicode minus
    word = "increase" if direction > 0 else "decrease"
    return f"{sign}{int(amt):,} ({word})"


def parse_signed_parts(line):
    """Return list of signed integer contributions from one evidence line."""
    out = []
    for sign, num, word in _PART.findall(line):
        amt = int(num.replace(",", ""))
        if sign in "-−" or word == "decrease":
            out.append(-amt)
        else:
            out.append(amt)
    return out


def generate_for_statement(stmt, seed=0, labels=None, skip=(), extra_forbidden=()):
    """Component-level evidence. Never prints the line total (no answer leak).

    Lines are keyed by account caption, not by row number. v0.3 printed
    "[row i]" from the clean statement, so after a row was moved, deleted or
    inserted the evidence row numbers stopped matching the exam statement,
    which located the injected row for 606/631 structural cases.

    labels : optional {idx: caption} (e.g. qualified captions for duplicates)
    skip   : row idx values to leave out
    extra_forbidden : further amounts no component may equal
    """
    rng = random.Random(seed)
    forbidden = _forbidden(stmt) | {abs(int(x)) for x in extra_forbidden if x is not None}
    eligible = [
        r for r in stmt["rows"]
        if r.get("kind") == "line" and r.get("value") not in (None, 0)
    ]
    if not eligible:
        return (
            f"Transaction evidence — {stmt['company']} FY{stmt['fiscal_year']} "
            f"({stmt['statement_type']}). Amounts are component movements; they are "
            f"NOT the reported line totals."
        )
    k = max(1, int(round(len(eligible) * COVERAGE)))
    k = min(k, len(eligible))
    covered = set(id(r) for r in rng.sample(eligible, k))

    out = [
        f"Transaction evidence — {stmt['company']} FY{stmt['fiscal_year']} "
        f"({stmt['statement_type']}). Amounts are component movements; they are "
        f"NOT the reported line totals. Signs are relative to the line as presented "
        f"(expenses and cash outflows are presented as negative amounts)."
    ]
    for r in stmt["rows"]:
        if id(r) not in covered or r["idx"] in skip:
            continue
        known = r.get("concept") in _EVENTS
        events = _oriented(r.get("concept"), r["value"], _expand(_EVENTS.get(r.get("concept"), _DEFAULT), rng))
        amts = _amounts(r["value"], events, rng, forbidden,
                        contra=(0.03, 0.25) if known else (0.15, 0.55))
        if not amts:
            continue
        parts = []
        signed = 0
        for (desc, direction), amt in zip(events, amts):
            parts.append(f"{desc}: {_fmt(direction, amt)}")
            signed += direction * int(amt)
        if signed != int(r["value"]):
            continue
        lab = (labels or {}).get(r["idx"], r["label"])
        out.append(f"[{lab}] " + "; ".join(parts))
    return "\n".join(out)


def generate_with_llm(stmt, client=None):
    raise NotImplementedError("Optional richer narratives; see docs/DATASHEET.md for the prompt.")
