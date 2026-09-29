#!/usr/bin/env python3
"""
score_predictions.py — the one evaluator.

Takes a predictions file produced WITHOUT the answer key and scores it against
data/benchmark/answer_key.jsonl. Prediction rows (one JSON per line):

    {"exam_id": "EX-…",                       # (sample_id is accepted for v0.3 files)
     "predicted_judgement": "Correct" | "Incorrect" | null,
     "predicted_asc": "ASC 606-10-25-23" | null (abstain),
     "predicted_error_type": "Numerical Error",   # optional
     "predicted_row": 12}                        # optional

Reports:
  * judgement: accuracy, false-alarm rate on clean controls, miss rate on errors
  * citation over citable rows only: EM at topic / subtopic / full paragraph,
    precision (of answered) and recall (of all citable), abstention
  * error type and row over injected rows

Usage:  python3 scripts/score_predictions.py results/pred_myrun.jsonl [--form N]
"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
from scorer import citation_scored, score_citation

KEY = os.path.join(ROOT, "data", "benchmark", "answer_key.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pred_path")
    ap.add_argument("--form", type=int, help="score one exam form only (no cross-item diffing)")
    a = ap.parse_args()

    keys = [json.loads(l) for l in open(KEY)]
    if a.form is not None:
        keys = [k for k in keys if k.get("form") == a.form]
    by_eid = {k["exam_id"]: k for k in keys}
    by_sid = {k["sample_id"]: k for k in keys}
    preds = {}
    for l in open(a.pred_path):
        p = json.loads(l)
        k = by_eid.get(p.get("exam_id")) or by_sid.get(p.get("sample_id"))
        if k:
            preds[k["exam_id"]] = p

    cit = [k for k in keys if citation_scored(k["ground_truth_citations"])]
    inj = [k for k in keys if k["general_judgement"] == "Incorrect"]
    ctrl = [k for k in keys if k["general_judgement"] == "Correct"]

    # judgement
    def judged(k):
        p = preds.get(k["exam_id"], {})
        j = p.get("predicted_judgement")
        if j is None and p.get("predicted_asc"):
            j = "Incorrect"
        return (j or "").strip().lower()
    fa = sum(1 for k in ctrl if judged(k) == "incorrect")
    miss = sum(1 for k in inj if judged(k) != "incorrect")
    acc = (len(ctrl) - fa + len(inj) - miss) / max(1, len(keys))

    # citation
    fired = 0
    hit = {"topic": 0, "subtopic": 0, "full": 0}
    for k in cit:
        asc = preds.get(k["exam_id"], {}).get("predicted_asc")
        if not asc:
            continue
        fired += 1
        # strict: the governing paragraph, not any reference the concept carries
        sc = score_citation(asc, k["ground_truth_citations"], credit_linkbase_set=False)
        for m in hit:
            hit[m] += sc[f"em_{m}"]

    # detection detail
    et = row = 0
    for k in inj:
        p = preds.get(k["exam_id"], {})
        if (p.get("predicted_error_type") or "").strip().lower() == (k["error_type"] or "").lower():
            et += 1
        ei = k["error_identification"] or {}
        valid = {ei.get("pre_inject_row"), ei.get("post_inject_row"), ei.get("problematic_entry")} - {None}
        if p.get("predicted_row") in valid:
            row += 1

    n = len(cit)
    print(f"Scored {os.path.basename(a.pred_path)}: {len(preds)}/{len(keys)} items matched"
          + (f" (form {a.form})" if a.form is not None else "") + "\n")
    print(f"  judgement accuracy          {100*acc:6.1f}%")
    print(f"  false alarms on controls    {fa}/{len(ctrl)}  ({100*fa/max(1,len(ctrl)):.1f}%)")
    print(f"  missed errors               {miss}/{len(inj)}  ({100*miss/max(1,len(inj)):.1f}%)\n")
    print(f"  citation items {n}: answered {fired} ({100*fired/max(1,n):.1f}%), abstained {n-fired}")
    print(f"  {'':<14}{'precision (of answered)':>26}{'recall (of all)':>20}")
    for m in ("topic", "subtopic", "full"):
        print(f"  ASC {m:<10}{100*hit[m]/max(1,fired):>24.1f}%{100*hit[m]/max(1,n):>19.1f}%")
    if any(p.get("predicted_error_type") for p in preds.values()):
        print(f"\n  error-type EM (injected)    {100*et/max(1,len(inj)):6.1f}%")
    if any("predicted_row" in p for p in preds.values()):
        print(f"  row EM (injected)           {100*row/max(1,len(inj)):6.1f}%")
    print("\n  Citation is scored on citable rows only (detection-only faults and controls skipped).")


if __name__ == "__main__":
    main()
