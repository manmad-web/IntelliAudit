#!/usr/bin/env python3
"""
Rule-first error injection + ground-truth citation cross-check.

For each rule in the rulebook we apply its recipe to a REAL, reconciling statement
(only 'injectable' concept-tagged lines are eligible), then attach the ground-truth
citation. linkbase_verified is a strict PARAGRAPH match against the official
US-GAAP reference linkbase (or its committed offline cache).

v0.4 design (after the second audit):

  * Arithmetic-visible vs knowledge-only. Detection-only rules (R04 missing,
    R05 typo, R06 fabricated, R07 identity, R12 sign) break footing, so an
    arithmetic gate can find them. Every CITABLE rule leaves the statement
    footing: misclassifications recompute the subtotals they move between,
    and recognition/measurement rules post the other side of the entry
    (retained earnings, AOCI, or the income-statement chain). The citable
    cases are exactly the ones arithmetic cannot solve.
  * Ledger basis. For a bookkeeping fault the ledger is the truth (clean
    statement). For a measurement/recognition fault the company booked what it
    reported, so the ledger is the statement as shown and the violation is in
    the supporting facts only.
  * Contrastive supporting facts on every record, clean controls included
    (src/evidence.py).
  * Evidence lines are keyed by caption, not by row number.
"""
import copy, random, re
from render import to_auditbench_text, to_xbrl_json
from transactions import generate_for_statement
from evidence import KIND_BY_CONCEPT, supporting_facts

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
    # zero-valued lines are excluded: deleting or perturbing a 0 changes nothing
    lines = [r for r in stmt["rows"] if r.get("kind") == "line" and r.get("injectable")
             and r.get("concept") and r.get("value")]
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


def _parent_of_section(stmt, section, exclude_idx):
    """The subtotal/total that sums the other lines of `section`."""
    counts = {}
    for p in stmt["rows"]:
        if p.get("kind") in ("subtotal", "total") and p.get("sums"):
            n = sum(1 for i in p["sums"] if i != exclude_idx and
                    _by_idx(stmt)[i].get("section") == section and _by_idx(stmt)[i].get("kind") == "line")
            if n:
                counts[p["idx"]] = n
    if counts:
        return max(counts, key=lambda k: (counts[k], -k))
    sub = [p for p in stmt["rows"] if p.get("kind") == "subtotal" and p.get("section") == section]
    return sub[0]["idx"] if sub else None


def move_and_recompute(m, row, to_section, pos=None):
    """Move `row` into `to_section`, re-parent it, recompute every subtotal.

    v0.3 moved the row but left it summed into its old subtotal, so the
    section it was dropped into no longer footed: arithmetic located every
    misclassification. A real misclassification is carried through the
    subtotals (AuditBench's own example recomputes total current assets).
    """
    old_parents = [p for p in m["rows"] if p.get("sums") and row["idx"] in p["sums"]]
    new_parent = _parent_of_section(m, to_section, row["idx"])
    for p in old_parents:
        p["sums"] = [i for i in p["sums"] if i != row["idx"]]
    if new_parent is not None:
        np_ = _by_idx(m)[new_parent]
        np_["sums"] = np_["sums"] + [row["idx"]]
    row["section"] = to_section
    m["rows"].remove(row)
    idxs = [i for i, r in enumerate(m["rows"])
            if r.get("section") == to_section and r.get("kind") == "line"]
    if pos is None:
        pos = (idxs[-1] + 1) if idxs else len(m["rows"])
    m["rows"].insert(pos, row)
    _reindex(m)
    _recompute(m)


def _sentence(label):
    return label[:1].upper() + label[1:].lower() if label else label


