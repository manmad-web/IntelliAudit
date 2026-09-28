# Datasheet — IntelliAudit-Bench

*How the dataset was built (the reproducibility artifact). AuditBench documented
its construction with GPT-4 **prompts** because its data is LLM-generated. Ours is
**deterministic code**, so the artifact is this datasheet + a re-runnable generator —
a stronger reproducibility claim: `python3 scripts/build_benchmark.py` yields
byte-identical records, every time.*

## 1. Motivation
Benchmark whether an auditor can **cite the governing FASB ASC standard** for a
financial-statement violation — a task AuditBench scored with broken labels and
FinAuditing/AuditFlow do not score at all.

## 2. Composition
1,756 exam items over 220 real statements (8 companies × FY2015–2024 × {balance
sheet, income statement, cash flow}): 1,536 injected faults (one per applicable rule
per statement) and 220 clean controls. 826 injected items are citable (15 governing
paragraphs); 710 are detection-only. `data/benchmark/summary.json` is authoritative.

## 3. Collection & construction process (deterministic)
1. **Real values** — `src/edgar_ingest.py` reads SEC companyfacts (10-K, `fp=FY`).
2. **Statements** — balance sheets from each filing's own calculation linkbase
   (`src/filing_structure.py`); income and cash-flow statements from a fixed template
   with labelled residual lines (still ~23% filler on cash flows — open).
3. **Normalization** — `src/normalize.py`: calculation-weight signs (treasury stock),
   section fixes, ordinary captions. Values unchanged except the sign fix.
4. **Rule-first injection** — `src/injector.py` applies one `rulebook.json` rule.
   Citable faults keep the statement footing; detection-only faults break it.
5. **Citation cross-check** — `src/citation_resolver.py`: strict paragraph match
   against the FASB US-GAAP 2023 reference linkbase (`linkbase-verified`), else
   `expert-authored-UNVALIDATED` per `docs/CITATION_POLICY.md`. Offline rebuilds use
   `data/reference/us-gaap-2023_ref_cache.json`.
6. **Evidence** — `src/transactions.py` (ledger movements keyed by caption; the
   company's books for measurement faults, the true ledger otherwise) and
   `src/evidence.py` (contrastive supporting facts on every statement).
7. **Split** — `scripts/split_dataset.py`: opaque exam ids, 17 forms, withheld key.

**No LLM is used anywhere in the build.** The generator is the disclosure.

## 4. Preprocessing / normalization
Values scaled to $millions; residual lines absorb template gaps (labelled, not
injectable). Known artifact: overlapping-concept residuals can be negative (e.g.
lease liability inside "other").

## 5. Optional LLM-in-the-loop (with prompts, AuditBench-style)
Only two places an LLM would enter — documented here so the artifact is complete:

**(a) Richer transaction narratives** (`transactions.generate_with_llm`, off by default). If enabled, disclose this prompt:
> *"You are a financial-data expert. Given this statement line `<label> = <value>`, generate 2–4 realistic business transactions that sum EXACTLY to `<value>`. Output each as a short event + amount, then `[Explanation: <value> = a + b − c]`."*

**(b) Cross-check judge** (`scripts/cross_check_llm.py`) — the blind auditor prompt is embedded in that script (System + User), reproduced in the paper appendix.

## 6. Validation — what has and has not been done

Done (automated): `scripts/check_triviality.py` (15 checks, 8 exam-only);
`scripts/identifiability_check.py` (every citable item derivable from the exam;
0 false alarms on controls); 36 unit tests; byte-identical rebuilds.

**Not done:** accountant review of the 15 governing paragraphs and of a sample of
items; the independent-LLM cross-check (`scripts/cross_check_llm.py`) on v0.4; the
blind LLM baselines on v0.4. Until the first is done, every
`expert-authored-UNVALIDATED` citation is a policy decision, not validated ground truth.

## 7. Uses & limitations
For citation-attribution and error-detection evaluation. Limitations: single
statements (not multi-document like FinAuditing); injected, not naturally occurring,
errors; 15 governing paragraphs (a hand-written rule system solves the citation task);
8 companies; cash-flow statements templated; row order from calculation, not
presentation, linkbases; DQC ids not used as labels.

## 8. Distribution & maintenance
Repo `manmad-web/IntelliAudit`; regenerate with `scripts/build_benchmark.py`.
Cite SEC EDGAR (public domain) + FASB US-GAAP taxonomy (FASB terms).
