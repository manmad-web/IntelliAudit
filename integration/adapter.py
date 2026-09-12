#!/usr/bin/env python3
"""
========================= PROVENANCE: NEW (integration glue) ==================
IntelliAudit-Bench original. The missing bridge between the two repos.
==============================================================================

adapter.py — convert one IntelliAudit-Bench record (records.jsonl) into the
AuditBench-shaped `item` dict the capstone pipeline (full_pipeline.run_pipeline)
consumes, and expose the GOLD us-gaap concept so the pipeline can bypass its
weak dictionary concept-mapper (the 82%-coverage bottleneck) and be measured on
citation quality alone.
"""
STMT_MAP = {"BalanceSheet": "balance_sheet", "IncomeStatement": "income_statement", "CashFlow": "cash_flow"}


def iab_to_item(record: dict) -> dict:
    """IntelliAudit-Bench record → capstone `item` dict (+ gold-concept bypass)."""
    ei = record["error_identification"]
    return {
        # fields the capstone parser / run_pipeline expect:
        "table": record["modified_statement_text"],
        "transaction_data": record.get("gt_transaction_data", ""),
        "gt_table": record["gt_table_text"],
        "general_judgement": record["general_judgement"],
        "errors": [{
            "error_type": record["error_type"],
            "problematic_entry": ei.get("problematic_entry"),
        }],
        # IntelliAudit-Bench extras that let the pipeline skip its mapper:
        "statement_type": STMT_MAP.get(record["metadata"]["statement_type"]),
        "gold_concept": ei.get("affected_xbrl_concept"),
        "gold_label": ei.get("affected_label"),
        # carried through for scoring:
        "_sample_id": record["sample_id"],
    }
