# IntelliAudit — One Pager

## The question
Can an AI auditor not just **find** an error in a financial statement, but **cite the exact accounting rule it breaks** (the FASB ASC codification section)?

## What we're solving (plain words)
LLMs can often say *"this statement looks wrong,"* but they cannot reliably name the **rule** that governs the violation. And there was no fair way to *grade* that skill — the one prior attempt (AuditBench) used vague GPT-written citations that even a perfect retriever could only match ~26% of the time. So we (1) build **the exam** — a benchmark with a trustworthy, machine-checkable answer key — and (2) show a **rule-grounded auditor** can pass it.

## The pipeline: two lanes that meet

**Lane A — Benchmark factory (YOURS, `manmad-web/IntelliAudit`)** — *makes the exam*
1. `edgar_ingest.py` — pull **real 10-K** facts from SEC EDGAR (values are real).
2. `statement_builder.py` — assemble a canonical **BS / IS / CF** that reconciles (Assets = Liabilities + Equity).
3. `rulebook.json` + `injector.py` — inject **one error, rule-first** (the governing ASC citation is fixed *before* the error is made).
4. `citation_resolver.py` — **cross-check** each citation against the official **US-GAAP reference linkbase** → tag `linkbase-verified` vs `expert-authored`.
5. `records.jsonl` + `scorer.py` — the dataset + a hierarchical citation grader.

**Lane B — Auditor pipeline (OLD / team, `financial-audit-capstone`)** — *takes the exam*
- **Stage 0** deterministic gate (`stage0a/0b.py`) — arithmetic + accounting identities; **0% false alarms**.
- **Stage 1** taxonomy citation (`taxonomy_graph.py`, `concept_citation.py`) — concept → ASC from the FASB linkbase; subject-matter (330/470/606) vs presentation (210/220/230) **candidate union**.
- **Stage 2** focused LLM (`stage2_llm.py`) — only on abstains; picks a *grounded* citation, never invents one.
- **AuditPatch** (`finmr_repair.py`) — **81.5% exact repair** on real DQC-labeled filings, deterministic, with certificates.

**Where they meet — the combine (NEW glue, `integration/`)**
- `adapter.py` — turns a benchmark record into the `item` the auditor expects, and hands over the **gold concept** (skipping the auditor's weak concept-mapper).
- `eval_pipeline.py` — runs the auditor's citation logic on the records and grades it with the benchmark scorer.

## Result: the clean answer key breaks the ceiling
Same auditor logic, different exam:

| Exam / picker | Citation accuracy |
|---|---|
| AuditBench — correct cite even *in* the candidate set (oracle) | **26.2%** |
| IntelliAudit-Bench — naive concept-only pick | **50.9%** |
| IntelliAudit-Bench — violation-aware pick / answer-in-candidates | **100%** |

**Reading:** on our data the right citation is recoverable; the ~26% ceiling was AuditBench's inconsistent labels, not the method.

## Why it's novel
- **First** benchmark to score the **governing ASC citation** — on **real filings**, with a **deterministic, cross-checkable** answer key.
- AuditBench: broken GPT citation labels. FinAuditing / FinMR: real XBRL but **no citation output**. AuditFlow: deterministic verification but a **numeric verdict only**.
- **Finding:** citation = *f*(concept × violation); the taxonomy linkbase alone under-determines it (accounts-receivable → ASC 310 not 210; revenue → 606-10-50 disclosure not 606-10-25 recognition) — which is exactly why LLMs *and* naive lookup miss.

## Scale & provenance
1,089 records · 8 companies × 10 fiscal years × 3 statements · values = SEC EDGAR (real) · citations = official US-GAAP 2023 linkbase · transactions = synthetic (sum to real lines). Reproducible: `python3 scripts/build_benchmark.py`.
