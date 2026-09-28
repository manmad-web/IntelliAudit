#!/usr/bin/env python3
"""
Presentation normalization for clean statements (idempotent, values preserved).

Three defects in the v0.3 clean statements, all found while re-auditing after
the external review, none of which change a reported fact:

1. Ignored calculation weights. The filing-linkbase builder added every child
   with weight +1. Treasury stock carries weight -1, so it was shown as a
   positive number and a residual plug of exactly -2x the treasury balance
   made the subtotal foot (J&J FY2023: a -$151,324m "(residual)" line). Fixed
   by flipping the child's sign and removing the plug. Only an exact -2x match
   is repaired; anything else is left alone.

2. Lines filed directly under LiabilitiesAndStockholdersEquity (Walmart
   FY2020-24, NVIDIA FY2015-18, Alphabet FY2015) landed in a headerless
   "LiabilitiesAndEquity" block after equity. Long-term debt appeared below
   retained earnings. Each such line is re-sectioned by concept: equity
   components to Equity, redeemable/temporary equity to TemporaryEquity,
   everything else to NoncurrentLiabilities, each under a header, in the
   usual order. Zero-valued "Commitments and contingencies" captions are
   dropped.

3. Captions. Concept-name captions and "(residual)" suffixes are replaced by
   ordinary statement captions (src/labels.py).

The statement records what was changed in stmt["normalization"].
"""
import re

from labels import RESIDUAL, display_label

_RANK = {"CurrentAssets": 0, "NoncurrentAssets": 1, "Assets": 2,
         "CurrentLiabilities": 3, "NoncurrentLiabilities": 4, "Liabilities": 5,
         "TemporaryEquity": 6, "Equity": 7, "LiabilitiesAndEquity": 8}
_HEADER = {"CurrentAssets": "Current assets:", "NoncurrentAssets": "Non-current assets:",
           "CurrentLiabilities": "Current liabilities:",
           "NoncurrentLiabilities": "Non-current liabilities:",
           "TemporaryEquity": "Temporary equity:", "Equity": "Stockholders' equity:"}
_EQUITY = re.compile(r"(CommonStock|AdditionalPaidInCapital|PreferredStock|RetainedEarnings|"
                     r"AccumulatedOtherComprehensive|TreasuryStock|MinorityInterest|StockholdersEquity|"
                     r"IssuedCapital|SharePremium|OtherReserves|TreasuryShares|NoncontrollingInterests)")
_TEMP = re.compile(r"(TemporaryEquity|RedeemableNoncontrollingInterest)")
_IS_CF_RESIDUAL = {
    "Other operating expenses, net (residual)": "Other operating expenses, net",
    "Other, net (residual)": "Other items, net",
    "Other operating activities, net (residual)": "Other operating activities, net",
    "Other investing activities, net (residual)": "Other investing activities, net",
    "Other financing activities, net (residual)": "Other financing activities, net",
}


def _bare(c):
    return (c or "").split(":")[-1]


def _reindex(rows):
    remap = {r["idx"]: i for i, r in enumerate(rows)}
    for i, r in enumerate(rows):
        r["idx"] = i
    for r in rows:
        if r.get("sums"):
            r["sums"] = [remap[c] for c in r["sums"] if c in remap]


def _fix_negative_weights(stmt, notes):
    rows = stmt["rows"]
    by = {r["idx"]: r for r in rows}
    drop = set()
    for r in rows:
        if not r.get("residual") or not r.get("value"):
            continue
        for p in rows:
            if not p.get("sums") or r["idx"] not in p["sums"]:
                continue
            for i in p["sums"]:
                x = by[i]
                if (i != r["idx"] and x.get("kind") == "line" and x.get("value")
                        and x["value"] > 0 and x["value"] * -2 == r["value"]
                        and _bare(x.get("concept")) in ("TreasuryStockValue", "TreasuryShares")):
                    x["value"] = -x["value"]
                    drop.add(r["idx"])
                    notes.append(f"sign: {_bare(x['concept'])} weight -1 applied; "
                                 f"removed residual {r['value']:,}")
                    break
    if drop:
        for p in rows:
            if p.get("sums"):
                p["sums"] = [i for i in p["sums"] if i not in drop]
        stmt["rows"] = [r for r in rows if r["idx"] not in drop]
        _reindex(stmt["rows"])


def _resection_balance_sheet(stmt, notes):
    rows = stmt["rows"]
    moved = False
    keep = []
    for r in rows:
        if r.get("kind") == "line" and r.get("section") == "LiabilitiesAndEquity":
            b = _bare(r.get("concept"))
            if b == "CommitmentsAndContingencies" and not r.get("value"):
                notes.append("dropped zero 'Commitments and contingencies' caption")
                continue
            if r.get("residual"):
                pass
            elif _TEMP.search(b):
                r["section"] = "TemporaryEquity"; moved = True
            elif _EQUITY.search(b):
                r["section"] = "Equity"; moved = True
            else:
                r["section"] = "NoncurrentLiabilities"; moved = True
        keep.append(r)
    dropped = {r["idx"] for r in rows} - {r["idx"] for r in keep}
    for r in keep:
        if r.get("sums"):
            r["sums"] = [i for i in r["sums"] if i not in dropped]
    rows = keep
    if moved:
        notes.append("re-sectioned lines filed directly under LiabilitiesAndStockholdersEquity")
    # stable order by section rank; within a section keep the original order
    order = {r["idx"]: n for n, r in enumerate(rows)}
    rows.sort(key=lambda r: (_RANK.get(r.get("section"), 9), order[r["idx"]]))
    # every section with lines gets exactly one header, first in the section
    out, seen = [], set()
    for r in rows:
        s = r.get("section")
        if r.get("kind") == "header":
            if s in seen:
                continue
            seen.add(s)
            out.append(r)
            continue
        if s in _HEADER and s not in seen and r.get("kind") == "line":
            out.append({"idx": -1 - len(out), "label": _HEADER[s], "section": s,
                        "concept": None, "value": None, "kind": "header"})
            seen.add(s)
        out.append(r)
    # headers must precede their section's first row
    final = []
    for s in sorted({r.get("section") for r in out}, key=lambda x: _RANK.get(x, 9)):
        block = [r for r in out if r.get("section") == s]
        block.sort(key=lambda r: 0 if r.get("kind") == "header" else 1)
        final.extend(block)
    stmt["rows"] = final
    _reindex(stmt["rows"])


def _labels(stmt):
    for r in stmt["rows"]:
        if r.get("kind") == "header":
            continue
        if r.get("residual"):
            if stmt["statement_type"] == "BalanceSheet":
                r["label"] = RESIDUAL.get(r.get("section"), "Other, net")
            else:
                r["label"] = _IS_CF_RESIDUAL.get(r["label"], r["label"])
        elif stmt["statement_type"] == "BalanceSheet" and r.get("concept"):
            r["label"] = display_label(r["concept"])


def normalize_statement(stmt):
    """Normalize one clean statement in place and return it."""
    if stmt.get("normalization", {}).get("version") == 1:
        return stmt
    notes = []
    if stmt["statement_type"] == "BalanceSheet":
        _fix_negative_weights(stmt, notes)
        _resection_balance_sheet(stmt, notes)
    _labels(stmt)
    stmt["normalization"] = {"version": 1, "notes": notes}
    return stmt
