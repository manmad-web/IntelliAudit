#!/usr/bin/env python3
"""
Orchestrator: real EDGAR statements  ->  rule-first error injection  ->  benchmark.

    python3 scripts/build_benchmark.py                  # full config
    python3 scripts/build_benchmark.py --companies AAPL MSFT --years 2022 2023
    python3 scripts/build_benchmark.py --no-citations    # skip linkbase cross-check (offline/fast)

Outputs:
    data/clean/<CIK>_<YEAR>_BS.json      clean reconciling statements (real)
    data/benchmark/records.jsonl         one injected-error record per line
    data/benchmark/summary.json          counts + citation-tier breakdown
"""
import argparse, json, os, random, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from edgar_ingest import get_company_facts
from statement_builder import build_balance_sheet, build_income_statement, build_cash_flow
import injector

BUILDERS = [("BS", build_balance_sheet), ("IS", build_income_statement), ("CF", build_cash_flow)]


def main():
    cfg = json.load(open(os.path.join(ROOT, "config.json")))
    rulebook = json.load(open(os.path.join(ROOT, "rulebook.json")))
    ap = argparse.ArgumentParser()
    ap.add_argument("--companies", nargs="*", help="tickers to include (default: all)")
    ap.add_argument("--years", nargs="*", type=int, help="fiscal years (default: config)")
    ap.add_argument("--no-citations", action="store_true", help="skip linkbase cross-check")
    args = ap.parse_args()

    if args.no_citations:
        injector._RESOLVER = None

    companies = cfg["companies"]
    if args.companies:
        want = {c.upper() for c in args.companies}
        companies = [c for c in companies if c["ticker"] in want]
    years = args.years or cfg["fiscal_years"]
    rng = random.Random(cfg.get("seed", 13))

    clean_dir = os.path.join(ROOT, "data", "clean")
    bench_dir = os.path.join(ROOT, "data", "benchmark")
    os.makedirs(clean_dir, exist_ok=True); os.makedirs(bench_dir, exist_ok=True)

    records, tier = [], Counter()
    built, skipped_year = 0, 0
    for co in companies:
        try:
            facts = get_company_facts(co["cik"])
        except Exception as e:
            print(f"[skip] {co['ticker']}: EDGAR fetch failed: {e}"); continue
        for yr in years:
            for tag, build in BUILDERS:
                stmt = build(facts, yr)
                if not stmt:
                    skipped_year += 1; continue
                stmt["ticker"] = co["ticker"]
                if not injector.check_reconciles(stmt):
                    print(f"[warn] {co['ticker']} FY{yr} {tag}: does not reconcile, skipping"); continue
                json.dump(stmt, open(os.path.join(clean_dir, f"{co['cik']}_{yr}_{tag}.json"), "w"), indent=2)
                built += 1
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
        "companies": [c["ticker"] for c in companies], "years": years,
        "clean_statements_built": built, "company_years_skipped": skipped_year,
        "records": len(records),
        "statement_type_breakdown": dict(Counter(r["metadata"]["statement_type"] for r in records)),
        "error_type_breakdown": dict(Counter(r["error_type"] for r in records)),
        "citation_tier_breakdown": dict(tier),
        "verifiable_error_pct": round(100 * sum(1 for r in records if r["self_check"]["error_breaks_reconciliation"]) / max(1, len(records)), 1),
    }
    json.dump(summary, open(os.path.join(bench_dir, "summary.json"), "w"), indent=2)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
