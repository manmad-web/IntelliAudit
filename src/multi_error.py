#!/usr/bin/env python3
"""
Multi-error items: 1-3 independent faults on one real statement.

A SEPARATE split (data/benchmark_multi/). The single-error benchmark is not
changed by anything here.

Composition rules, so the faults do not interfere:
  * every fault targets a different row; a row touched by one fault (its
    target, or the retained-earnings/AOCI line that absorbed a balanced
    entry) cannot be the target of another;
  * pass 1 applies the recognition/measurement faults (ledger = as booked),
    and the statement at that point is the company's ledger;
  * pass 2 applies bookkeeping faults: first those that recompute subtotals
    (moves, the identity break), then those that must leave a subtotal
    unfooted (missing row, wrong value, fabricated row, sign flip), so a later
    recompute cannot silently repair an earlier arithmetic fault;
  * the corrected statement is the clean one, plus the reclassification for
    any covenant-breach fault (R19).
The number of faults (1, 2 or 3) varies and clean controls are mixed in, so
the count itself is not given away.
"""
import copy, random

import injector
from evidence import supporting_facts
from render import to_auditbench_text, to_xbrl_json
from transactions import generate_for_statement

_RECOMPUTING = {"move_row", "relabel_concept", "fact_only"}


def _ident(meta):
    out = {(meta.get("row_concept"), meta.get("row_label"))}
    if meta.get("relabelled_to"):
        out.add((meta["relabelled_to"], meta["relabelled_label"]))
    return out


def _phase(rule):
    if rule.get("ledger") == "as_booked":
        return 0
    inj = rule["injection"]
    if inj["op"] in _RECOMPUTING or inj.get("recompute") or not inj.get("keep_totals", True):
        return 1
    return 2


def compose(clean, rules, k, rng):
    """Apply up to k compatible faults. Returns (booked, shown, applied) or None."""
    order = rules[:]
    rng.shuffle(order)
    chosen, used_ids = [], set()
    for r in order:                       # at most one fault per rule
        if len(chosen) == k:
            break
        if r["rule_id"] not in used_ids:
            chosen.append(r); used_ids.add(r["rule_id"])
    chosen.sort(key=_phase)
    stmt, booked, touched, applied = clean, None, set(), []
    offsets = set()
    for rule in chosen:
        if _phase(rule) > 0 and booked is None:
            booked = stmt
        mod, meta = injector.inject(stmt, rule, rng, exclude=touched | offsets)
        if mod is None:
            continue
        touched |= _ident(meta)
        if meta.get("offset_concept"):
            offsets |= {(r.get("concept"), r.get("label")) for r in mod["rows"]
                        if r.get("concept") == meta["offset_concept"]}
        applied.append((rule, meta))
        stmt = mod
    if booked is None:
        booked = stmt
    if not applied:
        return None
    return booked, stmt, applied


def _row_idx(stmt, concept, label):
    return next((r["idx"] for r in stmt["rows"] if r.get("concept") == concept and r.get("label") == label), None)


def build_multi_record(clean, rules, k, rng, sid):
    got = compose(clean, rules, k, rng)
    if got is None:
        return None
    booked, shown, applied = got

    corrected = copy.deepcopy(clean)
    errors, violations, no_decoy, orig_vals = [], {}, set(), []
    for rule, meta in applied:
        concept, label = meta.get("row_concept"), meta.get("row_label")
        post_c = meta.get("relabelled_to", concept)
        post_l = meta.get("relabelled_label", label)
        post = _row_idx(shown, post_c, post_l)
        pre = _row_idx(clean, concept, label)
        fixed = meta.pop("corrected_statement", None)
        if fixed is not None:                          # R19: apply its reclassification
            row = next(r for r in corrected["rows"] if r.get("concept") == concept and r.get("label") == label)
            injector.move_and_recompute(corrected, row, meta["corrected_section"])
        if meta.get("original_value") is not None:
            orig_vals.append(meta["original_value"])
        if rule.get("facts") and post is not None:
            violations[post] = (rule["facts"], meta)
        elif post is not None and rule["injection"]["op"] in ("perturb_value", "flip_sign", "overstate_vs_market"):
            no_decoy.add(post)
        if meta.get("offset_concept"):
            no_decoy |= {r["idx"] for r in shown["rows"] if r.get("concept") == meta["offset_concept"]}
        errors.append({
            "rule_id": rule["rule_id"], "error_type": rule["error_type"],
            "problematic_entry": post if post is not None else pre,
            "pre_inject_row": pre, "post_inject_row": post,
            "affected_xbrl_concept": concept, "affected_label": label,
            "injection_detail": meta,
            "ground_truth_citations": injector._citation_gt(rule, clean["statement_type"], concept),
        })

    # ledger = the books (after measurement faults, before bookkeeping faults)
    seed = (clean["fiscal_year"] * 7919 + sum(map(ord, sid))) & 0xFFFFFFFF
    frng = random.Random(seed)
    caps = injector._captions(booked)
    skip = set()
    for (rule, meta) in applied:
        if rule["injection"]["op"] == "move_row":
            mv = _row_idx(booked, meta.get("row_concept"), meta.get("row_label"))
            if mv is not None and caps[mv] != next(r["label"] for r in booked["rows"] if r["idx"] == mv):
                skip.add(mv)
    tx = generate_for_statement(booked, seed=seed, labels=caps, skip=skip, extra_forbidden=orig_vals)
    facts = supporting_facts(shown, frng, injector._captions(shown), violation=violations, no_decoy=no_decoy)
    if facts:
        tx = tx.rstrip("\n") + "\nSupporting facts (period-end reviews):\n" + facts

    errors.sort(key=lambda e: (e["problematic_entry"] is None, e["problematic_entry"]))
    return {
        "sample_id": sid, "record_type": "injected", "n_errors": len(errors),
        "metadata": {"company": clean["company"], "cik": clean.get("cik"), "fiscal_year": clean["fiscal_year"],
                     "statement_type": clean["statement_type"], "period": clean["period"],
                     "unit": clean["unit"], "source": clean["source"]},
        "general_judgement": "Incorrect",
        "errors": errors,
        "modified_statement_text": to_auditbench_text(shown),
        "gt_table_text": to_auditbench_text(corrected),
        "gt_transaction_data": tx,
        "gt_xbrl_json": to_xbrl_json(corrected),
        "self_check": {"clean_reconciles": injector.check_reconciles(clean),
                       "error_breaks_reconciliation": not injector.check_reconciles(shown)},
    }


def build_multi_control(clean, sid):
    rec = injector.build_control(clean, sid)
    rec["n_errors"] = 0
    rec["errors"] = []
    for k in ("rule_id", "error_type", "error_identification", "injection_detail", "ground_truth_citations"):
        rec.pop(k, None)
    return rec
