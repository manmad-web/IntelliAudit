#!/usr/bin/env python3
"""
Build the MULTI-ERROR split (US GAAP) from the committed clean statements.

    python3 scripts/build_multi.py            # -> data/benchmark_multi/

Separate from the single-error benchmark (data/benchmark/), which it does not
touch. Per real statement: MULTI_PER_STATEMENT items with 1-3 faults each
(see src/multi_error.py) plus one clean control. Same statements, same rules,
same evidence generator as the single-error set; only the composition differs.

Outputs: records.jsonl, exam.jsonl (opaque exam_id, form), answer_key.jsonl,
summary.json.
"""
import collections, hashlib, json, os, random, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import injector  # noqa: E402
from citation_resolver import CachedResolver  # noqa: E402
from multi_error import build_multi_control, build_multi_record  # noqa: E402
from normalize import normalize_statement  # noqa: E402

MULTI_PER_STATEMENT = 4
K_CHOICES = [1, 2, 2, 3, 3]        # the error count varies; 2-3 dominate
OUT = os.path.join(ROOT, "data", "benchmark_multi")
SALT = "intelliaudit-multi-v0.1"


def applicable(stmt, rules):
    out = []
    for r in rules:
        if stmt["statement_type"] not in r["statements"]:
            continue
        mod, _ = injector.inject(stmt, r, random.Random(0))
        if mod is not None:
            out.append(r)
    return out


def main():
    cfg = json.load(open(os.path.join(ROOT, "config.json")))
    rules = json.load(open(os.path.join(ROOT, "rulebook.json")))["rules"]
    injector._RESOLVER = CachedResolver()
    rng = random.Random(cfg.get("seed", 13) + 1000)
    recs = []
    for co in cfg["companies"]:
        for yr in cfg["fiscal_years"]:
            for tag in ("BS", "IS", "CF"):
                p = os.path.join(ROOT, "data", "clean", f"{co['cik']}_{yr}_{tag}.json")
                if not os.path.exists(p):
                    continue
                clean = normalize_statement(json.load(open(p)))
                if not injector.check_reconciles(clean):
                    continue
                rs = applicable(clean, rules)
                recs.append(build_multi_control(clean, f"IAM-{co['ticker']}-{yr}-{tag}-CONTROL-00"))
                for i in range(MULTI_PER_STATEMENT):
                    k = min(rng.choice(K_CHOICES), len(rs))
                    for _attempt in range(5):          # redraw if faults cancel each other
                        rec = build_multi_record(clean, rs, k, rng, f"IAM-{co['ticker']}-{yr}-{tag}-M{i:02d}")
                        if rec:
                            recs.append(rec)
                            break

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "records.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    from jsonl import gzip_copy
    gzip_copy(os.path.join(OUT, "records.jsonl"))

    # split: opaque ids, one version of a statement per form
    eid = lambda sid: "EXM-" + hashlib.sha256((SALT + sid).encode()).hexdigest()[:12]
    by_stmt = collections.defaultdict(list)
    for r in recs:
        m = r["metadata"]
        by_stmt[(m["cik"], m["fiscal_year"], m["statement_type"])].append(r["sample_id"])
    form = {}
    frng = random.Random(cfg.get("seed", 13))
    for key in sorted(by_stmt):
        sids = sorted(by_stmt[key]); frng.shuffle(sids)
        for i, s in enumerate(sids):
            form[s] = i
    exam, ans = [], []
    for r in recs:
        m = r["metadata"]
        exam.append({"exam_id": eid(r["sample_id"]), "form": form[r["sample_id"]],
                     "metadata": {x: m[x] for x in ("company", "cik", "fiscal_year", "statement_type", "period", "unit")},
                     "statement_text": r["modified_statement_text"], "transaction_data": r["gt_transaction_data"]})
        ans.append({"exam_id": eid(r["sample_id"]), "sample_id": r["sample_id"], "form": form[r["sample_id"]],
                    "record_type": r["record_type"], "general_judgement": r["general_judgement"],
                    "n_errors": r["n_errors"], "errors": r["errors"],
                    "corrected_statement_text": r["gt_table_text"], "self_check": r["self_check"]})
    for name, rows in (("exam.jsonl", sorted(exam, key=lambda e: e["exam_id"])),
                       ("answer_key.jsonl", sorted(ans, key=lambda e: e["exam_id"]))):
        with open(os.path.join(OUT, name), "w") as f:
            for x in rows:
                f.write(json.dumps(x) + "\n")

    errs = [e for r in recs for e in r["errors"]]
    summary = {
        "split": "multi-error (US GAAP)",
        "items": len(recs), "controls": sum(r["record_type"] == "control" for r in recs),
        "n_errors_distribution": dict(sorted(collections.Counter(r["n_errors"] for r in recs).items())),
        "errors_total": len(errs),
        "citable_errors": sum(bool(e["ground_truth_citations"].get("citable")) for e in errs),
        "items_with_2plus_citable": sum(sum(bool(e["ground_truth_citations"].get("citable")) for e in r["errors"]) >= 2
                                        for r in recs),
        "rule_breakdown": dict(sorted(collections.Counter(e["rule_id"].split("_")[0] for e in errs).items())),
        "error_type_breakdown": dict(collections.Counter(e["error_type"] for e in errs)),
        "forms": len(set(form.values())),
    }
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
