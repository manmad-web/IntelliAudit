#!/usr/bin/env python3
"""
Regression gate for the failure modes found in the 2026-09 external audit.
Run after every rebuild. Exits non-zero if the benchmark has become guessable
or started leaking its own answers again.

    python3 scripts/check_triviality.py
"""
import collections, glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
recs = [json.loads(l) for l in open(os.path.join(ROOT, "data", "benchmark", "records.jsonl"))]
fails = []


def check(name, value, limit, worse="above"):
    bad = value > limit if worse == "above" else value < limit
    print(f"  {'FAIL' if bad else 'ok  '}  {name:<52} {value:>6.1f}%   (limit {limit}%)")
    if bad:
        fails.append(name)


print(f"Triviality / leakage gate — {len(recs)} records\n")

# 1 — citation guessable from (error type x statement type), citable cases only
cit = [r for r in recs if r["ground_truth_citations"].get("citable")]
if cit:
    m = collections.defaultdict(collections.Counter)
    for r in cit:
        m[(r["error_type"], r["metadata"]["statement_type"])][r["ground_truth_citations"]["asc_full"]] += 1
    guess = 100 * sum(c.most_common(1)[0][1] for c in m.values()) / len(cit)
    check("citation guessable from (err type x stmt type)", guess, 60)
print(f"        citable cases: {len(cit)} / {len(recs)}  "
      f"(rest are detection-only, no governing paragraph)")

# 2 — transactions restate the original value of the broken line
num = [r for r in recs if "original_value" in r.get("injection_detail", {})]
if num:
    leak = sum(1 for r in num
               if f'{r["injection_detail"]["original_value"]:,}' in r["gt_transaction_data"])
    check("numeric cases whose ORIGINAL value is in the evidence", 100 * leak / len(num), 5)

# 3 — deleted row still named in the evidence
miss = [r for r in recs if r["error_type"] == "Missing Row"]
if miss:
    still = sum(1 for r in miss
                if (r["injection_detail"].get("row_label") or "~") in r["gt_transaction_data"])
    check("deleted rows still named in the evidence", 100 * still / len(miss), 80)

# 4 — fabricated-row label diversity
fab = [r for r in recs if r["error_type"] == "Redundant Row"]
if fab:
    n = len(set(r["injection_detail"]["row_label"] for r in fab))
    print(f"  {'ok  ' if n >= 8 else 'FAIL'}  {'distinct fabricated labels':<52} {n:>6}     (min 8)")
    if n < 8:
        fails.append("fabricated label diversity")

# 5 — moved rows always land immediately after a subtotal
mv = [r for r in recs if r["error_type"] == "Misclassification"]
after_sub = 0
for r in mv:
    lines = r["modified_statement_text"].splitlines()
    tgt = r["injection_detail"].get("row_label")
    for i, ln in enumerate(lines):
        if tgt and tgt in ln and i > 0 and "Total" in lines[i - 1]:
            after_sub += 1
            break
if mv:
    check("moved rows sitting directly after a subtotal", 100 * after_sub / len(mv), 40)

# 6 — residual filler share of balance sheets
tot = fil = 0
for f in glob.glob(os.path.join(ROOT, "data", "clean", "*_BS.json")):
    s = json.load(open(f))
    ln = [r for r in s["rows"] if r.get("kind") == "line" and r.get("value")]
    tot += sum(abs(r["value"]) for r in ln)
    fil += sum(abs(r["value"]) for r in ln if r.get("residual"))
if tot:
    check("balance-sheet magnitude that is unnamed filler", 100 * fil / tot, 15)

# 7 — citation tier honesty (paragraph-level)
v = [r for r in recs if r["ground_truth_citations"]["citation_tier"] == "linkbase-verified"]
ok = sum(1 for r in v if any(re.sub(r"\(\(.*?\)\)", "", x).strip() == r["ground_truth_citations"]["asc_full"]
                             for x in r["ground_truth_citations"]["linkbase_reference_set"]))
print(f"  {'ok  ' if not v or ok == len(v) else 'FAIL'}  {'linkbase-verified holding at PARAGRAPH level':<52} "
      f"{(100*ok/len(v) if v else 100):>6.1f}%   (must be 100%)")
if v and ok != len(v):
    fails.append("citation tier honesty")

print()
if fails:
    print(f"GATE FAILED — {len(fails)} issue(s): {', '.join(fails)}")
    sys.exit(1)
print("GATE PASSED")
