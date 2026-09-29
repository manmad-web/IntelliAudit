#!/usr/bin/env python3
"""
Regression gate for the failure modes found in the two 2026-09 audits.
Run after every rebuild (build_benchmark.py, then split_dataset.py).
Exits non-zero if the benchmark has become guessable or leaks its answers.

    python3 scripts/check_triviality.py

v0.3's gate passed while an exam-only keyword script scored 92.5% on citation:
every check it ran read the ANSWER KEY's error type, never the exam. Checks
8-15 below read only what a system under test can see (exam.jsonl).
"""
import collections, glob, json, os, re, sys

import argparse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from frameworks import get as _fw  # noqa: E402
_ap = argparse.ArgumentParser()
_ap.add_argument("--config", default="config.json")
_FW = _fw(json.load(open(os.path.join(ROOT, _ap.parse_args().config))).get("framework", "us-gaap"))
BENCH = os.path.join(ROOT, _FW["out_dir"])
CLEAN = os.path.join(ROOT, _FW["clean_dir"])
from jsonl import open_text  # noqa: E402
recs = [json.loads(l) for l in open_text(os.path.join(BENCH, "records.jsonl"))]
exam = [json.loads(l) for l in open(os.path.join(BENCH, "exam.jsonl"))]
key = {k["exam_id"]: k for k in (json.loads(l) for l in open(os.path.join(BENCH, "answer_key.jsonl")))}
inj = [r for r in recs if r.get("record_type", "injected") == "injected"]
fails = []


def check(name, value, limit, worse="above", unit="%"):
    bad = value > limit if worse == "above" else value < limit
    print(f"  {'FAIL' if bad else 'ok  '}  {name:<58} {value:>6.1f}{unit}  (limit {limit}{unit})")
    if bad:
        fails.append(name)


def ledger(text):
    return text.split("Supporting facts")[0]


print(f"Triviality / leakage gate — {len(recs)} records ({len(inj)} injected, "
      f"{len(recs) - len(inj)} clean controls), {len(exam)} exam items\n")

print("Answer-key checks (as in v0.3)")
# 1 — citation guessable from (error type x statement type), citable cases only
cit = [r for r in inj if r["ground_truth_citations"].get("citable")]
m = collections.defaultdict(collections.Counter)
for r in cit:
    m[(r["error_type"], r["metadata"]["statement_type"])][r["ground_truth_citations"]["asc_full"]] += 1
guess = 100 * sum(c.most_common(1)[0][1] for c in m.values()) / max(1, len(cit))
check("1 citation guessable from (err type x stmt type)", guess, 60)
print(f"        citable cases: {len(cit)} / {len(inj)} injected")

# 2 — the LEDGER restates the original value of the broken line. Supporting
# facts are excluded on purpose: for a measurement fault the measurement datum
# (NRV, fair value) IS the evidence, and consistent facts of the same shape
# appear on other lines and on clean controls (checks 9 and 10).
num = [r for r in inj if "original_value" in (r.get("injection_detail") or {})]
amt = re.compile(r"[+−-]([\d,]+) \((?:increase|decrease)\)")
leak = 0
for r in num:
    printed = {int(x.replace(",", "")) for x in amt.findall(ledger(r["gt_transaction_data"]))}
    leak += abs(int(r["injection_detail"]["original_value"])) in printed
check("2 numeric cases whose ORIGINAL value is a ledger amount", 100 * leak / max(1, len(num)), 5)

# 3 — deleted row still named in the evidence
miss = [r for r in inj if r["error_type"] == "Missing Row"]
still = sum(1 for r in miss if f"[{r['injection_detail'].get('row_label')}" in r["gt_transaction_data"])
check("3 deleted rows still named in the ledger", 100 * still / max(1, len(miss)), 80)

# 4 — fabricated-row label diversity
fab = [r for r in inj if r["error_type"] == "Redundant Row"]
n = len(set(r["injection_detail"]["row_label"] for r in fab))
check("4 distinct fabricated labels", n, 8, worse="below", unit="")

