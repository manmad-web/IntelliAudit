#!/usr/bin/env python3
"""
identifiability_check.py — is every citable case solvable from the exam alone?

The external audit found two rules (R09 revenue timing, R11 inventory NRV)
whose citation could not be derived from anything in the record. This script
is a transparent, hand-written rule system that reads ONLY exam.jsonl (never
the answer key while predicting) and applies textbook US-GAAP tests:

  * classification by caption knowledge (inventory/receivables are current,
    operating-cycle payables are current, long-term debt is not current,
    capex is investing, dividends/buybacks are financing);
  * the measurement tests stated in the supporting facts (NRV vs carrying
    amount, reporting-unit fair value vs carrying amount, recoverability then
    fair value, AFS at fair value, allowance vs expected credit loss, VA vs
    realizable DTA, lease bright lines, contract liabilities vs unsatisfied
    obligations, R&D capitalized, covenant breach without a >12-month waiver).

It is NOT a leaderboard entry: it was written by the people who wrote the
generator. What it shows is that the answer is identifiable from the exam and
what knowledge that takes. A high score here is the ceiling a deterministic
pipeline can reach; the benchmark is informative about models, not about
this script.

    python3 scripts/identifiability_check.py
"""
import collections, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, "data", "benchmark")
N = r"([\d,]+)"


def num(x):
    return int(x.replace(",", ""))


def rows_with_sections(text):
    out, sect = [], None
    for ln in text.splitlines():
        m = re.match(r"\[row (\d+)\]: (.*?)(?: \| (\(?\$[\d,]+\)?))? \[SEP\]", ln)
        if not m:
            continue
        label, val = m.group(2), m.group(3)
        if val is None:
            sect = label.lower()
            continue
        v = num(val.strip("()$")) * (-1 if val.startswith("(") else 1)
        out.append((label, v, sect))
    return out


def fact_violation(f):
    """Return a citation if this fact line shows a violation, else None."""
    fl = f.lower()
    nums = [num(x) for x in re.findall(r"(?<![\w%])(\d[\d,]*)(?!%)", f)]
    if "net realizable value" in fl or "selling prices less costs" in fl:
        carrying, nrv = nums[-2], nums[-1]
        return "ASC 330-10-35-1B" if carrying > nrv else None
    if "reporting unit" in fl:
        m_ca = re.search(r"carrying amount[^\d]*" + N, f)
        m_fv = re.search(r"fair value of the reporting unit " + N + r"|reporting unit fair value " + N, f)
        ca = num(m_ca.group(1))
        fv = num(next(g for g in m_fv.groups() if g))
        return "ASC 350-20-35-1" if fv < ca else None
    if "available-for-sale" in fl:
        ac = num(re.search(r"amortized cost(?: basis)? " + N, f).group(1))
        fv = num(re.search(r"fair value(?: at period-end \(quoted and observable market prices\))? " + N, f).group(1))
        return ("carried", ac, fv)
    if "economic life" in fl:
        own = re.search(r"(?:ownership transfers to the lessee|transfer of title at end of term): (yes|no)", fl).group(1)
        t = int(re.search(r"(\d+)%", fl).group(1))
        p = int(re.findall(r"(\d+)%", fl)[1])
        return ("lease", "finance" if (own == "yes" or t >= 75 or p >= 90) else "operating")
    if "performance obligations" in fl:
        x, z = nums[-2], nums[-1]
        return "ASC 606-10-25-23" if z < x else None
    if "credit loss" in fl or "expected-credit-loss" in fl:
        e, a = nums[-2], nums[-1]
        return "ASC 326-20-30-1" if a < e else None
    if "undiscounted" in fl:
        ca, ucf, fv = nums[-3], nums[-2], nums[-1]
        return "ASC 360-10-35-17" if (ucf < ca and fv < ca) else None
    if "covenant" in fl:
        if "in compliance" in fl:
            return None
        if "more than twelve months" in fl:
            return None
        return "ASC 470-10-45-11"
    if "deferred tax asset" in fl:
        g, a, r = nums[-3], nums[-2], nums[-1]
        return "ASC 740-10-30-5" if g - a > r else None
    if "development costs" in fl:
        return "ASC 730-10-25-1" if nums[-1] > 0 else None
    return None


def solve(e):
    t = e["transaction_data"]
    facts = [ln[2:] for ln in t.split("Supporting facts", 1)[1].splitlines()[1:]] if "Supporting facts" in t else []
    rows = rows_with_sections(e["statement_text"])
    vals = {}
    for l, v, sect in rows:        # duplicate captions are qualified by section in the facts
        q = {"current assets:": "current asset", "non-current assets:": "non-current asset",
             "current liabilities:": "current liability",
             "non-current liabilities:": "non-current liability"}.get(sect)
        vals[l] = v
        if q:
            vals[f"{l} ({q})"] = v
    for f in facts:
        label = f.split(":")[0]
        label = re.sub(r" \([\d,]+\)$", "", label)
        r = fact_violation(f)
        if isinstance(r, tuple) and r[0] == "carried":
            if vals.get(label) is not None and vals[label] != r[2]:
                return "ASC 320-10-35-1"
        elif isinstance(r, tuple) and r[0] == "lease":
            cap = "finance" if label.lower().startswith("finance") else "operating"
            if cap != r[1]:
                return "ASC 842-10-25-2"
        elif r:
            return r
    for label, v, sect in rows:
        lab = label.lower()
        if sect and sect.startswith("non-current assets") and re.search(r"inventor|receivable", lab):
            return "ASC 210-10-45-1"
        if sect and sect.startswith("non-current liab") and re.search(r"accounts payable|accrued liab|accrued comp", lab):
            return "ASC 210-10-45-8"
        if sect and sect.startswith("current liab") and lab == "long-term debt":
            return "ASC 210-10-45-12"
        if sect and sect.startswith("operating") and "property, plant" in lab:
            return "ASC 230-10-45-13"
        if sect and sect.startswith("operating") and re.search(r"dividends paid|repurchases of common", lab):
            return "ASC 230-10-45-15"
    return None


def main():
    exam = [json.loads(l) for l in open(os.path.join(BENCH, "exam.jsonl"))]
    preds = {e["exam_id"]: solve(e) for e in exam}                    # key not loaded yet
    key = {k["exam_id"]: k for k in (json.loads(l) for l in open(os.path.join(BENCH, "answer_key.jsonl")))}
    per = collections.defaultdict(lambda: [0, 0])
    fp = n_clean = 0
    for eid, p in preds.items():
        k = key[eid]
        if k["general_judgement"] == "Correct":
            n_clean += 1
            fp += p is not None
            continue
        g = k["ground_truth_citations"]
        if not g.get("citable"):
            continue
        rid = k["rule_id"].split("_")[0]
        per[rid][1] += 1
        per[rid][0] += p == g["asc_full"]
    tot = [sum(v[0] for v in per.values()), sum(v[1] for v in per.values())]
    print("Identifiability (exam-only rule system; NOT a benchmark result)\n")
    for rid in sorted(per):
        h, n = per[rid]
        print(f"  {rid}  {h:>4}/{n:<4} {100*h/n:5.1f}%")
    print(f"\n  citable solved      {tot[0]}/{tot[1]} = {100*tot[0]/max(1,tot[1]):.1f}%")
    print(f"  false citations on clean controls: {fp}/{n_clean}")


if __name__ == "__main__":
    main()
