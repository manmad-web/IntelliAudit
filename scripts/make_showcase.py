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


# ============================================================================
#  dataset_card.json — FACTS ONLY. Ships with the benchmark.
#  Deliberately contains NO novelty claims, NO competitor comparison, and NO
#  experimental caveats — those belong in the paper, not in a data artifact.
# ============================================================================
card = {
    "name": "IntelliAudit-Bench",
    "version": "0.1",
    "description": ("A benchmark for standards-citation attribution in financial-statement auditing. "
                    "Each record is a real 10-K financial statement containing one deliberately injected "
                    "accounting error, paired with synthetic supporting transactions and the governing "
                    "FASB ASC citation as ground truth."),
    "repository": "https://github.com/manmad-web/IntelliAudit",
    "domain": "financial auditing / accounting standards / XBRL",
    "language": "en",
    "task": ("Given a financial statement with one injected error (and its transactions), "
             "identify the error and cite the governing FASB ASC codification reference."),

    "license_and_terms": {
        "financial_values": "Derived from SEC EDGAR filings (US public domain).",
        "citations": "Derived from the FASB US-GAAP 2023 taxonomy; subject to FASB terms of use.",
        "generated_content": "Injected errors and synthetic transactions produced by this repository's generator.",
    },

    "files": {
        "data/benchmark/exam.jsonl": "1089 rows — statement WITH injected error + transactions. No labels. Input to a system.",
        "data/benchmark/answer_key.jsonl": "1089 rows — judgement, error identification, and ASC citation. Withheld during evaluation.",
        "data/benchmark/statements_clean.jsonl": "223 rows — the error-free statements (control set / repair target).",
        "data/benchmark/records.jsonl": "1089 rows — exam and answer key joined, for convenience.",
        "data/clean/": "223 files — one clean statement per company x fiscal year x statement type.",
        "data/benchmark/summary.json": "Aggregate counts.",
    },

    # schema restated here (not reused from the briefing) so the card stays
    # free of any comparison to other datasets
    "record_schema": {**showcase["record_schema"],
                      "rule_id / error_type": "the rulebook rule that was injected, and its error-type label"},
    "statistics": showcase["statistics"],
    "error_rules": showcase["error_rules"],

    "source_data": {
        "financial_values": "SEC EDGAR companyfacts API — actual reported 10-K facts; values are never fabricated.",
        "citation_authority": "Official US-GAAP 2023 reference linkbase (xbrl.fasb.org), 17,800 concepts indexed.",
        "transactions": "Synthetic, deterministic; generated to sum exactly to the real reported line values.",
    },

    "construction": {
        "summary": ("Deterministic five-step generator: (1) ingest real 10-K XBRL facts from SEC EDGAR; "
                    "(2) normalize into canonical reconciling statements; (3) inject one error rule-first "
                    "from a curated rulebook mapping {error type -> us-gaap concept -> governing ASC citation}; "
                    "(4) cross-check each citation against the official US-GAAP reference linkbase; "
                    "(5) synthesize transactions summing to the reported line values."),
        "reproduce": ["python3 scripts/build_benchmark.py", "python3 scripts/split_dataset.py"],
        "llm_used_in_construction": False,
        "details": "See docs/DATASHEET.md",
    },

    "ground_truth_confidence": {
        "linkbase-verified": "Citation confirmed present in the concept's official FASB linkbase reference set.",
        "expert-authored": "Governing standard not tagged on that line by the linkbase (recognition/classification judgment); requires human validation.",
        "unresolved": "Fabricated line items with no corresponding us-gaap concept.",
        "counts": showcase["statistics"]["by_citation_tier"],
    },

    "known_limitations": [
        "Single-error: exactly one injected error per record; no multi-error split.",
        "Sector concentration: 5 of 8 companies are technology; no financial-sector, energy, or industrial filers.",
        "Compact single statements (~30 rows), not multi-document long-context filings.",
        "Errors are injected rather than naturally occurring.",
        "DQC rule identifiers are provisional (dqc_verified=false) pending cross-check against the official XBRL-US ruleset.",
        "Statement layout follows a canonical concept template with residual balancing lines, not each filer's exact presentation linkbase ordering.",
    ],

    "evaluation": {
        "scorer": "scripts/score_predictions.py",
        "metrics": "Citation exact-match at ASC topic / subtopic / full-paragraph, reported as precision (of answered), recall (of all records), and abstention rate; plus error-type and row exact-match.",
        "prediction_format": {"sample_id": "str", "predicted_asc": "str or null to abstain",
                              "predicted_error_type": "str (optional)", "predicted_row": "int (optional)"},
    },

    "sample_records": samples,
}

card_out = os.path.join(ROOT, "data", "dataset_card.json")
json.dump(card, open(card_out, "w"), indent=2)
print(f"wrote {card_out}")
print(f"  facts-only card: {os.path.getsize(card_out):,} bytes (no novelty claims, no experiment caveats)")
