#!/usr/bin/env python3
"""
========================= PROVENANCE: NEW (integration glue) ==================
IntelliAudit-Bench original. The eval runner that combines the two repos.
==============================================================================

eval_pipeline.py — run the PIPELINE's citation logic (OLD repo, vendored) on the
BENCHMARK records (NEW repo) and score with the BENCHMARK scorer (NEW repo).

This is the "combined system": it realizes the fix the live capstone pipeline is
missing — it POPULATES the candidate set (which is dead/empty in
full_pipeline today) by unioning:
    subject-matter topic (pipeline_citation)  ∪
    presentation topic   (pipeline_citation)  ∪
    real linkbase arcs   (IntelliAudit-Bench citation_resolver, the answer key's
                          own taxonomy engine, used here read-only as a candidate
                          source — NOT to peek at labels)

Then it scores three pickers against the benchmark ground truth:
    concept-only      (best_topic)          — what the pipeline does today
    violation-aware   (uses Stage-0 error type: recognition→subject, else present.)
    candidate-hit     (is the right ASC anywhere in the union?)   ← the ceiling

Run:  python3 integration/eval_pipeline.py
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, HERE)

import pipeline_citation as pc          # OLD repo (vendored)
from adapter import iab_to_item          # NEW glue
from scorer import score_citation        # NEW benchmark grader

# recognition/measurement rules → cite the subject-matter standard; else presentation
SUBJECT_PREF_RULES = {"R03", "R09", "R10", "R11"}

RECORDS = os.path.join(ROOT, "data", "benchmark", "records.jsonl")


def _taxonomy_topics(concept):
    """Real linkbase arc topics for a concept (uses the benchmark's own resolver,
    read-only, as an extra candidate source). Returns [] if offline."""
    try:
        from citation_resolver import CitationResolver
        global _RES
        try:
            _RES
        except NameError:
            _RES = CitationResolver()
        cites = _RES.citations((concept or "").replace("us-gaap:", ""))
        return [pc.topic_of(c.replace("ASC ", "")) for c in cites]
    except Exception:
        return []


def main(use_linkbase=True):
    recs = [json.loads(l) for l in open(RECORDS)]
    overall = collections.Counter()
    bytier = collections.defaultdict(collections.Counter)
    n = 0
    for r in recs:
        item = iab_to_item(r)
        concept, stype = item["gold_concept"], item["statement_type"]
        g = r["ground_truth_citations"]
        gt_topic = pc.family(pc.topic_of(g["asc_full"].replace("ASC ", "")))

        tax = _taxonomy_topics(concept) if use_linkbase else []
        best = pc.best_topic(concept, stype)                    # pipeline today
        cands = pc.candidate_topics(concept, stype, taxonomy_topics=tax)  # WIRED candidate set

        rid = r["rule_id"].split("_")[0]
        if rid in SUBJECT_PREF_RULES:
            va = pc.family(pc.subject_topic(concept)) or pc.family(best)
        else:
            va = pc.family(pc.topic_of(pc.presentation_citation(stype)))

        best_hit = int(pc.family(best) == gt_topic)
        va_hit = int(va == gt_topic)
        cand_hit = int(gt_topic in {pc.family(t) for t in cands})
        # also run the benchmark's hierarchical citation scorer on the best pick
        sc = score_citation(f"ASC {best}" if best else "", g)

        n += 1
        for bucket in (overall, bytier[g["citation_tier"]]):
            bucket["best"] += best_hit; bucket["va"] += va_hit; bucket["cand"] += cand_hit
            bucket["em_topic"] += sc["em_topic"]; bucket["n"] += 1

    def line(c):
        return (f"concept-only {100*c['best']/c['n']:5.1f}%  |  "
                f"violation-aware {100*c['va']/c['n']:5.1f}%  |  "
                f"candidate-hit {100*c['cand']/c['n']:5.1f}%")

    print(f"Combined system: PIPELINE citation logic on {n} BENCHMARK records "
          f"(gold concept, {'linkbase-unioned' if use_linkbase else 'no-linkbase'} candidates)\n")
    print(f"OVERALL   : {line(overall)}")
    print(f"\nReference — same logic on AuditBench: oracle over candidates = 26.2%\n")
    for tier in ("linkbase-verified", "expert-authored", "unresolved"):
        if tier in bytier:
            print(f"  {tier:<18}: {line(bytier[tier])}  (n={bytier[tier]['n']})")
    return {"n": n, "overall": dict(overall), "by_tier": {k: dict(v) for k, v in bytier.items()}}


if __name__ == "__main__":
    main(use_linkbase="--no-linkbase" not in sys.argv)
