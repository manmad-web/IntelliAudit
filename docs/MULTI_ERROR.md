# Multi-error split (US GAAP)

`data/benchmark_multi/` — built by `python3 scripts/build_multi.py` from the same 1,989
real US GAAP statements, rules and evidence generator as the single-error benchmark, which it
does not change. Gate: `python3 scripts/check_multi.py`. Scoring:
`python3 scripts/score_multi.py <pred.jsonl> [--form N]`.

| | |
|---|---|
| items | 9,945 = 7,956 with faults + 1,989 clean controls |
| faults per item | 1 (1,725), 2 (3,301), 3 (2,930); the count is not given away |
| faults | 17,117, of which 7,481 citable |
| forms | 5, one version of each statement per form |

## Composition rules
- Each fault hits a different row; a row that absorbed a balanced entry (retained
  earnings, AOCI) cannot be another fault's target, but two balanced faults may both
  post to it (their effects add up).
- Measurement/recognition faults are applied first; the statement at that point is the
  company's ledger. Then subtotal-recomputing faults (moves, identity break), then the
  arithmetic faults that must stay unfooted, so no fault silently repairs another.
- Statement footing breaks **if and only if** an arithmetic (detection-only) fault is
  present (gate check 2): an arithmetic gate can find those and never the citable ones.
- Corrected statement = the clean one, plus the reclassification for a covenant-breach fault.

## What it tests that the single-error set cannot
Whether a pipeline stops after the first finding. The rule system in
`scripts/identifiability_check.py` finds all 7,481 citable faults (row-agnostic) with no
spurious citation; it does not locate rows and misses the 205 items whose faults are all
arithmetic. That is the ceiling for rules written by the benchmark authors, not a result.

## Prediction format
```json
{"exam_id": "EXM-…", "predicted_judgement": "Incorrect",
 "errors": [{"row": 12, "error_type": "Misclassification", "asc": "ASC 210-10-45-1"},
            {"row": 30, "error_type": "Numerical Error", "asc": null}]}
```
Errors are matched to gold on row (pre- or post-injection index). Reported: judgement
accuracy and false alarms, error-level P/R/F1, exact error-count rate, type accuracy,
citation recall/precision (row-matched and row-agnostic).

## For the capstone pipeline
`integration/adapter.py` already emits an `errors` list; feed each item's `errors` from
this answer key only at score time. Stage 0 should now report several findings per
item instead of the first one.
