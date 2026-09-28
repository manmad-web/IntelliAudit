#!/usr/bin/env python3
"""
Supporting facts: the period-end review data an auditor would hold.

v0.3 attached a "Supporting facts" line ONLY to R09/R10/R11/R14 records, each
with a fixed phrase ("net realizable value is", "implied fair value of
goodwill", "Classification indicated by these tests", "performance obligation
unsatisfied"). An exam-only script that maps phrase -> paragraph and never
reads a number scored 455/492 (92.5%) on citation, and "facts present" alone
separated injected records from clean ones.

v0.4 is contrastive:
  * Every statement (clean controls included) gets CONSISTENT facts for a
    random half of its fact-bearing lines. A fact's presence says nothing.
  * The injected record's fact has exactly the same template as a consistent
    one. Only the numbers differ, so a system has to compare the fact with the
    statement (NRV vs carrying amount, fair value vs carrying amount, ...).
  * Decoys include the look-alike cases that are NOT violations under US GAAP
    (PP&E recoverable on undiscounted flows even though fair value is lower;
    a covenant breach waived for more than a year).
  * Two phrasings per fact kind.

Facts never print an ASC code, and never state the conclusion.
"""
import random

KIND_BY_CONCEPT = {
    "us-gaap:InventoryNet": "inventory",
    "us-gaap:Goodwill": "goodwill",
    "us-gaap:AvailableForSaleSecuritiesCurrent": "securities",
    "us-gaap:AvailableForSaleSecuritiesNoncurrent": "securities",
    "us-gaap:AvailableForSaleSecuritiesDebtSecuritiesCurrent": "securities",
    "us-gaap:AvailableForSaleSecuritiesDebtSecuritiesNoncurrent": "securities",
    "us-gaap:MarketableSecuritiesCurrent": "securities",
    "us-gaap:MarketableSecuritiesNoncurrent": "securities",
    "us-gaap:OperatingLeaseRightOfUseAsset": "lease",
    "us-gaap:FinanceLeaseRightOfUseAsset": "lease",
    "us-gaap:OperatingLeaseLiabilityNoncurrent": "lease",
    "us-gaap:FinanceLeaseLiabilityNoncurrent": "lease",
    "us-gaap:OperatingLeaseLiabilityCurrent": "lease",
    "us-gaap:FinanceLeaseLiabilityCurrent": "lease",
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "us-gaap:Revenues": "revenue",
    "us-gaap:AccountsReceivableNetCurrent": "receivable",
    "us-gaap:ReceivablesNetCurrent": "receivable",
    "us-gaap:PropertyPlantAndEquipmentNet": "ppe",
    "us-gaap:LongTermDebtNoncurrent": "debt",
    "us-gaap:DeferredIncomeTaxAssetsNet": "dta",
    "us-gaap:DeferredTaxAssetsNetNoncurrent": "dta",
    "us-gaap:ResearchAndDevelopmentExpense": "rnd",
    # IFRS edition: only kinds whose facts read the same under IFRS. Goodwill,
    # PP&E, DTA, debt and R&D facts are US-GAAP-worded (reporting-unit fair
    # value, undiscounted flows, valuation allowance, waiver timing, 730) and
    # need IFRS templates first (rulebook_ifrs.json status needs-ifrs-facts).
    "ifrs-full:Inventories": "inventory",
    "ifrs-full:TradeAndOtherCurrentReceivables": "receivable",
    "ifrs-full:CurrentTradeReceivables": "receivable",
    "ifrs-full:Revenue": "revenue",
    "ifrs-full:RevenueFromContractsWithCustomers": "revenue",
}

P_DECOY = 0.5


def _pct(rng, lo, hi):
    return rng.uniform(lo, hi)


def _up(v, rng, lo, hi):
    return v + max(1, int(round(abs(v) * _pct(rng, lo, hi))))


# ---------------------------------------------------------------- templates --
def _inventory(L, c, n, rng):
    return rng.choice([
        f"{L}: lower-of-cost-and-net-realizable-value review at period-end — carrying amount "
        f"{c:,}; estimated net realizable value {n:,}.",
        f"{L}: period-end valuation memo — inventories at cost {c:,}; estimated selling prices "
        f"less costs of completion, disposal and transportation {n:,}.",
    ])


def _goodwill(L, ca, fv, rng):
    return rng.choice([
        f"{L}: annual impairment test of the reporting unit to which this goodwill is assigned — "
        f"carrying amount of the reporting unit including goodwill {ca:,}; fair value of the "
        f"reporting unit {fv:,}.",
        f"{L}: impairment test at the annual testing date — reporting unit fair value {fv:,}; "
        f"reporting unit carrying amount {ca:,} (includes the goodwill shown).",
    ])


def _securities(L, ac, fv, rng):
    return rng.choice([
        f"{L}: debt securities classified as available-for-sale — amortized cost {ac:,}; "
        f"fair value at period-end (quoted and observable market prices) {fv:,}.",
        f"{L}: available-for-sale debt portfolio at period-end — fair value {fv:,}; "
        f"amortized cost basis {ac:,}.",
    ])


