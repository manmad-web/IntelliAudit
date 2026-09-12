#!/usr/bin/env python3
"""
Scoring — the metric that makes this a *citation* benchmark.

Citation accuracy is scored HIERARCHICALLY against the ground truth, because a
concept legitimately maps to several ASC references; exact-match on one fuzzy
string (AuditBench) is too brittle. We report EM at three granularities:
    topic     : ASC 210          (broad)
    subtopic  : ASC 210-10       (main)  <- headline number
    full      : ASC 210-10-45-1  (strict)

extract_asc() pulls ASC codes from free-text model output. A prediction counts
if it matches the GT rule's ASC at that granularity, OR (optionally, credit=True)
if it falls in the concept's valid linkbase reference set.
"""
import re

_ASC_RE = re.compile(r"ASC\s*(\d{3})(?:-(\d{2,3}))?(?:-(\d+[A-Z]?))?(?:-(\d+[A-Z]?))?", re.I)


def extract_asc(text):
    """Return list of normalized ASC codes at (topic, subtopic, full) from text."""
    out = []
    for m in _ASC_RE.finditer(str(text)):
        topic, sub, sec, para = m.groups()
        code = topic
        for seg in (sub, sec, para):
            if seg:
                code += f"-{seg}"
        out.append(code)
    return out


def _levels(code):
    p = code.split("-")
    return {"topic": p[0], "subtopic": "-".join(p[:2]) if len(p) >= 2 else p[0], "full": code}


def score_citation(pred_text, gt_citations, credit_linkbase_set=True):
    """Return {em_topic, em_subtopic, em_full} in {0,1} for one prediction vs GT."""
    preds = [_levels(c) for c in extract_asc(pred_text)]
    gt_full = gt_citations["asc_full"].replace("ASC ", "")
    gt = _levels(gt_full)
    valid = {gt["topic"]}, {gt["subtopic"]}, {gt["full"]}
    if credit_linkbase_set:
        for c in gt_citations.get("linkbase_reference_set", []):
            lv = _levels(re.sub(r"\(\(.*?\)\)", "", c).replace("ASC ", "").strip())
            valid[0].add(lv["topic"]); valid[1].add(lv["subtopic"]); valid[2].add(lv["full"])
    out = {"em_topic": 0, "em_subtopic": 0, "em_full": 0}
    for p in preds:
        if p["topic"] in valid[0]:
            out["em_topic"] = 1
        if p["subtopic"] in valid[1]:
            out["em_subtopic"] = 1
        if p["full"] in valid[2]:
            out["em_full"] = 1
    return out


def score_detection(pred, record):
    """Basic detection EM: general judgment, error-type, problematic-entry."""
    gj = float(str(pred.get("General Judgment", pred.get("general_judgement", ""))).strip().lower()
               == record["general_judgement"].lower())
    et = float(str(pred.get("error_type", "")).strip().lower() == record["error_type"].lower())
    pe_pred = pred.get("problematic_entry")
    pe_gt = record["error_identification"]["problematic_entry"]
    en = float(pe_pred is not None and pe_gt is not None and int(re.search(r"\d+", str(pe_pred)).group()) == pe_gt)
    return {"em_general_judgment": gj, "em_error_type": et, "em_error_entry": en}


def aggregate(rows):
    keys = rows[0].keys()
    return {k: round(sum(r[k] for r in rows) / len(rows), 4) for k in keys}


if __name__ == "__main__":
    gt = {"asc_full": "ASC 210-10-45-1", "linkbase_reference_set": ["ASC 310-10-45-2"]}
    print("pred '210-10-45-1':", score_citation("It violates ASC 210-10-45-1.", gt))
    print("pred 'ASC 210':    ", score_citation("See ASC 210 area.", gt))
    print("pred wrong:        ", score_citation("Per ASC 606-10-25.", gt))
