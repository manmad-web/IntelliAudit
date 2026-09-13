#!/usr/bin/env python3
"""
========================= PROVENANCE: NEW (integration glue) ==================
IntelliAudit-Bench original.
==============================================================================

eval_pipeline.py — a CITATION-SELECTOR sanity/upper-bound check. NOT a result.

READ THIS BEFORE QUOTING ANY NUMBER FROM HERE:

  * This does NOT run the capstone auditor. It runs only the Stage-1 citation
    *selector* (pipeline_citation, faithfully copied). No Stage 0, no detection,
    no LLM.
  * "concept-only" IS a legitimate heuristic number: best_topic given only the
    gold concept + statement type, topic-normalized on both sides.
  * "rulebook-oracle" and "candidate-coverage" are UPPER BOUNDS THAT LEAK THE
    LABEL. Because injection is rule-first, rule_id is the identity of the rule
    that DEFINES the citation; a picker that branches on rule_id is re-deriving
    the rulebook, so 100% is guaranteed before any auditing. Likewise the
    subject∪presentation union covers the rule's topic by construction. These
    show the answer is RECOVERABLE on this data — they are not findings and must
    never be reported as the pipeline's accuracy.

The REAL experiments the benchmark enables (not done here):
  1. Baseline: an independent blind LLM on exam.jsonl  → scripts/cross_check_llm.py
  2. Method:   the ACTUAL capstone run_pipeline (Stage 0 detect + Stage 1 cite)
               on exam.jsonl. Note: Stage 0 abstains on classification/fabricated
               errors (~62%), so it cannot supply the violation signal for most
               citation-relevant rows today — that gap is the honest open problem.
"""
import collections, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src")); sys.path.insert(0, HERE)
import pipeline_citation as pc
from adapter import iab_to_item
RECORDS = os.path.join(ROOT, "data", "benchmark", "records.jsonl")
LABEL_LEAKING_RULES = {"R03", "R09", "R10", "R11"}   # recognition/measurement → subject


def norm(x):
    return pc.family(pc.topic_of(x)) if x else None


def main():
    recs = [json.loads(l) for l in open(RECORDS)]
    agg = collections.Counter(); n = 0
    for r in recs:
        item = iab_to_item(r); concept, stype = item["gold_concept"], item["statement_type"]
        gt = norm(r["ground_truth_citations"]["asc_full"].replace("ASC ", ""))

        best = norm(pc.best_topic(concept, stype))                       # heuristic, honest
        cands = {norm(t) for t in pc.candidate_topics(concept, stype)}   # UPPER BOUND (by construction)
        rid = r["rule_id"].split("_")[0]                                 # <-- LEAKS the label
        oracle = norm(pc.subject_topic(concept)) if rid in LABEL_LEAKING_RULES \
            else norm(pc.presentation_citation(stype))

        agg["concept_only"] += int(best == gt)
        agg["rulebook_oracle_LEAKS_LABEL"] += int(oracle == gt)
        agg["candidate_coverage_UPPER_BOUND"] += int(gt in cands)
        n += 1

    print(f"CITATION-SELECTOR CHECK on {n} records (NOT the auditor, NOT a result)\n")
    print(f"  concept-only (honest heuristic)      : {100*agg['concept_only']/n:5.1f}%")
    print(f"  rulebook-oracle  [LEAKS rule_id]     : {100*agg['rulebook_oracle_LEAKS_LABEL']/n:5.1f}%   <- upper bound, not a finding")
    print(f"  candidate-coverage [by construction] : {100*agg['candidate_coverage_UPPER_BOUND']/n:5.1f}%   <- upper bound, not a finding")
    print(f"\n  Interpretation: the correct citation is RECOVERABLE on this data")
    print(f"  (AuditBench oracle was 26.2%). The pipeline's real accuracy must be")
    print(f"  measured by running the actual auditor + a blind LLM baseline — see docstring.")


if __name__ == "__main__":
    main()
