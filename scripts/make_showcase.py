#!/usr/bin/env python3
"""Build a single self-describing JSON to send supervisors: schema + stats +
sample records + novelty + provenance. Output: docs/intelliaudit_dataset_showcase.json"""
import json, os, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
recs = [json.loads(l) for l in open(os.path.join(ROOT, "data", "benchmark", "records.jsonl"))]
rules = json.load(open(os.path.join(ROOT, "rulebook.json")))["rules"]


def pick(stype, rule_id):
    return next((r for r in recs if r["metadata"]["statement_type"] == stype and r["rule_id"] == rule_id), None)


samples = [r for r in [
    pick("BalanceSheet", "R01_current_noncurrent_asset_misclass"),
    pick("IncomeStatement", "R09_revenue_recognition_timing"),
    pick("CashFlow", "R08_cashflow_section_misclass"),
] if r]

showcase = {
    "dataset": "IntelliAudit-Bench",
    "one_line": "A standards-CITATION benchmark for LLM financial auditing: real 10-K statements, injected errors, and deterministic FASB ASC citation ground truth cross-checked against the official US-GAAP taxonomy.",
    "authors_note_to_supervisors": "This bundle shows the dataset shape (identical to AuditBench, upgraded with real values + taxonomy-verified citations). Full generator + 1,089 records live in the repo; here are the schema, stats, three full sample records, and the novelty argument.",

    "what_it_is": {
        "shape": "Same as AuditBench: each record = one clean statement + one injected error + synthetic transactions + labels.",
        "substrate": "REAL 10-K balance sheets / income statements / cash flows from SEC EDGAR (values are actual reported facts, never fabricated).",
        "transactions": "SYNTHETIC (real filings never publish transaction-level ledgers) — they sum to the real line values.",
        "ground_truth_citation": "The governing FASB ASC code, chosen rule-first (before injection) and cross-checked against the official US-GAAP 2023 reference linkbase; tagged linkbase-verified vs expert-authored.",
        "NOT_huge_tables": "Compact single statements (~30 rows, [row n] text) like AuditBench — NOT FinMR's 17k-167k-char whole-filing dumps."
    },

    "record_schema": {
        "sample_id": "unique id, e.g. IA-AAPL-2023-BS-R01_...",
        "metadata": "{company, cik, fiscal_year, statement_type, period, unit, source}",
        "general_judgement": "'Incorrect' (this record has an injected error)",
        "rule_id / error_type": "which rulebook rule + AuditBench error type",
        "error_identification": "{error_type, problematic_entry, affected_xbrl_concept, affected_label, pre_inject_row, post_inject_row}",
        "gt_table_text": "the CLEAN statement ([row n] text)",
        "modified_statement_text": "the ERROR-INSERTED statement ([row n] text)",
        "gt_transaction_data": "synthetic transactions summing to real line values",
        "gt_xbrl_json": "OIM-style fact list (concept, period, unit, value)",
        "ground_truth_citations": "{asc_full, asc_subtopic, asc_topic, dqc_rule, linkbase_reference_set, linkbase_verified, citation_tier, rationale}",
        "self_check": "{clean_reconciles, error_breaks_reconciliation}"
    },

    "statistics": {
        "records": len(recs),
        "clean_statements": len({(r["metadata"]["company"], r["metadata"]["fiscal_year"], r["metadata"]["statement_type"]) for r in recs}),
        "companies": sorted({r["metadata"]["company"] for r in recs}),
        "fiscal_years": sorted({r["metadata"]["fiscal_year"] for r in recs}),
        "by_statement_type": dict(collections.Counter(r["metadata"]["statement_type"] for r in recs)),
        "by_error_type": dict(collections.Counter(r["error_type"] for r in recs)),
        "by_citation_tier": dict(collections.Counter(r["ground_truth_citations"]["citation_tier"] for r in recs)),
    },

    "error_rules": [
        {"rule_id": r["rule_id"], "error_type": r["error_type"], "asc": r["citation"]["asc"],
         "dqc": r["dqc_rule"].get("dqc_id"), "family": r.get("family")}
        for r in rules
    ],

    "how_we_are_novel": {
        "gap": "Detection is covered by prior work; standards CITATION attribution is not.",
        "vs_AuditBench": "AuditBench (arXiv 2506.17282) has a citation field but it is GPT-4 free text scored ~26% by an unreleased retriever; synthetic companies. We give real data + deterministic, cross-checkable ASC citations.",
        "vs_FinAuditing": "FinAuditing (arXiv 2510.08886) uses real XBRL + DQC but its tasks are concept-ID / relation-type / value-recompute — it never outputs an ASC citation.",
        "vs_FinMR": "FinMR (FinAuditing subtask) outputs two numbers {extracted, calculated} over huge XBRL filings — no citation, and a long-context task, not ours.",
        "vs_AuditFlow": "AuditFlow (arXiv 2606.03031) does deterministic taxonomy+XBRL verification but scores a numeric verdict, not citation attribution.",
        "our_contribution": "The FIRST benchmark that scores 'name the governing ASC codification reference' on real filings with deterministic, cross-checkable ground truth — plus the measured finding that citation is a function of concept x violation, which the taxonomy linkbase alone under-determines (AR->310 not 210; revenue->606-50 disclosure not 606-25 recognition).",
        "recoverability_note_not_a_result": "A citation-SELECTOR check (Stage-1 logic only, no detection/LLM): on AuditBench the correct citation is in the candidate set only 26.2% of the time (measured oracle); on IntelliAudit-Bench it is recoverable (concept-only heuristic ~51%; upper bound 100%). The 100% is TRUE BY CONSTRUCTION because injection is rule-first, so it is an upper bound, NOT the auditor's accuracy. Real results require a blind-LLM baseline + an actual staged-pipeline run (both TODO)."
    },

    "provenance": {
        "values": "SEC EDGAR companyfacts (real 10-K)",
        "citations": "official US-GAAP 2023 reference linkbase (sha256 b48fbb7b..., 17,800 concepts indexed)",
        "transactions": "synthetic, deterministic (sum to real lines)",
        "generator": "reproducible: python3 scripts/build_benchmark.py"
    },

    "sample_records": samples,
}

out = os.path.join(ROOT, "docs", "intelliaudit_dataset_showcase.json")
json.dump(showcase, open(out, "w"), indent=2)
print(f"wrote {out}")
print(f"  records={len(recs)}  samples={len(samples)}  size={os.path.getsize(out):,} bytes")