# 5 — moved rows always land immediately after a subtotal
mv = [r for r in inj if r["injection_detail"] and "to_section" in r["injection_detail"]]
after_sub = 0
for r in mv:
    lines = r["modified_statement_text"].splitlines()
    tgt = r["injection_detail"].get("row_label")
    for i, ln in enumerate(lines):
        if tgt and f": {tgt} |" in ln and i > 0 and "Total" in lines[i - 1]:
            after_sub += 1
            break
check("5 moved rows sitting directly after a subtotal", 100 * after_sub / max(1, len(mv)), 40)

# 6 — residual filler share of balance sheets
tot = fil = 0
for f in glob.glob(os.path.join(CLEAN, "*_BS.json")):
    s = json.load(open(f))
    ln = [r for r in s["rows"] if r.get("kind") == "line" and r.get("value")]
    tot += sum(abs(r["value"]) for r in ln)
    fil += sum(abs(r["value"]) for r in ln if r.get("residual"))
check("6 balance-sheet magnitude that is unnamed filler", 100 * fil / max(1, tot), 15)
for tag, name in (("IS", "income statement"), ("CF", "cash flow")):
    t2 = f2 = 0
    for f in glob.glob(os.path.join(CLEAN, f"*_{tag}.json")):
        ln = [r for r in json.load(open(f))["rows"] if r.get("kind") == "line" and r.get("value")]
        t2 += sum(abs(r["value"]) for r in ln)
        f2 += sum(abs(r["value"]) for r in ln if r.get("residual"))
    print(f"  info  6{tag[0].lower()} {name} magnitude that is unnamed filler".ljust(66)
          + f"{100 * f2 / max(1, t2):>5.1f}%   (OPEN: IS/CF still use a fixed template, see KNOWN_ISSUES)")

# 16 — every detection-only fault must be visible to arithmetic (else the item
# has no answer: a missing/perturbed line that no subtotal sums)
det = [r for r in inj if not r["ground_truth_citations"].get("citable")]
inv = sum(1 for r in det if not r["self_check"]["error_breaks_reconciliation"])
check("16 detection-only faults invisible to arithmetic", 100 * inv / max(1, len(det)), 0)

# 7 — citation tier honesty (paragraph-level)
v = [r for r in inj if r["ground_truth_citations"]["citation_tier"] == "linkbase-verified"]
ok = sum(1 for r in v if any(re.sub(r"\(\(.*?\)\)", "", x).strip() == r["ground_truth_citations"]["asc_full"]
                             for x in r["ground_truth_citations"]["linkbase_reference_set"]))
check("7 linkbase-verified holding at PARAGRAPH level", 100 * ok / max(1, len(v)) if v else 100, 100, worse="below")

print("\nExam-only checks (what a system under test can see)")
FACT_WORDS = {
    "inventory": "net realizable", "goodwill": "reporting unit", "securities": "available-for-sale",
    "lease": "economic life", "revenue": "performance obligations", "receivable": "credit loss",
    "ppe": "undiscounted", "debt": "covenant", "dta": "deferred tax asset", "rnd": "development costs",
}
FACT_TO_ASC = {"inventory": "ASC 330-10-35-1B", "goodwill": "ASC 350-20-35-1", "securities": "ASC 320-10-35-1",
               "lease": "ASC 842-10-25-2", "revenue": "ASC 606-10-25-23", "receivable": "ASC 326-20-30-1",
               "ppe": "ASC 360-10-35-17", "debt": "ASC 470-10-45-11", "dta": "ASC 740-10-30-5",
               "rnd": "ASC 730-10-25-1"}


def fact_kinds(e):
    t = e["transaction_data"]
    facts = t.split("Supporting facts", 1)[1].lower() if "Supporting facts" in t else ""
    return frozenset(k for k, w in FACT_WORDS.items() if w in facts)


