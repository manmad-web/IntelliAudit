#!/usr/bin/env python3
"""
Rule-first error injection + ground-truth citation cross-check.

For each rule in the rulebook we apply its recipe to a REAL, reconciling statement
(only 'injectable' concept-tagged lines are eligible), then attach the ground-truth
citation. The citation is cross-checked against the OFFICIAL linkbase via
citation_resolver so you can verify it:
  * linkbase_verified = True  -> the rule's ASC subtopic appears in the concept's
    real reference set (deterministic, unarguable).
  * linkbase_verified = False -> the governing standard the linkbase does NOT tag
    on the line (e.g. recognition ASC 606-10-25 on a revenue line). These are the
    HARD, expert-authored citations and are the interesting cases.
"""
import copy, json, os, random
from render import to_auditbench_text, to_xbrl_json
from transactions import generate_for_statement

try:
    from citation_resolver import CitationResolver
    _RESOLVER = CitationResolver()
except Exception:
    _RESOLVER = None


def _by_idx(stmt):
    return {r["idx"]: r for r in stmt["rows"]}


def check_reconciles(stmt):
    idx = _by_idx(stmt)
    for r in stmt["rows"]:
        if r.get("kind") in ("subtotal", "total") and r.get("sums"):
            if r["value"] != sum(idx[c]["value"] for c in r["sums"] if idx[c].get("value") is not None):
                return False
    for ident in stmt.get("identities", []):
        if ident.get("tolerant"):   # e.g. cash roll-forward (subtotal tree already checks it)
            continue
        lhs = next((x["value"] for x in stmt["rows"] if x["concept"] == ident["lhs"]), None)
        rhs = sum(next((x["value"] for x in stmt["rows"] if x["concept"] == c), 0) for c in ident["rhs"])
        if lhs != rhs:
            return False
    return True


def _recompute(stmt):
    idx = _by_idx(stmt)
    for r in stmt["rows"]:
        if r.get("kind") in ("subtotal", "total") and r.get("sums"):
            r["value"] = sum(idx[c]["value"] for c in r["sums"] if idx[c].get("value") is not None)


def _eligible(stmt, rule):
    elig = rule.get("eligible_concepts", [])
    lines = [r for r in stmt["rows"] if r.get("kind") == "line" and r.get("injectable") and r.get("concept")]
    if elig == ["*non_subtotal_non_total"]:
        return lines
    return [r for r in lines if r["concept"] in elig]


def _reindex(stmt):
    remap = {r["idx"]: i for i, r in enumerate(stmt["rows"])}
    for i, r in enumerate(stmt["rows"]):
        r["idx"] = i
    for r in stmt["rows"]:
        if r.get("sums"):
            r["sums"] = [remap[c] for c in r["sums"] if c in remap]