def inject(stmt, rule, rng, exclude=()):
    """exclude: (concept, label) identities that may not be targeted (rows a
    previous error on the same multi-error item already touched)."""
    op = rule["injection"]["op"]
    m = copy.deepcopy(stmt)
    cands = _eligible(m, rule)
    if exclude:
        cands = [r for r in cands if (r.get("concept"), r.get("label")) not in exclude]
    inj = rule["injection"]

    if op == "move_row":
        to_section = inj.get("to_section")
        cands = [r for r in cands if r["section"] == inj.get("from_section", r["section"])]
        if not cands or not to_section:
            return None, "no eligible concept / no target section"
        row = rng.choice(cands)
        src = row["section"]
        if src == to_section:
            return None, "no-op move (source == target section)"
        idxs = [i for i, r in enumerate(m["rows"])
                if r.get("section") == to_section and r.get("kind") == "line"]
        pos = rng.choice(idxs + [idxs[-1] + 1]) if idxs else None
        if pos is not None and pos > m["rows"].index(row):
            pos -= 1
        move_and_recompute(m, row, to_section, pos)
        return m, {"row_concept": row["concept"], "row_label": row["label"], "from_section": src,
                   "to_section": to_section}

    if op == "delete_row":
        if not cands:
            return None, "no deletable line"
        row = rng.choice(cands); m["rows"].remove(row); _reindex(m)
        return m, {"row_concept": row["concept"], "row_label": row["label"], "deleted_value": row["value"]}

    if op in ("perturb_value", "overstate_vs_market"):
        if not cands:
            return None, "no eligible concept"
        row = rng.choice(cands)
        lo, hi = inj.get("pct_range", [0.05, 0.3])
        pct = rng.uniform(lo, hi)
        direction = inj.get("direction")
        orig = row["value"]
        if direction == "toward_zero":                 # e.g. an expense understated
            new = int(round(orig * (1 - pct)))
        else:
            if direction == "overstate" or op == "overstate_vs_market":
                pct = abs(pct)
            else:
                pct = rng.choice([-1, 1]) * pct
            new = int(round(orig * (1 + pct)))
        if new == orig:
            return None, "perturbation rounds to zero"
        meta = {"row_concept": row["concept"], "row_label": row["label"],
                "original_value": orig, "erroneous_value": new}
        bal = inj.get("balance_with")
        if bal:
            off = next((r for r in m["rows"] if r.get("kind") == "line" and r.get("concept") in bal), None)
            if off is None:
                return None, "no balancing line"
            off["value"] += new - orig
            meta.update({"offset_concept": off["concept"], "offset_delta": new - orig})
        row["value"] = new
        if bal or inj.get("recompute") or not inj.get("keep_totals", True):
            _recompute(m)
        return m, meta

    if op == "flip_sign":
        if not cands:
            return None, "no eligible concept"
        row = rng.choice(cands); orig = row["value"]; row["value"] = -abs(orig)
        return m, {"row_concept": row["concept"], "row_label": row["label"], "original_value": orig, "erroneous_value": row["value"]}

    if op == "relabel_concept":
        # Lease misclassification: present an operating lease as a finance lease
        # (or vice versa). Values unchanged, so the statement still foots.
        if not cands:
            return None, "no eligible lease concept"
        row = rng.choice(cands)
        old_c, old_l = row["concept"], row["label"]
        for a, b in inj.get("swap", [["Operating", "Finance"]]):
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

    if op == "fact_only":
        # The statement is left exactly as filed; the supporting facts make it
        # wrong (e.g. a covenant breach that makes non-current debt callable).
        # The corrected statement is the filed one with the fix applied.
        if not cands:
            return None, "no eligible concept"
        row = rng.choice(cands)
        fixed = copy.deepcopy(stmt)
        frow = next(r for r in fixed["rows"] if r["idx"] == row["idx"])
        move_and_recompute(fixed, frow, inj["corrected_section"])
        return m, {"row_concept": row["concept"], "row_label": row["label"],
                   "statement_unchanged": True, "corrected_statement": fixed,
                   "corrected_section": inj["corrected_section"]}

    if op == "insert_row":
        # Section-aware pool (v0.3 could put "Deferred Revenue" under assets) in
        # sentence case (v0.3's Title Case stood out against real captions).
        pools = inj["fabricated_labels"]
        subs = [r for r in m["rows"] if r.get("kind") in ("subtotal", "total") and r.get("value") is not None
                and r.get("section") in pools]
        if not subs:
            return None, "no subtotal with a label pool"
        sub = rng.choice(subs)
        existing = {(r.get("label") or "").lower() for r in m["rows"]}
        pool = [e for e in pools[sub["section"]] if e[0].lower() not in existing]
        if not pool:
            return None, "no unused fabricated label"
        label, sign = rng.choice(pool)
        label = _sentence(label)
        lo, hi = inj.get("value_pct_of_subtotal", [0.02, 0.08])
        val = sign * (int(round(abs(sub["value"]) * rng.uniform(lo, hi))) or 1)
        # insert among the subtotal's own line children and sum it into that
        # subtotal WITHOUT recomputing: the stated subtotal no longer foots.
        # (v0.3 left the row out of every sums list, so self_check reported
        # 140/140 redundant-row cases as still reconciling.)
        kids = [i for i, r in enumerate(m["rows"]) if r["idx"] in (sub.get("sums") or [])
                and r.get("kind") == "line"]
        pos = rng.choice(kids + [kids[-1] + 1]) if kids else m["rows"].index(sub)
        section = m["rows"][kids[0]]["section"] if kids else sub["section"]
        fab = {"idx": -1, "label": label, "section": section,
               "concept": "us-gaap:FABRICATED", "value": val,
               "kind": "line", "injectable": False, "fabricated": True}
        m["rows"].insert(pos, fab)
        _reindex(m)
        sub["sums"] = sub["sums"] + [fab["idx"]]
        return m, {"row_concept": "us-gaap:FABRICATED", "row_label": label,
                   "fabricated_value": val, "fabricated": True}

    return None, f"op '{op}' not implemented"


