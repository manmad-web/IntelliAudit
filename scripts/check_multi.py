#!/usr/bin/env python3
"""
Gate for the multi-error split (data/benchmark_multi/). Exits non-zero on failure.

    python3 scripts/check_multi.py
"""
import collections, json, os, re, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from identifiability_check import solve_all  # noqa: E402

B = os.path.join(ROOT, "data", "benchmark_multi")
recs = [json.loads(l) for l in open(os.path.join(B, "records.jsonl"))]
exam = [json.loads(l) for l in open(os.path.join(B, "exam.jsonl"))]
key = {k["exam_id"]: k for k in (json.loads(l) for l in open(os.path.join(B, "answer_key.jsonl")))}
DET_ONLY = ("R04", "R05", "R06", "R07", "R12")
fails = []


def check(name, ok, detail):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name:<62} {detail}")
    if not ok:
        fails.append(name)


print(f"Multi-error gate — {len(recs)} items\n")
inj = [r for r in recs if r["record_type"] == "injected"]

dup = sum(1 for r in inj if len({(e["affected_xbrl_concept"], e["affected_label"]) for e in r["errors"]}) != len(r["errors"]))
check("1 every fault in an item targets a different row", dup == 0, f"{dup} items share a row")

bad = 0
for r in inj:
    has_det = any(e["rule_id"].startswith(DET_ONLY) for e in r["errors"])
    if r["self_check"]["error_breaks_reconciliation"] != has_det:
        bad += 1
check("2 footing breaks iff an arithmetic (detection-only) fault is present", bad == 0, f"{bad} items violate it")

tells = re.compile(r"\bR\d\d_|IAM?-[A-Z]+-\d{4}|FABRICATED|\(residual\)|\[row \d+\]\s[A-Z]|ASC\s*\d")
n_t = sum(1 for e in exam if tells.search(json.dumps(e)))
check("3 exam items with an id / generator tell", n_t == 0, f"{n_t}")

counts = Counter(r["n_errors"] for r in recs)
top = max(counts.values()) / len(recs)
check("4 no single error count dominates (share of the modal count <= 40%)", top <= 0.40,
      f"{dict(sorted(counts.items()))}")

per = Counter((e["form"], e["metadata"]["cik"], e["metadata"]["fiscal_year"], e["metadata"]["statement_type"]) for e in exam)
check("5 max versions of one statement inside a form", max(per.values()) == 1, f"{max(per.values())}")

# 6 identifiability: every citable fault's paragraph is found from the exam alone
found = gold_n = spurious = fp = 0
for e in exam:
    pred = Counter(solve_all(e))                       # key not used here
    k = key[e["exam_id"]]
    gold = Counter(x["ground_truth_citations"]["asc_full"] for x in k["errors"]
                   if x["ground_truth_citations"].get("citable"))
    if k["general_judgement"] == "Correct":
        fp += bool(pred)
        continue
    found += sum((pred & gold).values()); gold_n += sum(gold.values())
    spurious += sum((pred - gold).values())
check("6 citable faults identifiable from the exam (rule system)", found == gold_n,
      f"{found}/{gold_n}; spurious {spurious}; false citations on controls {fp}")

print()
if fails:
    print(f"GATE FAILED — {', '.join(fails)}"); sys.exit(1)
print("GATE PASSED")