def _lease_tests(kind, rng):
    if kind == "operating":
        return "no", "no", int(_pct(rng, 18, 68)), int(_pct(rng, 30, 84)), "no"
    if rng.random() < 0.3:
        return "yes", "no", int(_pct(rng, 40, 70)), int(_pct(rng, 60, 85)), "no"
    if rng.random() < 0.5:
        return "no", "no", int(_pct(rng, 78, 96)), int(_pct(rng, 60, 88)), "no"
    return "no", "no", int(_pct(rng, 40, 70)), int(_pct(rng, 91, 99)), "no"


def _lease(L, tests, rng):
    own, opt, t, p, spec = tests
    return rng.choice([
        f"{L}: classification tests for the underlying leases — ownership transfers to the "
        f"lessee: {own}; purchase option reasonably certain to be exercised: {opt}; lease term "
        f"as % of remaining economic life: {t}%; present value of lease payments as % of fair "
        f"value of the underlying assets: {p}%; asset of a specialized nature: {spec}.",
        f"{L}: lease classification worksheet — transfer of title at end of term: {own}; "
        f"bargain/reasonably-certain purchase option: {opt}; term / economic life: {t}%; "
        f"PV of payments / fair value: {p}%; specialized asset: {spec}.",
    ])


def _revenue(L, x, z, rng):
    return rng.choice([
        f"{L}: cut-off review — consideration billed or received during the period for "
        f"performance obligations not yet satisfied at period-end {x:,}; of which recorded as "
        f"contract liabilities (deferred revenue) {z:,}.",
        f"{L}: period-end review of unsatisfied performance obligations — amounts invoiced for "
        f"goods and services not yet transferred to customers {x:,}; amount carried in contract "
        f"liabilities {z:,}.",
    ])


def _receivable(L, g, e, a, rng):
    return rng.choice([
        f"{L}: credit-loss review — gross receivables {g:,}; lifetime expected credit losses "
        f"estimated at period-end {e:,}; allowance for credit losses recorded {a:,}.",
        f"{L}: expected-credit-loss model output — amortized cost of receivables {g:,}; "
        f"expected credit losses {e:,}; allowance on the books {a:,}.",
    ])


def _ppe(L, ca, ucf, fv, rng):
    return rng.choice([
        f"{L}: one asset group within this line was tested after a triggering event (sustained "
        f"operating losses) — carrying amount of the asset group {ca:,}; sum of undiscounted "
        f"future cash flows {ucf:,}; fair value of the asset group {fv:,}. No impairment loss "
        f"was recorded.",
        f"{L}: long-lived asset review (asset group with a triggering event) — carrying amount "
        f"{ca:,}; undiscounted cash flows expected from use and disposal {ucf:,}; fair value "
        f"{fv:,}. No impairment loss was recorded.",
    ])


def _debt(L, v, status, rng):
    return rng.choice([
        f"{L} ({v:,}): at period-end the entity {status} Under the credit agreement a covenant "
        f"breach entitles the lenders to demand repayment.",
        f"{L} ({v:,}): covenant compliance review — {status} A breach makes the facility "
        f"callable by the lenders.",
    ])


_DEBT_OK = [
    "was in compliance with all financial covenants.",
    "breached the maximum leverage covenant; before the financial statements were issued the "
    "lenders waived the breach and their right to demand repayment for a period of more than "
    "twelve months from the balance-sheet date.",
]
_DEBT_BAD = [
    "breached the maximum leverage covenant; no waiver has been obtained and the lenders may "
    "demand repayment at any time.",
    "breached the minimum interest-cover covenant; the lenders waived their right to demand "
    "repayment for six months from the balance-sheet date only.",
]


def _dta(L, g, a, r, rng):
    return rng.choice([
        f"{L}: realizability assessment — gross deferred tax assets {g:,}; valuation allowance "
        f"recorded {a:,}; amount management concludes is more likely than not to be realized "
        f"{r:,}.",
        f"{L}: deferred tax asset review — gross balance {g:,}; allowance on the books {a:,}; "
        f"portion expected (more likely than not) to be realized {r:,}.",
    ])


def _rnd(L, total, exp, cap, rng):
    return rng.choice([
        f"{L}: research and development costs incurred in the period {total:,}; expensed "
        f"{exp:,}; capitalized to the balance sheet as development costs {cap:,}.",
        f"{L}: R&D cost analysis — total costs incurred {total:,}; charged to expense {exp:,}; "
        f"deferred as capitalized development costs {cap:,}.",
    ])


