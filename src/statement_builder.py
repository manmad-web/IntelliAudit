#!/usr/bin/env python3
"""
Assemble a concept-tagged, internally-consistent balance sheet for a real company
and fiscal year, using REAL EDGAR values for each line and computed subtotals.

Design choices (documented for the paper):
  * Line values are the company's actual reported us-gaap facts.
  * Subtotals/totals are RECOMPUTED from the lines that were actually reported,
    so the clean statement always reconciles even when a company omits a template
    line. (The reported subtotal may differ slightly; we prefer internal
    consistency for a clean baseline. A presentation-linkbase-faithful variant is
    a TODO.)
  * A line concept absent from the filing that year is dropped, not zero-filled.
"""
from edgar_ingest import get_company_facts, concept_value, company_meta

# Canonical, ordered balance-sheet template: (label, concept, section, kind, sums)
BS_TEMPLATE = [
    ("Current assets:", None, "CurrentAssets", "header", None),
    ("Cash and cash equivalents", "us-gaap:CashAndCashEquivalentsAtCarryingValue", "CurrentAssets", "line", None),
    ("Short-term investments", "us-gaap:ShortTermInvestments", "CurrentAssets", "line", None),
    ("Accounts receivable, net", "us-gaap:AccountsReceivableNetCurrent", "CurrentAssets", "line", None),
    ("Inventories", "us-gaap:InventoryNet", "CurrentAssets", "line", None),
    ("Other current assets", "us-gaap:OtherAssetsCurrent", "CurrentAssets", "line", None),
    ("Total current assets", "us-gaap:AssetsCurrent", "CurrentAssets", "subtotal", "auto"),
    ("Non-current assets:", None, "NoncurrentAssets", "header", None),
    ("Property, plant and equipment, net", "us-gaap:PropertyPlantAndEquipmentNet", "NoncurrentAssets", "line", None),
    ("Operating lease right-of-use assets", "us-gaap:OperatingLeaseRightOfUseAsset", "NoncurrentAssets", "line", None),
    ("Goodwill", "us-gaap:Goodwill", "NoncurrentAssets", "line", None),
    ("Intangible assets, net", "us-gaap:IntangibleAssetsNetExcludingGoodwill", "NoncurrentAssets", "line", None),
    ("Long-term investments", "us-gaap:LongTermInvestments", "NoncurrentAssets", "line", None),
    ("Other non-current assets", "us-gaap:OtherAssetsNoncurrent", "NoncurrentAssets", "line", None),
    ("Total non-current assets", "us-gaap:AssetsNoncurrent", "NoncurrentAssets", "subtotal", "auto"),
    ("Total assets", "us-gaap:Assets", "Assets", "total", "auto_assets"),
    ("Current liabilities:", None, "CurrentLiabilities", "header", None),
    ("Accounts payable", "us-gaap:AccountsPayableCurrent", "CurrentLiabilities", "line", None),
    ("Accrued liabilities", "us-gaap:AccruedLiabilitiesCurrent", "CurrentLiabilities", "line", None),
    ("Deferred revenue, current", "us-gaap:ContractWithCustomerLiabilityCurrent", "CurrentLiabilities", "line", None),
    ("Long-term debt, current", "us-gaap:LongTermDebtCurrent", "CurrentLiabilities", "line", None),
    ("Operating lease liabilities, current", "us-gaap:OperatingLeaseLiabilityCurrent", "CurrentLiabilities", "line", None),
    ("Total current liabilities", "us-gaap:LiabilitiesCurrent", "CurrentLiabilities", "subtotal", "auto"),
    ("Non-current liabilities:", None, "NoncurrentLiabilities", "header", None),
    ("Long-term debt, non-current", "us-gaap:LongTermDebtNoncurrent", "NoncurrentLiabilities", "line", None),
    ("Operating lease liabilities, non-current", "us-gaap:OperatingLeaseLiabilityNoncurrent", "NoncurrentLiabilities", "line", None),
    ("Other non-current liabilities", "us-gaap:OtherLiabilitiesNoncurrent", "NoncurrentLiabilities", "line", None),
    ("Total non-current liabilities", "us-gaap:LiabilitiesNoncurrent", "NoncurrentLiabilities", "subtotal", "auto"),
    ("Total liabilities", "us-gaap:Liabilities", "Liabilities", "total", "auto_liab"),
    ("Stockholders' equity:", None, "Equity", "header", None),
    ("Common stock and additional paid-in capital", "us-gaap:CommonStocksIncludingAdditionalPaidInCapital", "Equity", "line", None),
    ("Retained earnings", "us-gaap:RetainedEarningsAccumulatedDeficit", "Equity", "line", None),
    ("Accumulated other comprehensive income (loss)", "us-gaap:AccumulatedOtherComprehensiveIncomeLossNetOfTax", "Equity", "line", None),
    ("Total stockholders' equity", "us-gaap:StockholdersEquity", "Equity", "subtotal", "auto"),
    ("Total liabilities and stockholders' equity", "us-gaap:LiabilitiesAndStockholdersEquity", "LiabilitiesAndEquity", "total", "auto_le"),
]

