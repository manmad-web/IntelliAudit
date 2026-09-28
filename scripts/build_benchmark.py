#!/usr/bin/env python3
"""
Orchestrator: real EDGAR statements  ->  rule-first error injection  ->  benchmark.

    python3 scripts/build_benchmark.py                  # full config
    python3 scripts/build_benchmark.py --companies AAPL MSFT --years 2022 2023
    python3 scripts/build_benchmark.py --no-citations    # skip linkbase cross-check (offline/fast)
    python3 scripts/build_benchmark.py --offline         # rebuild from committed data/clean + cached
                                                         # linkbase refs (no SEC / FASB network needed)

Outputs:
    data/clean/<CIK>_<YEAR>_BS.json      clean reconciling statements (real)
    data/benchmark/records.jsonl         one injected-error record per line
    data/benchmark/summary.json          counts + citation-tier breakdown
"""
import argparse, json, os, random, re, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from edgar_ingest import get_company_facts
from statement_builder import (build_balance_sheet, build_income_statement, build_cash_flow,
                               build_balance_sheet_from_filing)
from normalize import normalize_statement
import injector

BUILDERS = [("BS", build_balance_sheet), ("IS", build_income_statement), ("CF", build_cash_flow)]


def _name_ok(expected, entity):
    """Guard against a wrong CIK: the EDGAR entityName must share a word with the configured name."""
    stop = {"inc", "corp", "co", "company", "the", "plc", "ltd", "sa", "ag", "nv", "se", "group",
            "holdings", "corporation", "limited", "of", "and", "&"}
    tok = lambda x: {w for w in re.findall(r"[a-z0-9]+", (x or "").lower()) if w not in stop and len(w) > 1}
    return bool(tok(expected) & tok(entity))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json",
                    help="config file (config.json = the US-GAAP core set; configs/ifrs.json = IFRS edition)")
    ap.add_argument("--companies", nargs="*", help="tickers to include (default: all)")
    ap.add_argument("--years", nargs="*", type=int, help="fiscal years (default: config)")
    ap.add_argument("--no-citations", action="store_true", help="skip linkbase cross-check")
    ap.add_argument("--phase", type=int, default=1,
                    help="include companies up to this phase (phase 2 = banks/insurers/REITs/utilities; "
                         "needs templates that do not exist yet)")
    ap.add_argument("--offline", action="store_true",
                    help="build from committed data/clean/*.json and data/reference linkbase cache")
    args = ap.parse_args()
    cfg = json.load(open(os.path.join(ROOT, args.config)))
    framework = cfg.get("framework", "us-gaap")
    from frameworks import get as _fw
    fw = _fw(framework)
    rulebook = json.load(open(os.path.join(ROOT, fw["rulebook"])))
    if framework != "us-gaap":
        # The IFRS edition is a separate dataset. Balance sheets only for now:
        # the income-statement and cash-flow builders are us-gaap templates.
        global BUILDERS
        BUILDERS = [("BS", lambda f, y, c=None: build_balance_sheet_from_filing(f, y, c, framework=framework))]
        rulebook["rules"] = [r for r in rulebook["rules"] if r.get("status") == "ready"]
        if args.offline:
            injector._RESOLVER = None
        elif cfg.get("taxonomy_zip"):
            from citation_resolver import IfrsCitationResolver
            injector._RESOLVER = IfrsCitationResolver(cfg["taxonomy_zip"])
        else:
            injector._RESOLVER = None
            print("[warn] no IFRS taxonomy_zip in the config: citations will not be linkbase-checked")

    if args.no_citations:
        injector._RESOLVER = None
    elif args.offline and framework == "us-gaap":
        from citation_resolver import CachedResolver
        injector._RESOLVER = CachedResolver()

    companies = [c for c in cfg["companies"] if c.get("phase", 1) <= args.phase]
    if args.companies:
        want = {c.upper() for c in args.companies}
        companies = [c for c in companies if c["ticker"] in want]
    years = args.years or cfg["fiscal_years"]
    rng = random.Random(cfg.get("seed", 13))

    clean_dir = os.path.join(ROOT, fw["clean_dir"])
    bench_dir = os.path.join(ROOT, fw["out_dir"])
    os.makedirs(clean_dir, exist_ok=True); os.makedirs(bench_dir, exist_ok=True)

    records, tier = [], Counter()
    built, skipped_year = 0, 0
    for co in companies:
        facts = None
        if not args.offline:
            try:
                facts = get_company_facts(co["cik"])
            except Exception as e:
                print(f"[skip] {co['ticker']}: EDGAR fetch failed: {e}"); continue
            if not _name_ok(co["name"], facts.get("entityName")):
                print(f"[skip] {co['ticker']}: CIK {co['cik']} is {facts.get('entityName')!r}, "
                      f"not {co['name']!r} — fix the CIK in {args.config}"); continue
        for yr in years:
            for tag, build in BUILDERS:
                clean_path = os.path.join(clean_dir, f"{co['cik']}_{yr}_{tag}.json")
                if args.offline:
                    stmt = json.load(open(clean_path)) if os.path.exists(clean_path) else None
                elif framework == "us-gaap":
                    stmt = build(facts, yr)
                else:
                    stmt = build(facts, yr, co["cik"])
                if not stmt:
                    skipped_year += 1; continue
                stmt["ticker"] = co["ticker"]
                stmt = normalize_statement(stmt)
                if not injector.check_reconciles(stmt):
                    print(f"[warn] {co['ticker']} FY{yr} {tag}: does not reconcile, skipping"); continue
                json.dump(stmt, open(clean_path, "w"), indent=2)
                built += 1
                if cfg.get("controls_per_statement", 1):
                    rec = injector.build_control(stmt, f"IA-{co['ticker']}-{yr}-{tag}-CONTROL-00")
                    records.append(rec)
                    tier[rec["ground_truth_citations"]["citation_tier"]] += 1
                for rule in rulebook["rules"]:
                    if stmt["statement_type"] not in rule["statements"]:
                        continue
                    for k in range(cfg.get("n_per_rule_per_statement", 1)):
                        mod, meta = injector.inject(stmt, rule, rng)
                        if mod is None:
                            continue
                        sid = f"IA-{co['ticker']}-{yr}-{tag}-{rule['rule_id']}-{k:02d}"
                        rec = injector.build_record(stmt, rule, mod, meta, sid)
                        records.append(rec)
                        tier[rec["ground_truth_citations"]["citation_tier"]] += 1
        print(f"  {co['ticker']}: built BS/IS/CF through FY{max(years)}")

    with open(os.path.join(bench_dir, "records.jsonl"), "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    summary = {
        "framework": framework,
        "companies": [c["ticker"] for c in companies], "years": years,
        "clean_statements_built": built, "company_years_skipped": skipped_year,
        "records": len(records),
        "controls": sum(1 for r in records if r["record_type"] == "control"),
        "statement_type_breakdown": dict(Counter(r["metadata"]["statement_type"] for r in records)),
        "error_type_breakdown": dict(Counter(r["error_type"] or "None (control)" for r in records)),
        "rule_breakdown": dict(sorted(Counter((r["rule_id"] or "CONTROL").split("_")[0] for r in records).items())),
        "distinct_citable_paragraphs": sorted({r["ground_truth_citations"]["asc_full"] for r in records
                                               if r["ground_truth_citations"].get("citable")}),
        "citation_tier_breakdown": dict(tier),
        "injected_breaking_footing_pct": round(100 * sum(1 for r in records if r["record_type"] == "injected" and r["self_check"]["error_breaks_reconciliation"]) / max(1, sum(1 for r in records if r["record_type"] == "injected")), 1),
        "citable_breaking_footing_pct": round(100 * sum(1 for r in records if r["ground_truth_citations"].get("citable") and r["self_check"]["error_breaks_reconciliation"]) / max(1, sum(1 for r in records if r["ground_truth_citations"].get("citable"))), 1),
    }
    json.dump(summary, open(os.path.join(bench_dir, "summary.json"), "w"), indent=2)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
