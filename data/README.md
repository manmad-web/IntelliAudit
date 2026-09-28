# What's in `data/` — a plain-English map

Three folders. Data flows **raw → clean → benchmark**.

```
data/raw/       real numbers downloaded from SEC        (source material, cache)
   ↓  statement_builder.py
data/clean/     the correct, error-free statements       (the "before")
   ↓  injector.py + rulebook.json + citation_resolver.py
data/benchmark/ the actual test: exam + answer key       (what you ship)
```

## `data/raw/`  — the source material (not shipped; re-downloadable)
- **8 files** (not committed), `companyfacts_CIK<10digits>.json`, one per company.
- Real financial facts pulled straight from the **SEC EDGAR** database (every number a company officially reported). Everything else is built from these. Cached so we download once; git-ignored because anyone can re-fetch them.

## `data/clean/`  — the correct statements, no errors ("ground truth")
- **220 files**, named `<CIK>_<YEAR>_<TYPE>.json` — e.g. `104169_2015_BS.json` = Walmart's 2015 **B**alance **S**heet. `IS` = Income Statement, `CF` = Cash Flow.
- Each is one financial statement, assembled from the real numbers above and made to **reconcile** (Assets = Liabilities + Equity, subtotals add up). This is the "before" — the truth with **no errors injected**, after `src/normalize.py` (sign, section and caption fixes; values unchanged). We inject errors into copies of these to make the exam.

## `data/benchmark/`  — the benchmark itself (this is what the paper releases)

| File | Lines | Plain meaning | Used for |
|---|---|---|---|
| **`exam.jsonl`** | 1756 | **THE EXAM.** Opaque `exam_id`, `form`, statement, ledger evidence and supporting facts. 1,536 items have one hidden fault, 220 are clean. No answers. | Hand this to the auditor/LLM. Score one form at a time or item by item. |
| **`answer_key.jsonl`** | 1756 | **THE ANSWER KEY.** `exam_id` → `sample_id`, judgement, error type, row, and the governing **ASC paragraph** (or null). | Withheld; used only to grade. |
| **`statements_clean.jsonl`** | 220 | The clean statements. | Repair target; reference. |
| **`records.jsonl`** | 1756 | Generator output: exam and key joined. | Regenerating the split; internal. |
| **`summary.json`** | — | Counts per rule, statement type, tier; distinct paragraphs. | Authoritative statistics. |
| **`PREVIEW.txt`** | — | One item per rule with its key. | Eyeballing. |

`data/reference/us-gaap-2023_ref_cache.json` — concept → ASC references from the FASB
reference linkbase, so the benchmark can be rebuilt with no network (`--offline`).

## Why `exam` and `answer_key` are separate
To stop the system from **cheating (leakage)**: you give it the exam, you withhold the key. A model that could see the citation in its input isn't being tested. (`scripts/check_triviality.py` verifies `exam.jsonl` contains no ASC code, rule id or generator tell.)

## How to regenerate everything
```bash
python3 scripts/build_benchmark.py --offline   # clean → records (no network; byte-identical)
python3 scripts/build_benchmark.py             # raw → clean → records (needs SEC access)
python3 scripts/split_dataset.py               # records → exam / answer_key / statements_clean
```
No LLM is used — the generator is the reproducibility guarantee.
