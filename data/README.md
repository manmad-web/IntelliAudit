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
- **8 files**, `companyfacts_CIK<10digits>.json`, one per company.
- Real financial facts pulled straight from the **SEC EDGAR** database (every number a company officially reported). Everything else is built from these. Cached so we download once; git-ignored because anyone can re-fetch them.

## `data/clean/`  — the correct statements, no errors ("ground truth")
- **223 files**, named `<CIK>_<YEAR>_<TYPE>.json` — e.g. `104169_2015_BS.json` = Walmart's 2015 **B**alance **S**heet. `IS` = Income Statement, `CF` = Cash Flow.
- Each is one financial statement, assembled from the real numbers above and made to **reconcile** (Assets = Liabilities + Equity, subtotals add up). This is the "before" — the truth with **no errors injected**. We inject errors into copies of these to make the exam.

## `data/benchmark/`  — the benchmark itself (this is what the paper releases)

| File | Lines | Plain meaning | Used for |
|---|---|---|---|
| **`exam.jsonl`** | 1089 | **THE EXAM.** Each line = a statement **with one hidden error** + its transactions, and **nothing else** (no answers, no citation). | Hand this to the auditor/LLM. It must find the error and cite the rule from this alone. |
| **`answer_key.jsonl`** | 1089 | **THE ANSWER KEY.** Each line = the correct answers: is it wrong, what error type, which row, and the exact **FASB ASC citation**. | Kept hidden from the system; used only to **grade** its predictions. |
| **`statements_clean.jsonl`** | 223 | All 223 clean statements in one file (same content as `data/clean/`, consolidated). | (a) a **no-error control set** to check the auditor doesn't false-alarm on clean statements; (b) the "corrected" target for the repair task. |
| **`records.jsonl`** | 1089 | **THE MASTER FILE.** Each line = one complete case with **everything joined**: clean version + error version + transactions + error details + citation. | Convenience / regenerating the split; internal use. `exam` + `answer_key` are just this file cut in two. |
| **`summary.json`** | — | Dataset statistics (counts per company / error-type / citation-tier). | A quick data card. |
| **`PREVIEW.txt`** | — | A few human-readable sample records. | Eyeball the data without opening the big files. |

## Why `exam` and `answer_key` are separate
To stop the system from **cheating (leakage)**: you give it the exam, you withhold the key. A model that could see the citation in its input isn't being tested. (We verified `exam.jsonl` contains **0** ASC codes.)

## How to regenerate everything
```bash
python3 scripts/build_benchmark.py   # raw → clean → records   (deterministic, byte-identical)
python3 scripts/split_dataset.py     # records → exam / answer_key / statements_clean
```
No LLM is used — the generator is the reproducibility guarantee.
