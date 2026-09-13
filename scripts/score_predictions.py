#!/usr/bin/env python3
"""
score_predictions.py — the ONE honest evaluator.

Takes a predictions file that NEVER saw the answer key, and scores it against
answer_key.jsonl. Any system (blind LLM, Stage-0+mapper, full pipeline) produces
predictions in this format:

    {"sample_id": "...", "predicted_asc": "ASC 606-10-25-1" or null-to-abstain,
     "predicted_error_type": "Numerical Error" (optional),
     "predicted_row": 12 (optional)}

Reports the three numbers a reviewer wants, side by side:
  * ASC-full / subtopic / topic exact-match
  * error-type EM, row EM
  * precision (among the cases it answered), recall (over all), abstention rate

Usage:  python3 scripts/score_predictions.py results/pred_myrun.jsonl
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
from scorer import score_citation

KEY = os.path.join(ROOT, "data", "benchmark", "answer_key.jsonl")


def load_key():
    return {k["sample_id"]: k for k in (json.loads(l) for l in open(KEY))}


def main(pred_path):
    key = load_key()
    preds = [json.loads(l) for l in open(pred_path)]
    n = len(key)
    fired = 0
    hit = {"topic": 0, "subtopic": 0, "full": 0, "etype": 0, "row": 0}
    for p in preds:
        k = key.get(p["sample_id"])
        if not k:
            continue
        asc = p.get("predicted_asc")
        if not asc:                      # abstain
            continue
        fired += 1
        # STRICT: must match the GOVERNING citation (not just any valid ASC for the
        # concept). credit_linkbase_set=True would over-credit — wrong for a citation
        # benchmark whose point is the right rule for the violation.
        sc = score_citation(asc, k["ground_truth_citations"], credit_linkbase_set=False)
        hit["topic"] += sc["em_topic"]; hit["subtopic"] += sc["em_subtopic"]; hit["full"] += sc["em_full"]
        if p.get("predicted_error_type", "").strip().lower() == k["error_type"].lower():
            hit["etype"] += 1
        pe = k["error_identification"]
        valid = {pe.get("pre_inject_row"), pe.get("post_inject_row"), pe.get("problematic_entry")} - {None}
        if p.get("predicted_row") in valid:
            hit["row"] += 1

    ab = n - fired
    print(f"Scored {os.path.basename(pred_path)} vs answer_key ({n} records)\n")
    print(f"  fired (answered)   : {fired}   ({100*fired/n:.1f}%)")
    print(f"  abstained          : {ab}   ({100*ab/n:.1f}%)\n")
    print(f"  {'metric':<16}{'precision (of answered)':>26}{'recall (of all)':>20}")
    for m in ("topic", "subtopic", "full"):
        p_ = 100*hit[m]/fired if fired else 0
        r_ = 100*hit[m]/n
        print(f"  ASC {m:<12}{p_:>24.1f}%{r_:>19.1f}%")
    if any(p.get("predicted_error_type") for p in preds):
        print(f"  error-type EM   {100*hit['etype']/fired if fired else 0:>24.1f}%{100*hit['etype']/n:>19.1f}%")
    if any("predicted_row" in p for p in preds):
        print(f"  row EM          {100*hit['row']/fired if fired else 0:>24.1f}%{100*hit['row']/n:>19.1f}%")
    print("\n  Reading: precision = correct WHEN it answered; recall = correct over ALL")
    print("  1,089 (abstentions count against recall). Report all three ASC levels.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: score_predictions.py <predictions.jsonl>"); sys.exit(1)
    main(sys.argv[1])
