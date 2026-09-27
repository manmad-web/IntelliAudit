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
1,202 records over 220 real statements (8 companies × 10 fiscal years × {balance
sheet, income statement, cash flow}). Each record = one clean statement + one
injected error + synthetic transactions + labels (see `record_schema` in
`intelliaudit_dataset_showcase.json`). See `data/benchmark/summary.json` for the
current authoritative counts — this file is regenerated on every rebuild.

## 3. Collection & construction process (fully deterministic)
1. **Real values** — `src/edgar_ingest.py` fetches `https://data.sec.gov/api/xbrl/companyfacts/CIK<10-digit>.json`; each line value is the company's actual reported 10-K fact (`fy`, `fp=FY`, `form=10-K`).
2. **Canonical statement** — `src/statement_builder.py` places facts into an ordered us-gaap template; uses the company's **real reported subtotals/totals** as anchors and inserts transparent **residual "Other, net" lines** so every subtotal foots and Assets = Liabilities + Equity, with every number traceable to real data.
3. **Rule-first error injection** — `src/injector.py` applies one recipe from `rulebook.json`. The rule fixes the **governing ASC citation BEFORE** the error is injected (so the label is not a post-hoc guess).
4. **Citation cross-check** — `src/citation_resolver.py` downloads the official **US-GAAP 2023 reference linkbase** (`https://xbrl.fasb.org/us-gaap/2023/us-gaap-2023.zip`, sha256 `b48fbb7b…`, 17,800 concepts) and checks whether the rule's ASC is among the concept's real references → tags `linkbase-verified` vs `expert-authored`.
5. **Transactions** — `src/transactions.py` generates synthetic transactions that sum to each real line value (template-based, deterministic by default).

**No LLM is used anywhere in the current build.** There are therefore no generation
prompts to disclose — the generator *is* the disclosure.

## 4. Preprocessing / normalization
Values scaled to $millions; residual lines absorb template gaps (labelled, not
injectable). Known artifact: overlapping-concept residuals can be negative (e.g.
lease liability inside "other").

## 5. Optional LLM-in-the-loop (with prompts, AuditBench-style)
Only two places an LLM would enter — documented here so the artifact is complete:

**(a) Richer transaction narratives** (`transactions.generate_with_llm`, off by default). If enabled, disclose this prompt:
> *"You are a financial-data expert. Given this statement line `<label> = <value>`, generate 2–4 realistic business transactions that sum EXACTLY to `<value>`. Output each as a short event + amount, then `[Explanation: <value> = a + b − c]`."*

**(b) Cross-check judge** (`scripts/cross_check_llm.py`) — the blind auditor prompt is embedded in that script (System + User), reproduced in the paper appendix.

## 6. Validation protocol — ⚠️ DESCRIBED BUT **NOT PERFORMED**

> **Correction (Sept 2026).** An external audit found that this section described a
> validation protocol as though it had been carried out. **It had not.** Neither the
> LLM cross-check nor the human expert review below was ever run. The harness
> (`scripts/cross_check_llm.py`) exists; it has never been executed. Treat the
> protocol below as *planned*, not *performed*. See `KNOWN_ISSUES.md`.
- **Tier 1 — `linkbase-verified` (13 records):** deterministic; the ASC holds at paragraph level in the concept's official linkbase reference set. No human/LLM needed.
- **Tier 2 — `expert-authored-UNVALIDATED` (479 records):** the governing standard the linkbase does not tag on the line (e.g. recognition ASC 606-10-25). *Planned* validation (still not run): (i) **independent LLM judge** (`cross_check_llm.py`, a *different* model) predicts the citation blind; agreement raises confidence, disagreement flags the record; (ii) **human expert review** of the flagged set — the same 50%-manual-review discipline FinAuditing used.
- **`no-governing-paragraph` (710 records):** detection-only — no single ASC paragraph governs the error type (e.g. an arbitrary numeric perturbation), so these are excluded from citation scoring. See `KNOWN_ISSUES.md`.
- **Leakage:** verified 0/1202 records contain any ASC code in model-visible fields.

## 7. Uses & limitations
For citation-attribution and error-detection evaluation. Limitations: compact
single statements (not multi-document long-context like FinMR); injected (not
naturally occurring) errors; DQC ids `verified:false` pending official-ruleset
cross-check; template ordering, not presentation-linkbase-faithful.

## 8. Distribution & maintenance
Repo `manmad-web/IntelliAudit`; regenerate with `scripts/build_benchmark.py`.
Cite SEC EDGAR (public domain) + FASB US-GAAP taxonomy (FASB terms).
