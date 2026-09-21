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
import copy, json, os, random, re
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
        # AUDIT FIX: v0.1 always inserted after the section's LAST row, i.e. directly
        # after a subtotal — a deterministic positional tell. Now insert at a random
        # position among the target section's line rows.
        idxs = [i for i, r in enumerate(m["rows"])
                if r.get("section") == to_section and r.get("kind") == "line"]
        pos = rng.choice(idxs) if idxs else len(m["rows"])
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

    if op == "relabel_concept":
        # Lease misclassification: present an operating lease as a finance lease
        # (or vice versa). The paired liability is left untouched, so the
        # statement now asserts a lease classification its own figures contradict.
        if not cands:
            return None, "no eligible lease concept"
        row = rng.choice(cands)
        old_c, old_l = row["concept"], row["label"]
        for a, b in rule["injection"].get("swap", [["Operating", "Finance"]]):
            if a in old_c:
                row["concept"] = old_c.replace(a, b); row["label"] = old_l.replace(a, b).replace(a.lower(), b.lower())
                break
            if b in old_c:
                row["concept"] = old_c.replace(b, a); row["label"] = old_l.replace(b, a).replace(b.lower(), a.lower())
                break
        if row["concept"] == old_c:
            return None, "swap token not present in concept"
        return m, {"row_concept": old_c, "row_label": old_l,
                   "relabelled_to": row["concept"], "relabelled_label": row["label"]}

    if op == "insert_row":
        # AUDIT FIX: v0.1 always inserted immediately before the FIRST subtotal and
        # drew from only 4 fixed labels — two deterministic tells. Now: random
        # subtotal, random position among that section's lines, wider label pool.
        subs = [r for r in m["rows"] if r.get("kind") == "subtotal" and r.get("value") is not None]
        if not subs:
            return None, "no subtotal"
        sub = rng.choice(subs)
        label = rng.choice(rule["injection"]["fabricated_labels"])
        lo, hi = rule["injection"].get("value_pct_of_subtotal", [0.02, 0.08])
        val = int(round(abs(sub["value"]) * rng.uniform(lo, hi)))
        idxs = [i for i, r in enumerate(m["rows"])
                if r.get("section") == sub["section"] and r.get("kind") == "line"]
        pos = rng.choice(idxs) if idxs else m["rows"].index(sub)
        m["rows"].insert(pos, {"idx": -1, "label": label, "section": sub["section"],
                               "concept": "us-gaap:FABRICATED", "value": val,
                               "kind": "line", "injectable": False})
        _reindex(m)
        return m, {"row_concept": "us-gaap:FABRICATED", "row_label": label, "fabricated_value": val}

    return None, f"op '{op}' not implemented in v0.1"


def _strip(x):
    """'ASC 210-10-45-1((b))' -> 'ASC 210-10-45-1'"""
    return re.sub(r"\(\(.*?\)\)", "", x).strip()


def _citation_gt(rule, stmt_type, concept):
    """
    AUDIT FIXES:
      * linkbase_verified is now a STRICT PARAGRAPH match. v0.1 compared only the
        subtopic, so 675 records were labelled "linkbase-verified" when just 103
        hold at paragraph level. The flag now means what it says.
      * DQC ids are only emitted when the rulebook marks them verified. v0.1
        shipped provisional ids, 3 of 5 of which the audit found to be wrong;
        omitting is better than asserting something false.
      * A rule may declare citation.asc = null, meaning "no single ASC paragraph
        governs this" (arithmetic/existence faults). Those become detection-only
        cases and are EXCLUDED from citation scoring via citable=false.
    """
    c = rule["citation"]
    asc = c.get("citation_by_statement", {}).get(stmt_type, c.get("asc"))

    linkbase_set = []
    if _RESOLVER and concept and concept != "us-gaap:FABRICATED":
        try:
            linkbase_set = _RESOLVER.citations(concept.replace("us-gaap:", ""))
        except Exception:
            linkbase_set = []

    if not asc:                                   # detection-only case
        return {
            "citable": False, "asc_full": None, "asc_subtopic": None, "asc_topic": None,
            "dqc_rule": None, "linkbase_reference_set": linkbase_set,
            "linkbase_verified": False, "citation_tier": "no-governing-paragraph",
            "rationale": c.get("rationale", ""),
            "note": "No single ASC paragraph governs this fault; detection-only, excluded from citation scoring.",
        }

    parts = asc.replace("ASC ", "").split("-")
    topic = parts[0]
    subtopic = "-".join(parts[:2]) if len(parts) >= 2 else topic
    verified = any(_strip(x) == asc for x in linkbase_set)   # STRICT paragraph match
    dqc = rule.get("dqc_rule", {})
    return {
        "citable": True,
        "asc_full": asc, "asc_subtopic": f"ASC {subtopic}", "asc_topic": f"ASC {topic}",
        "dqc_rule": dqc.get("dqc_id") if dqc.get("verified") else None,
        "linkbase_reference_set": linkbase_set,
        "linkbase_verified": verified,
        "citation_tier": "linkbase-verified" if verified else "expert-authored-UNVALIDATED",
        "weak_citation": c.get("weak_citation", False),
        "rationale": c["rationale"],
    }


def build_record(clean, rule, mod, meta, sid):
    concept = meta.get("row_concept")
    label = meta.get("row_label")
    # gap #7 fix: injection shifts row numbers. Store BOTH indices and the
    # label/concept key so scoring can match on identity, not a volatile row id.
    pre = next((r["idx"] for r in clean["rows"] if r.get("concept") == concept and r.get("label") == label), None)
    post = next((r["idx"] for r in mod["rows"] if r.get("concept") == concept and r.get("label") == label), None)
    pe = post if post is not None else pre
    return {
        "sample_id": sid,
        "metadata": {"company": clean["company"], "cik": clean.get("cik"), "fiscal_year": clean["fiscal_year"],
                     "statement_type": clean["statement_type"], "period": clean["period"],
                     "unit": clean["unit"], "source": clean["source"]},
        "general_judgement": "Incorrect",
        "rule_id": rule["rule_id"], "error_type": rule["error_type"],
        "error_identification": {"error_type": rule["error_type"], "problematic_entry": pe,
                                 "affected_xbrl_concept": concept, "affected_label": label,
                                 "pre_inject_row": pre, "post_inject_row": post},
        "injection_detail": meta,
        "ground_truth_citations": _citation_gt(rule, clean["statement_type"], concept),
        "modified_statement_text": to_auditbench_text(mod),
        "gt_table_text": to_auditbench_text(clean),
        "gt_transaction_data": generate_for_statement(clean, seed=clean["fiscal_year"]),
        "gt_xbrl_json": to_xbrl_json(clean),
        "self_check": {"clean_reconciles": check_reconciles(clean),
                       "error_breaks_reconciliation": not check_reconciles(mod)},
    }
