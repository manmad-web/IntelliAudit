#!/usr/bin/env python3
"""
Regenerate data/dataset_card.json and data/benchmark/PREVIEW.txt from the
current build. Facts only: every count comes from records.jsonl / summary.json /
rulebook.json, so the card cannot drift from the data (v0.3's card was hand-
edited and still described the v0.1 schema).

    python3 scripts/make_dataset_card.py
"""
import collections, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = os.path.join(ROOT, "data", "benchmark")
summary = json.load(open(os.path.join(B, "summary.json")))
rules = json.load(open(os.path.join(ROOT, "rulebook.json")))
sys.path.insert(0, os.path.join(ROOT, "src"))
from jsonl import open_text  # noqa: E402
recs = [json.loads(l) for l in open_text(os.path.join(B, "records.jsonl"))]
exam = [json.loads(l) for l in open(os.path.join(B, "exam.jsonl"))]
key = {json.loads(l)["sample_id"]: json.loads(l) for l in open(os.path.join(B, "answer_key.jsonl"))}
n_rec, n_ctrl = len(recs), summary["controls"]

card = {
    "name": "IntelliAudit-Bench (US GAAP)",
    "version": rules["_meta"]["version"],
    "description": ("Standards-citation benchmark for financial-statement auditing. Real 10-K "
                    "statements (SEC EDGAR); one injected error per item or a clean control; "
                    "ledger evidence plus period-end supporting facts; the governing FASB ASC "
                    "paragraph as ground truth for citable faults."),
    "repository": "https://github.com/manmad-web/IntelliAudit",
    "framework": "US GAAP (FASB ASC). An IFRS edition is planned as a separate dataset; see docs/EXPANSION_PLAN.md.",
    "task": ("Given a statement and its evidence, judge Correct/Incorrect; if Incorrect, locate the "
             "error, name its type, and cite the governing ASC paragraph (or null when no single "
             "paragraph governs, e.g. an arithmetic slip)."),
    "license_and_terms": {
        "financial_values": "SEC EDGAR filings (US public domain).",
        "citations": "FASB ASC paragraph identifiers; linkbase cross-check uses the US-GAAP 2023 taxonomy (FASB terms).",
        "generated_content": "Injected errors, ledger evidence and supporting facts are produced by this repository's generator.",
    },
    "files": {
        "data/benchmark/exam.jsonl": f"{len(exam)} items — exam_id (opaque), form, metadata, statement_text, transaction_data. No labels.",
        "data/benchmark/answer_key.jsonl": f"{len(key)} rows — exam_id -> sample_id, judgement, rule, error identification, citation. Withheld.",
        "data/benchmark/statements_clean.jsonl": f"{summary['clean_statements_built']} clean statements.",
        "data/benchmark/records.jsonl": f"{n_rec} rows — exam and key joined (generator output).",
        "data/reference/us-gaap-2023_ref_cache.json": "concept -> ASC references from the FASB reference linkbase (offline rebuilds).",
    },
    "statistics": {
        "items": n_rec, "clean_controls": n_ctrl, "injected": n_rec - n_ctrl,
        "companies": summary["companies"], "fiscal_years": summary["years"],
        "statement_types": summary["statement_type_breakdown"],
        "error_types": summary["error_type_breakdown"],
        "rules": summary["rule_breakdown"],
        "citation_tiers": summary["citation_tier_breakdown"],
        "citable_items": sum(1 for r in recs if r["ground_truth_citations"].get("citable")),
        "distinct_citable_paragraphs": summary["distinct_citable_paragraphs"],
        "citable_items_breaking_footing_pct": summary["citable_breaking_footing_pct"],
        "exam_forms": len({e["form"] for e in exam}),
    },
    "error_rules": [{"rule_id": r["rule_id"], "error_type": r["error_type"], "statements": r["statements"],
                     "asc": r["citation"]["asc"], "citable": r["citation"]["citable"],
                     "clause": r["citation"].get("policy_clause"), "ledger": r.get("ledger", "clean"),
                     "supporting_fact": r.get("facts")} for r in rules["rules"]],
    "ground_truth_confidence": {
        "linkbase-verified": "the FASB reference linkbase attaches this exact paragraph to the affected concept",
        "expert-authored-UNVALIDATED": "chosen by docs/CITATION_POLICY.md; NOT yet reviewed by an accountant",
        "no-governing-paragraph": "detection-only fault; excluded from citation scoring",
        "no-error": "clean control",
    },
    "known_limitations": [
        "8 companies, 5 of them large-cap technology; no banks, insurers, utilities, REITs or energy.",
        "15 citable paragraphs. A hand-written rule system solves every citable item "
        "(scripts/identifiability_check.py): the citation task tests whether a system knows and "
        "applies these rules, not open-ended standards knowledge.",
        "Income-statement and cash-flow statements are still built from a fixed template; "
        "cash-flow filler is ~23% of line magnitude.",
        "Ledger evidence is two synthetic movements per line with no opening balance.",
        "No accountant has reviewed the expert-authored citations; the LLM cross-check has not been run on v0.4.",
        "Every statement appears in ~17 versions; score per form or item-by-item (docs/EVAL.md).",
    ],
    "evaluation": "docs/EVAL.md; scripts/score_predictions.py; regression gate scripts/check_triviality.py.",
}
json.dump(card, open(os.path.join(ROOT, "data", "dataset_card.json"), "w"), indent=1)

# PREVIEW: one item per rule, as the exam shows it, with its key
by_rule = collections.OrderedDict()
for r in sorted(recs, key=lambda r: r["sample_id"]):
    by_rule.setdefault((r["rule_id"] or "CONTROL").split("_")[0], r)
out = []
for rid, r in sorted(by_rule.items()):
    k = key[r["sample_id"]]
    g = r["ground_truth_citations"]
    out.append("#" * 70)
    out.append(f"{k['exam_id']}  ({rid}, {r['metadata']['company']} FY{r['metadata']['fiscal_year']} "
               f"{r['metadata']['statement_type']})")
    out.append(f"  judgement: {r['general_judgement']}   error: {r['error_type']}   "
               f"citation: {g.get('asc_full')}  [{g.get('citation_tier')}]")
    facts = r["gt_transaction_data"].split("Supporting facts", 1)
    if len(facts) > 1:
        out.append("  supporting facts:" + facts[1].split("\n", 1)[1][:600].replace("\n", "\n    "))
open(os.path.join(B, "PREVIEW.txt"), "w").write("\n".join(out) + "\n")
print(f"dataset_card.json + PREVIEW.txt written ({n_rec} records, {len(by_rule)} rules incl. control)")