def _strip(x):
    """'ASC 210-10-45-1((b))' -> 'ASC 210-10-45-1'"""
    return re.sub(r"\(\(.*?\)\)", "", x).strip()


def _citation_gt(rule, stmt_type, concept):
    """
    Paragraph-level ground truth. citable=false means no single ASC paragraph
    governs the fault (detection-only). linkbase_verified is a strict
    paragraph match. DQC ids are never emitted unless verified.
    """
    c = rule["citation"]
    asc = c.get("citation_by_statement", {}).get(stmt_type, c.get("asc"))

    linkbase_set, cached = [], None
    if _RESOLVER and concept and concept != "us-gaap:FABRICATED":
        try:
            linkbase_set = _RESOLVER.citations(concept.replace("us-gaap:", ""))
            if hasattr(_RESOLVER, "covers"):
                cached = _RESOLVER.covers(concept)
        except Exception:
            linkbase_set = []

    if not asc:                                   # detection-only case
        out = {
            "citable": False, "asc_full": None, "asc_subtopic": None, "asc_topic": None,
            "dqc_rule": None, "linkbase_reference_set": linkbase_set,
            "linkbase_verified": False, "citation_tier": "no-governing-paragraph",
            "rationale": c.get("rationale", ""),
            "note": "No single ASC paragraph governs this fault; detection-only, excluded from citation scoring.",
        }
    else:
        parts = asc.replace("ASC ", "").split("-")
        topic = parts[0]
        subtopic = "-".join(parts[:2]) if len(parts) >= 2 else topic
        verified = any(_strip(x) == asc for x in linkbase_set)   # STRICT paragraph match
        dqc = rule.get("dqc_rule", {})
        out = {
            "citable": True,
            "asc_full": asc, "asc_subtopic": f"ASC {subtopic}", "asc_topic": f"ASC {topic}",
            "dqc_rule": dqc.get("dqc_id") if dqc.get("verified") else None,
            "linkbase_reference_set": linkbase_set,
            "linkbase_verified": verified,
            "citation_tier": "linkbase-verified" if verified else "expert-authored-UNVALIDATED",
            "policy_clause": c.get("policy_clause"),
            "weak_citation": c.get("weak_citation", False),
            "rationale": c["rationale"],
        }
    if cached is False:
        out["linkbase_note"] = "concept not in the offline reference cache; rebuild online to populate"
    return out


# ------------------------------------------------------------- evidence -----
def _captions(stmt):
    """Printed caption per row; duplicates get the section so they stay distinct."""
    from collections import Counter
    n = Counter(r["label"] for r in stmt["rows"] if r.get("kind") == "line")
    word = {"CurrentAssets": "current asset", "NoncurrentAssets": "non-current asset",
            "CurrentLiabilities": "current liability", "NoncurrentLiabilities": "non-current liability"}
    return {r["idx"]: (f"{r['label']} ({word[r['section']]})" if n[r["label"]] > 1 and r.get("section") in word
                       else r["label"]) for r in stmt["rows"]}


def _row_by_identity(stmt, concept, label):
    return next((r for r in stmt["rows"] if r.get("concept") == concept and r.get("label") == label), None)


