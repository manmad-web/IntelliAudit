#!/usr/bin/env python3
"""
Split the combined records into the three benchmark files:

  data/benchmark/statements_clean.jsonl   ground truth, NO errors (one per stmt)
  data/benchmark/exam.jsonl               what the auditor sees — NO answers
  data/benchmark/answer_key.jsonl         judgement + error id + ASC citations

v0.4 exam changes (second audit):
  * Opaque ids. v0.3 exam ids were "IA-AAPL-2015-BS-R07_balance_sheet_identity_
    break-00": the rule name was in the question. Exam items now carry
    exam_id = "EX-" + sha256(salt + sample_id)[:12]; only the answer key maps
    exam_id -> sample_id.
  * Clean controls are exam items (judgement Correct), in the same format and
    with the same kind of evidence and supporting facts. v0.3's exam was 100%
    "Incorrect" and the clean file had no transactions, so "has evidence" meant
    "has an error".
  * Deterministic shuffle (sorted by exam_id), so file order says nothing.
  * form: every statement appears ~17 times on the exam (one per rule plus a
    control). Diffing those copies finds the injected row without any
    accounting. Each form holds at most one version of each statement; score a
    system on one form at a time, or give it items one at a time.
"""
import collections, hashlib, json, os, random, re

import argparse, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from frameworks import get as _fw  # noqa: E402
_ap = argparse.ArgumentParser()
_ap.add_argument("--config", default="config.json")
cfg = json.load(open(os.path.join(ROOT, _ap.parse_args().config)))
BENCH = os.path.join(ROOT, _fw(cfg.get("framework", "us-gaap"))["out_dir"])
SALT = str(cfg.get("exam_salt", "intelliaudit-v0.4"))
from jsonl import open_text  # noqa: E402
recs = [json.loads(l) for l in open_text(os.path.join(BENCH, "records.jsonl"))]


def exam_id(sid):
    return "EX-" + hashlib.sha256((SALT + sid).encode()).hexdigest()[:12]


def stmt_key(r):
    m = r["metadata"]
    return f"{m['cik']}_{m['fiscal_year']}_{m['statement_type']}"


# ── forms: at most one version of each statement per form ─────────────────
rng = random.Random(cfg.get("seed", 13))
form_of = {}
by_stmt = collections.defaultdict(list)
for r in recs:
    by_stmt[stmt_key(r)].append(r["sample_id"])
for k in sorted(by_stmt):
    sids = sorted(by_stmt[k])
    rng.shuffle(sids)
    for f, sid in enumerate(sids):
        form_of[sid] = f

# ── 1. clean ground-truth statements (one per company×year×statement) ─────
clean = {}
for r in recs:
    k = stmt_key(r)
    if k not in clean and r.get("record_type") == "control":
        m = r["metadata"]
        clean[k] = {
            "statement_id": k,
            "metadata": {x: m[x] for x in ("company", "cik", "fiscal_year", "statement_type", "period", "unit", "source")},
            "statement_text": r["gt_table_text"],
            "xbrl_json": r["gt_xbrl_json"],
        }

# ── 2. exam and 3. answer key ─────────────────────────────────────────────
exam, key = [], []
for r in recs:
    m = r["metadata"]
    eid = exam_id(r["sample_id"])
    exam.append({
        "exam_id": eid,
        "form": form_of[r["sample_id"]],
        "metadata": {x: m[x] for x in ("company", "cik", "fiscal_year", "statement_type", "period", "unit")},
        "statement_text": r["modified_statement_text"],
        "transaction_data": r.get("gt_transaction_data", ""),
    })
    key.append({
        "exam_id": eid,
        "sample_id": r["sample_id"],
        "record_type": r.get("record_type", "injected"),
        "form": form_of[r["sample_id"]],
        "general_judgement": r["general_judgement"],
        "rule_id": r["rule_id"],
        "error_type": r["error_type"],
        "error_identification": r["error_identification"],
        "ground_truth_citations": r["ground_truth_citations"],
        "corrected_statement_text": r["gt_table_text"],
        "injection_detail": r["injection_detail"],
        "self_check": r["self_check"],
    })
exam.sort(key=lambda e: e["exam_id"])
key.sort(key=lambda k: k["exam_id"])


def dump(name, rows):
    p = os.path.join(BENCH, name)
    with open(p, "w") as f:
        for x in rows:
            f.write(json.dumps(x) + "\n")
    return len(rows)


for name, rows in [("statements_clean.jsonl", list(clean.values())),
                   ("exam.jsonl", exam), ("answer_key.jsonl", key)]:
    print(f"  {name:<26} {dump(name, rows):>5} rows")

leak = sum(1 for e in exam if re.search(r"ASC\s*\d|\bR\d\d_", json.dumps(e)))
print(f"\nexam.jsonl leakage check: {leak} rows contain an ASC code or a rule id (must be 0)")
print(f"forms: {len(set(form_of.values()))} (max one version of a statement per form)")
