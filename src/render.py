#!/usr/bin/env python3
"""Rendering: structured statement -> AuditBench [row n] text, and -> XBRL-JSON."""


def fmt_money(v):
    if v is None:
        return None
    return f"(${abs(v):,.0f})" if v < 0 else f"${v:,.0f}"


def to_auditbench_text(stmt):
    lines = [f"[Time]: {stmt['period']} [SEP]"]
    for r in stmt["rows"]:
        if r.get("value") is None:
            lines.append(f"[row {r['idx']}]: {r['label']} [SEP]")
        else:
            lines.append(f"[row {r['idx']}]: {r['label']} | {fmt_money(r['value'])} [SEP]")
    return "\n".join(lines)


def to_xbrl_json(stmt):
    """Minimal OIM-style fact list (concept, period, unit, value)."""
    facts = []
    for r in stmt["rows"]:
        if r.get("concept") and r.get("value") is not None:
            facts.append({
                "concept": r["concept"],
                "period": {"instant": stmt["period"]},
                "unit": "iso4217:USD",
                "value": r["value"],
                "decimals": -6,
                "row": r["idx"],
                "label": r["label"],
            })
    return {"entity": {"name": stmt["company"], "cik": stmt.get("cik")},
            "statement": stmt["statement_type"], "fiscalYear": stmt["fiscal_year"], "facts": facts}