def exam_evidence(clean, shown, rule, meta, seed):
    """Ledger lines + supporting facts for one exam item.

    rule/meta are None for a clean control.
    """
    rng = random.Random(seed)
    as_booked = bool(rule and rule.get("ledger") == "as_booked")
    ledger = shown if as_booked else clean
    caps = _captions(ledger)
    skip = set()
    if rule and rule["injection"]["op"] == "move_row":
        # a moved row whose caption is duplicated would print a section
        # qualifier from the clean statement, i.e. its original section
        moved = _row_by_identity(ledger, meta["row_concept"], meta["row_label"])
        if moved is not None and caps[moved["idx"]] != moved["label"]:
            skip.add(moved["idx"])
    orig_vals = [meta.get("original_value")] if meta else []
    tx = generate_for_statement(ledger, seed=seed, labels=caps, skip=skip, extra_forbidden=orig_vals)

    shown_caps = _captions(shown)
    violation, no_decoy = None, set()
    if rule:
        target = _row_by_identity(shown, meta.get("relabelled_to", meta.get("row_concept")),
                                  meta.get("relabelled_label", meta.get("row_label")))
        kind = rule.get("facts")
        if kind and target is not None:
            violation = (target["idx"], kind, meta)
        elif target is not None and rule["injection"]["op"] in ("perturb_value", "flip_sign", "overstate_vs_market"):
            no_decoy.add(target["idx"])
        off = meta.get("offset_concept")
        if off:
            no_decoy |= {r["idx"] for r in shown["rows"] if r.get("concept") == off}
    facts = supporting_facts(shown, rng, shown_caps, violation=violation, no_decoy=no_decoy)
    if facts:
        tx = tx.rstrip("\n") + "\nSupporting facts (period-end reviews):\n" + facts
    return tx


def build_record(clean, rule, mod, meta, sid):
    concept = meta.get("row_concept")
    label = meta.get("row_label")
    # injection shifts row numbers: store both indices and the label/concept key
    pre = next((r["idx"] for r in clean["rows"] if r.get("concept") == concept and r.get("label") == label), None)
    post_c = meta.get("relabelled_to", concept)
    post_l = meta.get("relabelled_label", label)
    post = next((r["idx"] for r in mod["rows"] if r.get("concept") == post_c and r.get("label") == post_l), None)
    pe = post if post is not None else pre
    corrected = meta.pop("corrected_statement", None) or clean
    seed = (clean["fiscal_year"] * 7919 + sum(map(ord, sid))) & 0xFFFFFFFF
    return {
        "sample_id": sid,
        "record_type": "injected",
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
        "gt_table_text": to_auditbench_text(corrected),
        "gt_transaction_data": exam_evidence(clean, mod, rule, meta, seed),
        "gt_xbrl_json": to_xbrl_json(corrected),
        "self_check": {"clean_reconciles": check_reconciles(clean),
                       "error_breaks_reconciliation": not check_reconciles(mod)},
    }


def build_control(clean, sid):
    """A clean statement on the exam, same format, judgement Correct."""
    seed = (clean["fiscal_year"] * 7919 + sum(map(ord, sid))) & 0xFFFFFFFF
    return {
        "sample_id": sid,
        "record_type": "control",
        "metadata": {"company": clean["company"], "cik": clean.get("cik"), "fiscal_year": clean["fiscal_year"],
                     "statement_type": clean["statement_type"], "period": clean["period"],
                     "unit": clean["unit"], "source": clean["source"]},
        "general_judgement": "Correct",
        "rule_id": None, "error_type": None,
        "error_identification": None,
        "injection_detail": None,
        "ground_truth_citations": {"citable": False, "asc_full": None, "asc_subtopic": None,
                                   "asc_topic": None, "citation_tier": "no-error",
                                   "linkbase_reference_set": [], "linkbase_verified": False},
        "modified_statement_text": to_auditbench_text(clean),
        "gt_table_text": to_auditbench_text(clean),
        "gt_transaction_data": exam_evidence(clean, clean, None, None, seed),
        "gt_xbrl_json": to_xbrl_json(clean),
        "self_check": {"clean_reconciles": check_reconciles(clean), "error_breaks_reconciliation": False},
    }
