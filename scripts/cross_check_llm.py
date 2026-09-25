#!/usr/bin/env python3
"""
cross_check_llm.py — validate the benchmark's citation ground truth with an
INDEPENDENT LLM (a different model than any used to build the data).

Two jobs:
  1. BASELINE  — how well does a blind LLM auditor cite? (reproduces the ~26%
     AuditBench story; this is a headline baseline for the paper.)
  2. GT AUDIT  — where the independent LLM AGREES with our citation, confidence
     rises; where it DISAGREES on an `expert-authored` record, flag it for human
     review (this is how you validate the non-deterministic tier at scale,
     exactly what FinAuditing did with 50% manual review).

The model NEVER sees the ground-truth citation (leakage-safe; we verified 0/1089
records leak ASC codes into model-visible text). It sees only the error-injected
statement + transactions.

Pluggable client: uses Anthropic or OpenAI if a key is set; otherwise DRY-RUN
prints the exact prompts so you can run them by hand or wire any model.

    ANTHROPIC_API_KEY=... python3 scripts/cross_check_llm.py --n 50 --model claude-...
    OPENAI_API_KEY=...    python3 scripts/cross_check_llm.py --n 50 --model gpt-4o
    python3 scripts/cross_check_llm.py --dry-run --n 3      # just show prompts
"""
import argparse, json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
from scorer import score_citation

RECORDS = os.path.join(ROOT, "data", "benchmark", "records.jsonl")

SYSTEM = (
    "You are an independent financial-statement auditor. You are given ONE financial "
    "statement that contains exactly one injected error, plus supporting transactions. "
    "Identify the error and cite the SINGLE most relevant FASB ASC codification reference "
    "that governs it (e.g. 'ASC 606-10-25-1'). Do not explain. Output strict JSON:\n"
    '{"error_type": "...", "problematic_row": <int>, "asc_citation": "ASC ..."}'
)

def build_prompt(rec):
    return (f"STATEMENT ({rec['metadata']['statement_type']}, {rec['metadata']['company']} "
            f"FY{rec['metadata']['fiscal_year']}):\n{rec['modified_statement_text']}\n\n"
            f"TRANSACTIONS:\n{rec.get('gt_transaction_data','')[:1500]}\n\n"
            "Return only the JSON object.")

def get_client(model):
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        c = anthropic.Anthropic()
        def call(sys_p, user_p):
            m = c.messages.create(model=model, max_tokens=200, system=sys_p,
                                  messages=[{"role": "user", "content": user_p}])
            return m.content[0].text
        return call
    if os.environ.get("OPENAI_API_KEY"):
        from openai import OpenAI
        c = OpenAI()
        def call(sys_p, user_p):
            m = c.chat.completions.create(model=model, max_tokens=200,
                messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": user_p}])
            return m.choices[0].message.content
        return call
    return None

def parse_asc(text):
    try:
        obj = json.loads(text[text.index("{"):text.rindex("}")+1])
        return str(obj.get("asc_citation", ""))
    except Exception:
        import re
        m = re.search(r"ASC\s*[\d\-]+", str(text))
        return m.group(0) if m else ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    recs = [json.loads(l) for l in open(RECORDS)]
    random.Random(args.seed).shuffle(recs)
    recs = recs[:args.n]
    call = None if args.dry_run else get_client(args.model)

    if call is None:
        print("DRY-RUN (no API key or --dry-run): showing the blind prompts.\n")
        for r in recs[:3]:
            print("="*70, "\nSYSTEM:\n", SYSTEM, "\n\nUSER:\n", build_prompt(r)[:900], "\n")
        print("Set ANTHROPIC_API_KEY or OPENAI_API_KEY to run the full cross-check.")
        return

    agree = {"em_topic": 0, "em_subtopic": 0, "em_full": 0}
    tier_agree = {}
    flags = []
    n_scored = 0
    for r in recs:
        out = call(SYSTEM, build_prompt(r))
        pred = parse_asc(out)
        sc = score_citation(pred, r["ground_truth_citations"])
        if sc is None:               # detection-only; citation agreement is undefined
            continue
        n_scored += 1
        for k in agree: agree[k] += sc[k]
        tier = r["ground_truth_citations"]["citation_tier"]
        tier_agree.setdefault(tier, {"n": 0, "sub": 0})
        tier_agree[tier]["n"] += 1; tier_agree[tier]["sub"] += sc["em_subtopic"]
        if tier == "expert-authored" and sc["em_subtopic"] == 0:
            flags.append({"id": r["sample_id"], "gt": r["ground_truth_citations"]["asc_full"], "llm": pred})

    n = n_scored
    print(f"Independent LLM ({args.model}) vs benchmark GT, n={n} citable (of {len(recs)} sampled)")
    if not n:
        print("  no citable rows in the sample")
        return
    print(f"  agreement  EM@topic={agree['em_topic']/n:.1%}  @subtopic={agree['em_subtopic']/n:.1%}  @full={agree['em_full']/n:.1%}")
    print("  by tier (subtopic agreement):")
    for t, d in tier_agree.items():
        print(f"    {t:<18} {d['sub']/d['n']:.1%}  (n={d['n']})")
    print(f"\n  {len(flags)} expert-authored records the LLM disagreed with → HUMAN REVIEW:")
    for f in flags[:15]:
        print(f"    {f['id']}: GT={f['gt']}  LLM={f['llm']}")
    json.dump({"agreement": {k: agree[k]/n for k in agree}, "flags": flags},
              open(os.path.join(ROOT, "data", "benchmark", "cross_check.json"), "w"), indent=2)

if __name__ == "__main__":
    main()
