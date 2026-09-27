#!/usr/bin/env python3
"""
Exam-visible supporting facts for rules that are not identifiable from the
table + ordinary transactions alone.

Attached on the exam (appended to transaction evidence). Never prints the
clean/original line total. Never names an ASC paragraph — that would leak
the answer key.
"""


def _not_orig(n, *banned):
    """Choose a positive integer that is not any of the banned (clean) amounts."""
    n = int(n)
    banned = {int(x) for x in banned if x is not None}
    if n > 0 and n not in banned:
        return n
    for bump in (1, 2, 3, 5, 7, 11, 13, 17, 19, 23):
        for cand in (n - bump, n + bump, abs(n) // 2 - bump):
            if cand > 0 and cand not in banned:
                return cand
    return 1


def facts_for_exam(rule, clean, mod, meta, row_idx=None):
    """Return extra exam text for this injection, or ''."""
    rid = rule.get("rule_id") or ""
    label = meta.get("row_label") or meta.get("relabelled_label") or "the affected line"
    parts = []

    if rid.startswith("R09"):
        orig = int(meta["original_value"])
        err = int(meta["erroneous_value"])
        unsatisfied = abs(err - orig)
        if unsatisfied <= 0:
            return ""
        parts.append(
            f"Supporting facts — {label}: as of period-end, {unsatisfied:,} of the "
            f"amount recognized on this line relates to goods and services for which "
            f"the customer has not obtained control (performance obligation unsatisfied)."
        )

    elif rid.startswith("R11"):
        orig = int(meta["original_value"])
        err = int(meta["erroneous_value"])
        nrv = orig - max(1, abs(orig) // 20)
        nrv = _not_orig(nrv, orig, err)
        if nrv >= err:
            nrv = _not_orig(err - 1, orig, err)
        parts.append(
            f"Supporting facts — {label}: net realizable value is {nrv:,}. "
            f"No lower-of-cost-or-NRV write-down was recorded."
        )

    elif rid.startswith("R14"):
        orig = int(meta["original_value"])
        err = int(meta["erroneous_value"])
        implied = orig - max(1, abs(orig) // 10)
        implied = _not_orig(implied, orig, err)
        if implied >= err:
            implied = _not_orig(err - 1, orig, err)
        parts.append(
            f"Supporting facts — {label}: a triggering event occurred during the period "
            f"(the reporting unit's fair value fell below its carrying amount). "
            f"The implied fair value of goodwill is {implied:,}. No impairment loss "
            f"was recognised."
        )

    elif rid.startswith("R10"):
        old = meta.get("row_concept") or ""
        indicated = "operating" if "Operating" in old else "finance" if "Finance" in old else "operating"
        parts.append(
            f"Supporting facts — {label}: the contract does not transfer ownership, "
            f"has no bargain purchase option, the term is not for the major part of "
            f"remaining economic life, and the present value of lease payments is not "
            f"substantially all of fair value. Classification indicated by these tests "
            f"is {indicated}."
        )

    elif rid.startswith("R06"):
        val = int(meta.get("fabricated_value") or 0)
        idx = meta.get("post_inject_row", row_idx)
        if idx is None:
            idx = "?"
        if val > 0:
            debit = max(1, val // 5)
            credit = val + debit
            parts.append(
                f"[row {idx}] {label}: posting to this caption: +{credit:,} (increase); "
                f"reclass out of this caption: −{debit:,} (decrease)"
            )

    text = "\n".join(parts)
    if "ASC" in text or "606-" in text or "330-" in text:
        raise RuntimeError("supporting facts must not name a citation")
    return text