def inject(stmt, rule, rng):
    op = rule["injection"]["op"]
    m = copy.deepcopy(stmt)
    cands = _eligible(m, rule)

    if op == "move_row":
        to_section = rule["injection"].get("to_section")
        if not cands or not to_section:
            return None, "no eligible concept / no target section"
        row = rng.choice(cands)
        src = row["section"]
        if src == to_section:
            return None, "no-op move (source == target section)"
        row["section"] = to_section
        m["rows"].remove(row)
        pos = max(i for i, r in enumerate(m["rows"]) if r.get("section") == to_section) + 1
        m["rows"].insert(pos, row)
        _reindex(m)
        return m, {"row_concept": row["concept"], "row_label": row["label"], "from_section": src, "to_section": to_section}

    if op == "delete_row":
        if not cands:
            return None, "no deletable line"
        row = rng.choice(cands); m["rows"].remove(row); _reindex(m)
        return m, {"row_concept": row["concept"], "row_label": row["label"], "deleted_value": row["value"]}

    if op in ("perturb_value", "overstate_vs_market"):
        if not cands:
            return None, "no eligible concept"
        row = rng.choice(cands)
        lo, hi = rule["injection"].get("pct_range", [0.05, 0.3])
        pct = rng.uniform(lo, hi)
        if rule["injection"].get("direction") == "overstate" or op == "overstate_vs_market":
            pct = abs(pct)
        else:
            pct = rng.choice([-1, 1]) * pct
        orig = row["value"]; row["value"] = int(round(orig * (1 + pct)))
        if not rule["injection"].get("keep_totals", True):
            _recompute(m)
        return m, {"row_concept": row["concept"], "row_label": row["label"], "original_value": orig, "erroneous_value": row["value"]}

    if op == "flip_sign":
        if not cands:
            return None, "no eligible concept"
        row = rng.choice(cands); orig = row["value"]; row["value"] = -abs(orig)
        return m, {"row_concept": row["concept"], "row_label": row["label"], "original_value": orig, "erroneous_value": row["value"]}

    if op == "insert_row":
        sub = next((r for r in m["rows"] if r.get("kind") == "subtotal"), None)
        if not sub:
            return None, "no subtotal"
        label = rng.choice(rule["injection"]["fabricated_labels"])
        lo, hi = rule["injection"].get("value_pct_of_subtotal", [0.02, 0.08])
        val = int(round(sub["value"] * rng.uniform(lo, hi)))
        m["rows"].insert(m["rows"].index(sub), {"idx": -1, "label": label, "section": sub["section"],
                                                "concept": "us-gaap:FABRICATED", "value": val, "kind": "line", "injectable": False})
        _reindex(m)
        return m, {"row_concept": "us-gaap:FABRICATED", "row_label": label, "fabricated_value": val}

    return None, f"op '{op}' not implemented in v0.1"


def _citation_gt(rule, stmt_type, concept):
    c = rule["citation"]
    asc = c.get("citation_by_statement", {}).get(stmt_type, c["asc"])
    parts = asc.replace("ASC ", "").split("-")
    topic = parts[0]; subtopic = "-".join(parts[:2]) if len(parts) >= 2 else topic
    # cross-check against the real linkbase reference set for this concept
    linkbase_set, verified = [], None
    if _RESOLVER and concept and concept != "us-gaap:FABRICATED":
        try:
            linkbase_set = _RESOLVER.citations(concept.replace("us-gaap:", ""))
            verified = any(x.startswith(f"ASC {subtopic}") for x in linkbase_set)
        except Exception:
            verified = None
    return {
        "asc_full": asc, "asc_subtopic": f"ASC {subtopic}", "asc_topic": f"ASC {topic}",
        "dqc_rule": rule["dqc_rule"].get("dqc_id"), "dqc_verified": rule["dqc_rule"].get("verified", False),
        "linkbase_reference_set": linkbase_set,
        "linkbase_verified": verified,
        "citation_tier": ("linkbase-verified" if verified else "expert-authored") if verified is not None else "unresolved",
        "weak_citation": c.get("weak_citation", False),
        "rationale": c["rationale"],
    }


def build_record(clean, rule, mod, meta, sid):
    concept = meta.get("row_concept")
    pe = next((r["idx"] for r in mod["rows"] if r.get("concept") == concept and r.get("label") == meta.get("row_label")), None)
    return {
        "sample_id": sid,
        "metadata": {"company": clean["company"], "cik": clean.get("cik"), "fiscal_year": clean["fiscal_year"],
                     "statement_type": clean["statement_type"], "period": clean["period"],
                     "unit": clean["unit"], "source": clean["source"]},
        "general_judgement": "Incorrect",
        "rule_id": rule["rule_id"], "error_type": rule["error_type"],
        "error_identification": {"error_type": rule["error_type"], "problematic_entry": pe, "affected_xbrl_concept": concept},
        "injection_detail": meta,
        "ground_truth_citations": _citation_gt(rule, clean["statement_type"], concept),
        "modified_statement_text": to_auditbench_text(mod),
        "gt_table_text": to_auditbench_text(clean),
        "gt_transaction_data": generate_for_statement(clean, seed=clean["fiscal_year"]),
        "gt_xbrl_json": to_xbrl_json(clean),
        "self_check": {"clean_reconciles": check_reconciles(clean),
                       "error_breaks_reconciliation": not check_reconciles(mod)},
    }