SUBTOTAL_CHILD_SECTIONS = {
    "us-gaap:AssetsCurrent": ["CurrentAssets"],
    "us-gaap:AssetsNoncurrent": ["NoncurrentAssets"],
    "us-gaap:LiabilitiesCurrent": ["CurrentLiabilities"],
    "us-gaap:LiabilitiesNoncurrent": ["NoncurrentLiabilities"],
    "us-gaap:StockholdersEquity": ["Equity"],
}


RESIDUAL_LABELS = {
    "CurrentAssets": "Other current assets, net (residual)",
    "NoncurrentAssets": "Other non-current assets, net (residual)",
    "CurrentLiabilities": "Other current liabilities, net (residual)",
    "NoncurrentLiabilities": "Other non-current liabilities, net (residual)",
    "Equity": "Other equity, net (residual)",
}


def _anchor(facts, concept, fy, scale):
    cv = concept_value(facts, concept, fy)
    return (round(cv["value"] / scale), cv["end"]) if cv else (None, None)


def build_balance_sheet(facts, fiscal_year, scale=1_000_000):
    """
    Build a canonical, RECONCILING balance sheet from real facts.
    Strategy: use the company's REAL reported subtotals/totals as anchors; template
    lines carry real values; a transparent residual line per section absorbs any
    template gap so every subtotal == sum(children) and Assets == Liab + Equity,
    with every number traceable to real reported data.
    """
    meta = company_meta(facts)

    # --- real reported anchors --------------------------------------------
    a_cur, end_date = _anchor(facts, "us-gaap:AssetsCurrent", fiscal_year, scale)
    assets, e2 = _anchor(facts, "us-gaap:Assets", fiscal_year, scale)
    l_cur, _ = _anchor(facts, "us-gaap:LiabilitiesCurrent", fiscal_year, scale)
    liab, _ = _anchor(facts, "us-gaap:Liabilities", fiscal_year, scale)
    equity, _ = _anchor(facts, "us-gaap:StockholdersEquity", fiscal_year, scale)
    le_total, e3 = _anchor(facts, "us-gaap:LiabilitiesAndStockholdersEquity", fiscal_year, scale)
    end_date = end_date or e2 or e3
    if assets is None or a_cur is None or le_total is None or equity is None:
        return None
    a_noncur = assets - a_cur
    if liab is None:
        liab = le_total - equity
    l_noncur = liab - l_cur if l_cur is not None else None
    if l_cur is None:               # split unknown -> put all liab as one section
        l_cur, l_noncur = liab, 0
    anchors = {
        "CurrentAssets": a_cur, "NoncurrentAssets": a_noncur,
        "CurrentLiabilities": l_cur, "NoncurrentLiabilities": l_noncur, "Equity": equity,
    }
    subtotal_reported = {
        "us-gaap:AssetsCurrent": a_cur, "us-gaap:AssetsNoncurrent": a_noncur,
        "us-gaap:LiabilitiesCurrent": l_cur, "us-gaap:LiabilitiesNoncurrent": l_noncur,
        "us-gaap:StockholdersEquity": equity,
    }
    total_reported = {"us-gaap:Assets": assets, "us-gaap:Liabilities": liab,
                      "us-gaap:LiabilitiesAndStockholdersEquity": le_total}

    # --- lay out rows, tracking per-section line sums ----------------------
    rows, idx = [], 0
    section_line_idx, section_line_sum = {}, {}
    for label, concept, section, kind, sums in BS_TEMPLATE:
        if kind == "header":
            rows.append({"idx": idx, "label": label, "section": section, "concept": None, "value": None, "kind": "header"}); idx += 1
            continue
        if kind == "line":
            cv = concept_value(facts, concept, fiscal_year)
            if cv is None:
                continue
            val = round(cv["value"] / scale)
            rows.append({"idx": idx, "label": label, "section": section, "concept": concept, "value": val, "kind": "line", "injectable": True});
            section_line_idx.setdefault(section, []).append(idx)
            section_line_sum[section] = section_line_sum.get(section, 0) + val
            idx += 1
        else:
            # inject residual line just before the subtotal/total, per section
            if section in anchors:
                resid = anchors[section] - section_line_sum.get(section, 0)
                if resid != 0 or not section_line_idx.get(section):
                    rows.append({"idx": idx, "label": RESIDUAL_LABELS[section], "section": section,
                                 "concept": None, "value": resid, "kind": "line", "injectable": False, "residual": True})
                    section_line_idx.setdefault(section, []).append(idx)
                    idx += 1
            rows.append({"idx": idx, "label": label, "section": section, "concept": concept,
                         "value": None, "kind": kind, "_sums_spec": sums}); idx += 1

    # --- resolve subtotal/total children + set REPORTED values -------------
    for r in rows:
        if r.get("kind") in ("subtotal", "total"):
            spec = r.pop("_sums_spec", None)
            if spec == "auto":
                r["sums"] = list(section_line_idx.get(r["section"], []))
                r["value"] = subtotal_reported.get(r["concept"])
            elif spec == "auto_assets":
                r["sums"] = [i for i in (_find(rows, "us-gaap:AssetsCurrent"), _find(rows, "us-gaap:AssetsNoncurrent")) if i is not None]
                r["value"] = total_reported["us-gaap:Assets"]
            elif spec == "auto_liab":
                r["sums"] = [i for i in (_find(rows, "us-gaap:LiabilitiesCurrent"), _find(rows, "us-gaap:LiabilitiesNoncurrent")) if i is not None]
                r["value"] = total_reported["us-gaap:Liabilities"]
            elif spec == "auto_le":
                r["sums"] = [i for i in (_find(rows, "us-gaap:Liabilities"), _find(rows, "us-gaap:StockholdersEquity")) if i is not None]
                r["value"] = total_reported["us-gaap:LiabilitiesAndStockholdersEquity"]

    return {
        "company": meta["company"], "ticker": None, "cik": meta["cik"],
        "statement_type": "BalanceSheet", "fiscal_year": fiscal_year,
        "period": end_date, "unit": "USD millions", "source": "SEC EDGAR companyfacts (real 10-K)",
        "rows": rows,
        "identities": [{"lhs": "us-gaap:Assets", "rhs": ["us-gaap:LiabilitiesAndStockholdersEquity"], "name": "accounting_equation"}],
    }


def _find(rows, concept):
    for r in rows:
        if r.get("concept") == concept:
            return r["idx"]
    return None


def _recompute(rows):
    by_idx = {r["idx"]: r for r in rows}
    for r in rows:
        if r.get("kind") in ("subtotal", "total") and r.get("sums"):
            r["value"] = sum(by_idx[c]["value"] for c in r["sums"] if by_idx[c].get("value") is not None)


if __name__ == "__main__":
    f = get_company_facts("320193")
    bs = build_balance_sheet(f, 2023)
    print(bs["company"], bs["period"], "| rows:", len(bs["rows"]))
    for r in bs["rows"]:
        v = "" if r["value"] is None else f"{r['value']:>12,}"
        print(f"  [{r['idx']:>2}] {r['label']:<45} {v}   {r['concept'] or ''}")
