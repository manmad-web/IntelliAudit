#!/usr/bin/env python3
"""
Score predictions on the multi-error split (data/benchmark_multi/).

Prediction rows:
    {"exam_id": "EXM-…", "predicted_judgement": "Correct" | "Incorrect",
     "errors": [{"row": 12, "error_type": "Misclassification", "asc": "ASC 210-10-45-1" | null}, ...]}

Metrics
  judgement      accuracy; false alarms on clean controls
  detection      error-level precision / recall / F1, a predicted error matching a
                 gold error on its row (pre- or post-injection index); exact error-count rate
  type           accuracy on matched errors
  citation       row-matched: paragraph EM over citable gold errors (recall) and over
                 answered citations on matched citable errors (precision);
                 row-agnostic: per-item multiset overlap of cited paragraphs
                 (for systems that cite without locating)

Usage: python3 scripts/score_multi.py <pred.jsonl> [--form N]
"""
import argparse, json, os, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
from scorer import score_citation  # noqa: E402

KEY = os.path.join(ROOT, "data", "benchmark_multi", "answer_key.jsonl")


def para(asc):
    s = score_citation(asc or "", {"citable": True, "asc_full": asc or "ASC 000", "linkbase_reference_set": []},
                       credit_linkbase_set=False)
    return asc if s and s["em_full"] else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("pred"); ap.add_argument("--form", type=int)
    a = ap.parse_args()
    keys = [json.loads(l) for l in open(KEY)]
    if a.form is not None:
        keys = [k for k in keys if k["form"] == a.form]
    preds = {}
    for l in open(a.pred):
        p = json.loads(l); preds[p["exam_id"]] = p

    fa = miss = ok_j = 0
    tp = n_pred = n_gold = count_ok = type_ok = 0
    cit_gold = cit_hit = cit_ans = cit_ans_hit = 0
    set_gold = set_pred = set_hit = 0
    for k in keys:
        p = preds.get(k["exam_id"], {})
        perr = p.get("errors") or []
        j = (p.get("predicted_judgement") or ("Incorrect" if perr else "Correct")).lower()
        truth = k["general_judgement"].lower()
        ok_j += j == truth
        fa += truth == "correct" and j == "incorrect"
        miss += truth == "incorrect" and j != "incorrect"
        gold = k["errors"]
        n_gold += len(gold); n_pred += len(perr)
        count_ok += len(perr) == len(gold)
        # row matching (each gold matched at most once)
        free = list(range(len(gold)))
        for pe in perr:
            r = pe.get("row")
            hit = next((i for i in free if r is not None and r in
                        {gold[i]["pre_inject_row"], gold[i]["post_inject_row"], gold[i]["problematic_entry"]}), None)
            if hit is None:
                continue
            free.remove(hit); tp += 1
            g = gold[hit]
            type_ok += (pe.get("error_type") or "").lower() == g["error_type"].lower()
            if g["ground_truth_citations"].get("citable") and pe.get("asc"):
                cit_ans += 1
                sc = score_citation(pe["asc"], g["ground_truth_citations"], credit_linkbase_set=False)
                cit_ans_hit += sc["em_full"]; cit_hit += sc["em_full"]
        cit_gold += sum(bool(g["ground_truth_citations"].get("citable")) for g in gold)
        # row-agnostic citation overlap
        gs = Counter(g["ground_truth_citations"]["asc_full"] for g in gold if g["ground_truth_citations"].get("citable"))
        ps = Counter(x for x in (para(pe.get("asc")) for pe in perr) if x)
        set_gold += sum(gs.values()); set_pred += sum(ps.values()); set_hit += sum((gs & ps).values())

    n = len(keys); ctrl = sum(k["general_judgement"] == "Correct" for k in keys)
    P = tp / n_pred if n_pred else 0; R = tp / n_gold if n_gold else 0
    F = 2 * P * R / (P + R) if P + R else 0
    pct = lambda x, d: f"{100 * x / d:5.1f}%" if d else "  n/a"
    print(f"Multi-error scoring: {len(preds)} predictions vs {n} items"
          + (f" (form {a.form})" if a.form is not None else "") + "\n")
    print(f"  judgement accuracy             {pct(ok_j, n)}")
    print(f"  false alarms on controls       {fa}/{ctrl}")
    print(f"  missed items                   {miss}/{n - ctrl}\n")
    print(f"  error detection  P {100*P:5.1f}%   R {100*R:5.1f}%   F1 {100*F:5.1f}%   ({tp} matched)")
    print(f"  exact error count              {pct(count_ok, n)}")
    print(f"  error type on matched          {pct(type_ok, tp)}\n")
    print(f"  citation, row-matched  recall {pct(cit_hit, cit_gold)}  precision {pct(cit_ans_hit, cit_ans)}")
    print(f"  citation, row-agnostic recall {pct(set_hit, set_gold)}  precision {pct(set_hit, set_pred)}")


if __name__ == "__main__":
    main()
