# Provenance — what is YOUR code vs the OLD repo vs NEW glue

Three sources of code meet in this project. This file states exactly which is which
so nothing is mis-attributed.

## YOURS — IntelliAudit-Bench (this repo, `manmad-web/IntelliAudit`)
The **benchmark factory**. Original to this project.

| File | Role |
|---|---|
| `src/edgar_ingest.py` | pull real 10-K facts from SEC EDGAR (cached) |
| `src/statement_builder.py` | build canonical reconciling BS / IS / CF from real facts |
| `rulebook.json` | error rules, each with its governing ASC citation (rule-first) |
| `src/injector.py` | apply a rule → inject one error → attach cross-checked citation |
| `src/citation_resolver.py` | resolve a concept → real ASC from the official US-GAAP linkbase (builds the answer key) |
| `src/transactions.py` | synthetic transactions summing to real line values |
| `src/render.py` | `[row n]` AuditBench text + XBRL-JSON |
| `src/scorer.py` | hierarchical citation EM + detection EM (the grader) |
| `scripts/build_benchmark.py` | orchestrator → `data/benchmark/records.jsonl` |

## OLD — the auditor pipeline (`dakshkashyap/financial-audit-capstone` @ `pipeline-stage0-1-2-evals`)
The **auditor** (student). Team-built (daksh / irvin / man-mad). NOT modified here.

| File (in that repo) | Role |
|---|---|
| `approaches/stage0_deterministic_gate/stage0a.py`, `stage0b.py` | arithmetic + identity gate (0% false alarms) |
| `core/taxonomy_graph.py` | indexed FASB linkbase traverser (concept → ASC + candidate set) |
| `approaches/stage1_taxonomy_citation/concept_citation.py` | subject-matter vs presentation topic + candidate union |
| `approaches/stage1_concept_mapping/edgar_mapper.py` | label → us-gaap concept (dictionary; ~82%, the bottleneck) |
| `approaches/stage2_llm_audit/stage2_llm.py` | focused LLM on abstains, picks a grounded citation |
| `approaches/audit_patch_repair/finmr_repair.py` | AuditPatch — 81.5% deterministic repair on real DQC filings |
| `approaches/full_pipeline/pipeline.py` | Stage 0 + Stage 1 orchestrator (`run_pipeline`) |

## NEW — integration glue (`integration/` in this repo)
Original to this project; the missing bridge that makes the two lanes one system.

| File | Role | Note |
|---|---|---|
| `integration/adapter.py` | benchmark record → auditor `item` (+ gold-concept bypass) | NEW |
| `integration/eval_pipeline.py` | run the auditor's citation logic on the records, grade with the scorer | NEW |
| `integration/pipeline_citation.py` | **vendored** copy of the capstone's `concept_citation.py` | OLD code, copied read-only with attribution header, so the eval runs without cloning the whole capstone |

## The one fix the combine realizes
In the live capstone `full_pipeline`, `MappedRow.asc_candidates` is **never populated**
(the candidate set is dead code) and `edgar_mapper` never imports `concept_citation`.
`integration/eval_pipeline.py` **populates that candidate set** — unioning the
subject-matter topic, the presentation topic, and the real linkbase arcs — which is
what lifts citation from the naive ~51% single pick to 100% recoverable on this data.

## Rule of separation (so the two jobs never blur)
- The **benchmark** (Lane A) contains the answer key — never an auditor.
- The **auditor** (Lane B) never contains the answer key.
- `citation_resolver.py` (yours) and `taxonomy_graph.py` (theirs) both read the same
  FASB linkbase but play opposite roles: yours **writes** the answer key; theirs
  **takes** the exam. They are intentionally NOT merged.