# ---------------------------------------------------------- fact builders --
def consistent_fact(kind, row, rng, label):
    """A fact that agrees with the line as shown (no violation)."""
    v = int(row["value"] or 0)
    if kind == "inventory" and v > 0:
        return _inventory(label, v, _up(v, rng, 0.04, 0.3), rng)
    if kind == "goodwill" and v > 0:
        ca = _up(v, rng, 0.5, 3.0)
        return _goodwill(label, ca, _up(ca, rng, 0.05, 0.4), rng)
    if kind == "securities" and v > 0:
        ac = v + rng.choice([-1, 1]) * max(1, int(round(v * _pct(rng, 0.005, 0.06))))
        return _securities(label, max(1, ac), v, rng)
    if kind == "lease" and v:
        cls = "finance" if "Finance" in (row.get("concept") or "") else "operating"
        return _lease(label, _lease_tests(cls, rng), rng)
    if kind == "revenue" and v > 0:
        x = max(1, int(round(v * _pct(rng, 0.005, 0.04))))
        return _revenue(label, x, x, rng)
    if kind == "receivable" and v > 0:
        e = max(1, int(round(v * _pct(rng, 0.005, 0.05))))
        return _receivable(label, v + e, e, e, rng)
    if kind == "ppe" and v > 0:
        ca = max(2, int(round(v * _pct(rng, 0.05, 0.25))))
        if rng.random() < 0.5:   # recoverable on undiscounted flows; fair value lower (no loss)
            return _ppe(label, ca, _up(ca, rng, 0.05, 0.4), ca - max(1, int(round(ca * _pct(rng, 0.05, 0.3)))), rng)
        return _ppe(label, ca, _up(ca, rng, 0.1, 0.6), _up(ca, rng, 0.02, 0.3), rng)
    if kind == "debt" and v > 0:
        return _debt(label, v, rng.choice(_DEBT_OK), rng)
    if kind == "dta" and v > 0:
        g = _up(v, rng, 0.05, 0.6)
        return _dta(label, g, g - v, v, rng)
    if kind == "rnd" and v < 0:
        return _rnd(label, abs(v), abs(v), 0, rng)
    return None


def violating_fact(kind, meta, row, rng, label):
    """The fact for the injected record. Same template, contradicting numbers."""
    orig, err = meta.get("original_value"), meta.get("erroneous_value")
    if kind == "inventory":
        return _inventory(label, err, orig, rng)
    if kind == "goodwill":
        d = err - orig
        ca = _up(err, rng, 0.5, 3.0)
        return _goodwill(label, ca, ca - d, rng)
    if kind == "securities":
        return _securities(label, err, orig, rng)
    if kind == "lease":
        cls = "finance" if "Finance" in (meta.get("row_concept") or "") else "operating"
        return _lease(label, _lease_tests(cls, rng), rng)
    if kind == "revenue":
        d = err - orig
        extra = max(1, int(round(orig * _pct(rng, 0.002, 0.02))))
        return _revenue(label, d + extra, extra, rng)
    if kind == "receivable":
        d = err - orig
        e = max(d + 1, int(round(orig * _pct(rng, 0.01, 0.05))))
        return _receivable(label, orig + e, e, e - d, rng)
    if kind == "ppe":
        d = err - orig
        ca = max(2 * d, int(round(err * _pct(rng, 0.05, 0.25))))
        ucf = ca - max(1, int(round(ca * _pct(rng, 0.05, 0.3))))
        return _ppe(label, ca, ucf, ca - d, rng)
    if kind == "debt":
        return _debt(label, int(row["value"]), rng.choice(_DEBT_BAD), rng)
    if kind == "dta":
        g = _up(err, rng, 0.05, 0.6)
        return _dta(label, g, g - err, orig, rng)
    if kind == "rnd":
        return _rnd(label, abs(orig), abs(err), abs(orig) - abs(err), rng)
    return None


def supporting_facts(shown, rng, labels, violation=None, no_decoy=()):
    """Fact lines for the statement as shown on the exam.

    labels     : {idx: caption as printed}
    violation  : (row_idx, kind, meta) for the injected record, or None
    no_decoy   : row idx values that must not get a consistent fact (the row a
                 non-fact rule changed: a consistent fact there would contradict
                 the changed number and look like a measurement fault)
    """
    lines, spare = [], []
    for r in shown["rows"]:
        if r.get("kind") != "line":
            continue
        kind = KIND_BY_CONCEPT.get(r.get("concept"))
        if violation and r["idx"] == violation[0]:
            t = violating_fact(violation[1], violation[2], r, rng, labels.get(r["idx"], r["label"]))
        elif kind and r["idx"] not in no_decoy and rng.random() < P_DECOY:
            t = consistent_fact(kind, r, rng, labels.get(r["idx"], r["label"]))
        else:
            t = None
            if kind and r["idx"] not in no_decoy:
                spare.append((kind, r))
        if t:
            lines.append((r["idx"], "- " + t))
    # A record with a violation always has a fact. So that "has facts" is not
    # a signal, every statement with a fact-bearing line shows at least one.
    if not lines and spare:
        kind, r = rng.choice(spare)
        t = consistent_fact(kind, r, rng, labels.get(r["idx"], r["label"]))
        if t:
            lines.append((r["idx"], "- " + t))
    lines = [t for _, t in sorted(lines)]
    text = "\n".join(lines)
    if "ASC" in text or "IAS " in text or "IFRS " in text:
        raise RuntimeError("supporting facts must not name a citation")
    return text
