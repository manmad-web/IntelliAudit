#!/usr/bin/env python3
"""
Pull REAL financial data for real companies from SEC EDGAR XBRL (companyfacts).

We never fabricate the numbers: every line value comes from a company's actual
10-K facts. `companyfacts` is a flat {concept -> [facts]} map, so we select the
fiscal-year value for each concept ourselves. Ordering/sectioning is imposed by a
canonical statement template (statement_builder.py); full presentation-linkbase
fidelity is a documented TODO.
"""
import json, os, time, urllib.request

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
UA = "IntelliAudit Research contact@example.edu"   # SEC requires a real UA


def get_company_facts(cik: str, refresh: bool = False) -> dict:
    """Fetch + cache all XBRL facts for a company. cik: digits, zero-pad to 10."""
    padded = str(cik).zfill(10)
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"companyfacts_CIK{padded}.json")
    if os.path.exists(path) and not refresh:
        return json.load(open(path))
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = json.loads(urllib.request.urlopen(req, timeout=60).read())
    json.dump(data, open(path, "w"))
    time.sleep(0.2)  # be polite to SEC
    return data


def _days(f):
    from datetime import date
    try:
        s = date.fromisoformat(f["start"]); e = date.fromisoformat(f["end"])
        return (e - s).days
    except Exception:
        return None


def concept_value(facts: dict, concept: str, fiscal_year: int, unit: str = "USD", duration: bool = False):
    """
    Return the 10-K value for a us-gaap concept in a fiscal year, or None.
      duration=False  -> instant facts (balance sheet): take FY 10-K fact ending latest.
      duration=True   -> period facts (income stmt / cash flow): take the ANNUAL fact
                         (period span ~1 year), not a quarter/YTD.
    """
    name = concept.replace("us-gaap:", "")
    node = facts.get("facts", {}).get("us-gaap", {}).get(name)
    if not node:
        return None
    cands = []
    for u, flist in node.get("units", {}).items():
        if unit and u != unit:
            continue
        for f in flist:
            if not f.get("form", "").startswith("10-K"):
                continue
            if f.get("fy") == fiscal_year and f.get("fp") == "FY":
                if duration and "start" not in f:
                    continue
                if duration:
                    d = _days(f)
                    if d is None or d < 330 or d > 380:   # keep only ~annual periods
                        continue
                cands.append(f)
    if not cands:  # relaxed fallback by end-year
        for u, flist in node.get("units", {}).items():
            if unit and u != unit:
                continue
            for f in flist:
                if f.get("form", "").startswith("10-K") and str(f.get("end", "")).startswith(str(fiscal_year)):
                    if duration and (("start" not in f) or (_days(f) or 0) < 330 or (_days(f) or 999) > 380):
                        continue
                    cands.append(f)
    if not cands:
        return None
    best = max(cands, key=lambda f: (f.get("end", ""), _days(f) or 0))
    return {"value": best["val"], "end": best["end"], "start": best.get("start"),
            "accn": best.get("accn"), "form": best.get("form")}


def company_meta(facts: dict) -> dict:
    return {"company": facts.get("entityName"), "cik": str(facts.get("cik", "")).zfill(10)}


if __name__ == "__main__":
    f = get_company_facts("320193")
    print("Entity:", f.get("entityName"))
    for yr in (2020, 2024):
        v = concept_value(f, "us-gaap:AccountsReceivableNetCurrent", yr)
        print(f"  FY{yr} AR:", v)