# 8 — the v0.3 shortcut: a script that KNOWS which paragraph each fact kind
# maps to, but never compares a number, and otherwise guesses the majority
# presentation paragraph for the statement type (fit leave-one-company-out).
cit_exam = [e for e in exam if key[e["exam_id"]]["ground_truth_citations"].get("citable")]
hit = 0
for e in cit_exam:
    ks = sorted(fact_kinds(e))
    if ks:
        g = FACT_TO_ASC[ks[0]]
    else:
        maj = collections.Counter(key[x["exam_id"]]["ground_truth_citations"]["asc_full"] for x in cit_exam
                                  if x["metadata"]["cik"] != e["metadata"]["cik"]
                                  and x["metadata"]["statement_type"] == e["metadata"]["statement_type"]
                                  and not fact_kinds(x))
        g = maj.most_common(1)[0][0] if maj else None
    hit += g == key[e["exam_id"]]["ground_truth_citations"]["asc_full"]
check("8 citation from fact keywords, no number compared", 100 * hit / max(1, len(cit_exam)), 60)

# 9 — leave-one-company-out majority over (statement type, fact-kind set)
hit = 0
for e in cit_exam:
    f = (e["metadata"]["statement_type"], fact_kinds(e))
    c = collections.Counter(key[x["exam_id"]]["ground_truth_citations"]["asc_full"] for x in cit_exam
                            if x["metadata"]["cik"] != e["metadata"]["cik"]
                            and (x["metadata"]["statement_type"], fact_kinds(x)) == f)
    hit += bool(c) and c.most_common(1)[0][0] == key[e["exam_id"]]["ground_truth_citations"]["asc_full"]
check("9 citation from (stmt type, fact kinds), LOCO majority", 100 * hit / max(1, len(cit_exam)), 60)

# 10 — does the presence of supporting facts separate injected from clean?
# Compared within a statement type (a system sees the type; cash-flow
# statements carry no fact-bearing lines, and controls hold more of them).
has = lambda e: "Supporting facts" in e["transaction_data"]
ctrl = [e for e in exam if key[e["exam_id"]]["general_judgement"] == "Correct"]
bad = [e for e in exam if key[e["exam_id"]]["general_judgement"] == "Incorrect"]
gap = 0.0
for st in {e["metadata"]["statement_type"] for e in exam}:
    b = [e for e in bad if e["metadata"]["statement_type"] == st]
    c = [e for e in ctrl if e["metadata"]["statement_type"] == st]
    if b and c:
        gap = max(gap, abs(100 * sum(map(has, b)) / len(b) - 100 * sum(map(has, c)) / len(c)))
check("10 max_type |P(facts | error) - P(facts | clean)|", gap, 15)

# 11 — clean controls are on the exam
check("11 exam items that are clean controls", 100 * len(ctrl) / max(1, len(exam)), 10, worse="below")

# 12 — ids and text carry no generator artefacts
tells = re.compile(r"\bR\d\d_|IA-[A-Z]+-\d{4}|FABRICATED|\(residual\)|posting to this caption|\[row \d+\]\s[A-Z]|ASC\s*\d")
n_t = sum(1 for e in exam if tells.search(json.dumps(e)))
check("12 exam items with an id / generator tell", n_t, 0, unit="")

# 13 — citable cases an arithmetic gate can find (footing / identity breaks)
brk = sum(1 for r in cit if r["self_check"]["error_breaks_reconciliation"])
print(f"  info  13 citable cases that break footing (arithmetic-visible)   "
      f"{100 * brk / max(1, len(cit)):>5.1f}%   (by design ~0: citation needs knowledge)")

# 14 — distinct governing paragraphs
paras = {r["ground_truth_citations"]["asc_full"] for r in cit}
check("14 distinct citable paragraphs", len(paras), 12, worse="below", unit="")

# 15 — cross-item diffing: at most one version of a statement per form
per = collections.Counter((e["form"], e["metadata"]["cik"], e["metadata"]["fiscal_year"],
                           e["metadata"]["statement_type"]) for e in exam)
check("15 max versions of one statement inside a form", max(per.values()), 1, unit="")

print()
if fails:
    print(f"GATE FAILED — {len(fails)} issue(s): {', '.join(fails)}")
    sys.exit(1)
print("GATE PASSED")
