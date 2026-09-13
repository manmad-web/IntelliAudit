#!/usr/bin/env python3
"""
Split the combined records into the three standard benchmark files, so the
CLEAN ground truth, the EXAM (errors, no answers), and the ANSWER KEY (the ASC
citations) live separately — the way a benchmark is distributed:

  data/benchmark/statements_clean.jsonl   ground truth, NO errors (one per stmt)
  data/benchmark/exam.jsonl               error-injected statements + txs, NO answers
  data/benchmark/answer_key.jsonl         judgement + error id + ASC citations

Physically separating the answer key prevents citation leakage and lets you hand
a model the exam without the key. records.jsonl (the joined view) is kept too.
"""
import json, os, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, "data", "benchmark")
recs = [json.loads(l) for l in open(os.path.join(BENCH, "records.jsonl"))]

# ── 1. clean ground-truth statements (dedup: one per company×year×statement) ──
clean = {}
for r in recs:
    m = r["metadata"]
    sid = f"{m['cik']}_{m['fiscal_year']}_{m['statement_type']}"
    if sid not in clean:
        clean[sid] = {
            "statement_id": sid,
            "metadata": {k: m[k] for k in ("company", "cik", "fiscal_year", "statement_type", "period", "unit", "source")},
            "statement_text": r["gt_table_text"],
            "xbrl_json": r["gt_xbrl_json"],
        }

# ── 2. exam (what the auditor sees — NO judgement, NO citation) ──────────────
exam = []
# ── 3. answer key (the graded answers — judgement + error + ASC) ─────────────
key = []
for r in recs:
    m = r["metadata"]
    exam.append({
        "sample_id": r["sample_id"],
        "metadata": {k: m[k] for k in ("company", "cik", "fiscal_year", "statement_type", "period", "unit")},
        "statement_text": r["modified_statement_text"],
        "transaction_data": r.get("gt_transaction_data", ""),
    })
    key.append({
        "sample_id": r["sample_id"],
        "general_judgement": r["general_judgement"],
        "rule_id": r["rule_id"],
        "error_type": r["error_type"],
        "error_identification": r["error_identification"],
        "ground_truth_citations": r["ground_truth_citations"],
        "corrected_statement_text": r["gt_table_text"],
        "injection_detail": r["injection_detail"],
        "self_check": r["self_check"],
    })


def dump(name, rows):
    p = os.path.join(BENCH, name)
    with open(p, "w") as f:
        for x in rows:
            f.write(json.dumps(x) + "\n")
    return p, len(rows)


for name, rows in [("statements_clean.jsonl", list(clean.values())),
                   ("exam.jsonl", exam), ("answer_key.jsonl", key)]:
    p, n = dump(name, rows)
    print(f"  {name:<26} {n:>5} rows")

# leakage guard on the exam
import re
leak = sum(1 for e in exam if re.search(r"ASC\s*\d", e["statement_text"] + e["transaction_data"]))
print(f"\nexam.jsonl ASC-leakage check: {leak} rows contain an ASC code (must be 0)")
