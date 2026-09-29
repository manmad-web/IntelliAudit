#!/usr/bin/env python3
"""
Exam-only reference baselines for scripts/score_predictions.py.

Every prediction here is computed from data/benchmark/exam.jsonl alone. The
answer key is never opened. (The v0.3 version of this script read the answer
key — see results/legacy_v0.3/README.md.)

  results/pred_presentation_prior.jsonl
      Always "Incorrect"; cites the presentation paragraph most people would
      reach for first given only the statement type (210-10-45-1 / 606-10-25-23
      / 230-10-45-13). A floor: what knowing the statement type is worth.

  results/pred_identifiability_solver.jsonl
      scripts/identifiability_check.py's hand-written US-GAAP rule system. A
      ceiling for deterministic rules written by the benchmark's own authors;
      NOT a result for any pipeline.

Output rows: {exam_id, predicted_judgement, predicted_asc (null = abstain)}.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from identifiability_check import solve  # noqa: E402

exam = [json.loads(l) for l in open(os.path.join(ROOT, "data", "benchmark", "exam.jsonl"))]
PRIOR = {"BalanceSheet": "ASC 210-10-45-1", "IncomeStatement": "ASC 606-10-25-23", "CashFlow": "ASC 230-10-45-13"}


def prior(e):
    return {"exam_id": e["exam_id"], "predicted_judgement": "Incorrect",
            "predicted_asc": PRIOR[e["metadata"]["statement_type"]]}


def solver(e):
    asc = solve(e)
    return {"exam_id": e["exam_id"], "predicted_judgement": "Incorrect" if asc else None,
            "predicted_asc": asc}


os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
for name, fn in [("pred_presentation_prior.jsonl", prior), ("pred_identifiability_solver.jsonl", solver)]:
    with open(os.path.join(ROOT, "results", name), "w") as f:
        for e in exam:
            f.write(json.dumps(fn(e)) + "\n")
    print(f"  results/{name}: {len(exam)} rows")
