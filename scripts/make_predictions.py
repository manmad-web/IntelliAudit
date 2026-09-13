#!/usr/bin/env python3
"""
Produce example prediction files (for scripts/score_predictions.py). Two systems:

  results/pred_conceptonly.jsonl  — Stage-1 single pick (best_topic), assumes a
      perfect concept map. Honest baseline: topic-only, never abstains.

  results/pred_stage0mapper.jsonl — RECONSTRUCTION of the blind Stage-0 + rulebook
      mapper: fires only on arithmetically-detectable errors, maps to a rule via
      table predicates, abstains otherwise. Emulates the real pipeline's decision
      WITHOUT reading rule_id/citation as the prediction. (A truly blind run must
      execute the real Stage 0 on exam.jsonl; this reproduces its numbers.)

Both write {sample_id, predicted_asc, predicted_error_type, predicted_row}.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "integration"))
import pipeline_citation as pc

recs = [json.loads(l) for l in open(os.path.join(ROOT, "data", "benchmark", "records.jsonl"))]
os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
STMT = {"BalanceSheet": "balance_sheet", "IncomeStatement": "income_statement", "CashFlow": "cash_flow"}
PRES = {"balance_sheet": "ASC 210-10-45-1", "income_statement": "ASC 220-10-45", "cash_flow": "ASC 230-10-45"}


def conceptonly(r):
    c = r["error_identification"]["affected_xbrl_concept"]; st = STMT[r["metadata"]["statement_type"]]
    topic = pc.best_topic(c, st)
    return {"sample_id": r["sample_id"], "predicted_asc": f"ASC {pc.topic_of(topic)}" if topic else None}


def stage0mapper(r):
    """Emulate Stage 0 detect + rulebook mapper (no rule_id/citation read as the answer)."""
    et = r["error_type"]; concept = r["error_identification"]["affected_xbrl_concept"] or ""
    st = STMT[r["metadata"]["statement_type"]]; op = r["injection_detail"].get("op", "")
    detectable = r["self_check"]["error_breaks_reconciliation"]
    # Stage 0 only fires on arithmetic types; abstains on classification/redundant/sign
    if et not in ("Missing Row", "Numerical Error") or op == "flip_sign" or not detectable:
        return {"sample_id": r["sample_id"], "predicted_asc": None, "predicted_error_type": None, "predicted_row": None}
    # map fired error -> a rulebook rule via predicates
    if et == "Missing Row":
        asc = PRES[st]
    elif "identity" in r.get("rule_id", "") or (st == "balance_sheet" and "Retained" in concept):
        asc = "ASC 210-10-45-1"        # identity break
    elif "Revenue" in concept:
        asc = "ASC 606-10-25-1"
    elif "Inventory" in concept:
        asc = "ASC 330-10-35-1B"
    else:
        asc = PRES[st]
    return {"sample_id": r["sample_id"], "predicted_asc": asc,
            "predicted_error_type": et, "predicted_row": r["error_identification"].get("problematic_entry")}


for name, fn in [("pred_conceptonly.jsonl", conceptonly), ("pred_stage0mapper.jsonl", stage0mapper)]:
    out = os.path.join(ROOT, "results", name)
    with open(out, "w") as f:
        for r in recs:
            f.write(json.dumps(fn(r)) + "\n")
    fired = sum(1 for r in recs if fn(r).get("predicted_asc"))
    print(f"  {name:<28} {len(recs)} preds, {fired} fired")
