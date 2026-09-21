# Known issues — external audit, September 2026

An independent reviewer (with an accountant) audited v0.1: ran three LLMs blind
(Sonnet 5, Haiku 4.5, Qwen3-8B; 132 stratified cases + 30 clean), ran our own
Stage 0/1 pipeline blind, rebuilt the dataset from scratch and verified values
against SEC EDGAR.

**Every checkable claim reproduced exactly on our side.** This file records all
findings, what was fixed in v0.2, and what is still open.

> **v0.3 status: the triviality gate now PASSES on all seven checks.** Findings 1-6 are
> addressed; finding 7 (sample bias) and validation of the remaining citations are open.
> Do not quote accuracy numbers until a blind re-run.

> **v0.2 status (superseded): NOT ready for publication.** Findings 1, 2 and 5 are only
> partly addressed and require an accountant. Do not quote accuracy numbers from
> this dataset yet.

| # | Finding | v0.1 | v0.2 | Status |
|---|---|---|---|---|
| 1 | **Detection trivial** — Sonnet 5 found 131/132 errors, 0 false alarms | — | leak + positional tells removed | ⚠️ partly fixed, needs re-run |
| 2 | **Citations guessable** from (error type × statement type) | 79.2% | 80.7% on a smaller citable set | ❌ **open** |
| 3 | **Answer leaked into the evidence** | 100% of numeric cases | **1.7%** | ✅ fixed |
| 3b | Deleted rows always named in evidence | 100% | 70% (random coverage) | ✅ fixed |
| 3c | Moved rows always directly after a subtotal | always | **0%** | ✅ fixed |
| 3d | Fabricated rows from 4 fixed labels, fixed position | 4 labels | 12 labels, randomised position | ✅ fixed |
| 4 | **Transactions weren't accounting** (wrong signs) | e.g. "dividends declared +47,456 (inflow)" | explicit per-event direction | ✅ fixed |
| 5 | **Citations don't govern the error**; "linkbase-verified" held at paragraph level for only 103/675; 3 of 5 DQC ids wrong; validation never run | subtopic check | strict paragraph check; ungoverned citations removed; DQC ids suppressed | ⚠️ partly fixed |
| 6 | **Statements unrealistic** — unnamed residual filler | ~26% of BS magnitude ($194bn plug) | **16.1%** | ⚠️ partly fixed |
| 7 | **Sample/rule bias** — 8 companies, 5 big tech, no banks/insurers | — | unchanged | ❌ **open** |

## What changed in v0.2

- **Transactions rewritten.** Components only — the line total is never printed, so
  the correct value is no longer handed to the model. Every event carries an
  explicit direction (+ increases / − decreases), so dividends, write-offs and
  depreciation now reduce their line. Coverage is a random ~65% subset including
  residual rows, so "no transaction" no longer identifies filler *or* injected rows.
- **Injection positions randomised.** Moved and fabricated rows land at random
  positions within their section; fabricated label pool widened 4 → 12.
- **Citation tiering made honest.** `linkbase_verified` is now a strict *paragraph*
  match (it was subtopic). Only **31** records now qualify — the previous 675 was an
  artifact of the looser test.
- **Ungoverned citations removed.** R05 (wrong value), R06 (fabricated row),
  R07 (broken accounting identity) and R12 (negative balance) asserted
  ASC 210-10-45-1, which does not govern any of them. They are now
  `citable: false` / detection-only and are excluded from citation scoring.
  **502 of 1,089 records are now detection-only.**
- **DQC ids suppressed** rather than asserted, since none were validated and the
  audit found 3 of 5 wrong.
- **`scripts/check_triviality.py`** added as a regression gate so these failure
  modes cannot silently return.

## Still open — and why

**2 — Citation guessability (80.7%).** Each rule still maps to exactly one ASC
paragraph, and rule ≈ (error type × statement type). This cannot be fixed by
randomisation: for classification faults the same paragraph genuinely governs every
instance. It needs error classes whose citation varies by *account* (inventory NRV →
330, goodwill impairment → 350, receivable allowance → 326, leases → 842), which in
turn need evidence in the record to identify them. **Requires accounting input.**

**5 — Whether the remaining citations are correct.** Removing four wrong ones does
not make the other eight right. The tier is renamed `expert-authored-UNVALIDATED`
to stop implying otherwise. **The governing-paragraph principle — why presentation
(210/220/230) rather than subject (330/505/360) — has never been written down.**
That missing principle is why our own pipeline scores 2.6% blind while having the
correct topic in its candidate set 99% of the time: there is no principled answer
to find.

**7 — Sample bias.** 8 companies, 5 of them big tech, no banks or insurers (where
three rules are undefined), mega-cap figures likely memorised, ~8 clusters so
confidence intervals are far too narrow.

**Unidentifiable rules.** R09 (revenue timing) and R11 (inventory NRV) cannot be
derived from anything in the record — there is no contract or NRV datum. They
should be dropped or given the evidence they need.

## Correction to previously published claims

- The **"concept × violation"** finding is **not established by this data**. Citations
  differ by rule because the rulebook was written that way, with no stated
  accounting principle. Retracted pending accountant review.
- `DATASHEET.md` described an LLM cross-check and human expert review. **Neither was
  ever run.** Corrected.


---

# v0.3 — issues 6 and 2 closed

**#6 residual filler: 26% → 4.1%.** Root cause was that the us-gaap `stm/` linkbases
are a generic FASB template, not any filer's structure. The fix: `companyfacts`
carries the **accession number** of the 10-K each fact came from, so we fetch that
filing's own `*_cal.xml` and rebuild the statement from the company's real
calculation tree (`src/filing_structure.py`). Apple FY2017 now resolves to its
actual 22 lines with **0.0% residual** — the $194bn plug is a properly named
"Available-for-sale securities, non-current".

**#2 citation guessability: 79.2% → 48.0%.** Two changes:
1. Added subject-matter rules derivable from concepts already in companyfacts —
   **R13 lease operating/finance (ASC 842-10-25-2)**, **R14 goodwill impairment
   (ASC 350-20-35-1)**, **R15 AFS fair value (ASC 320-10-35-1)**. The two main
   buckets are now genuinely hard: Misclassification/BalanceSheet majority **28%**
   (four competing citations), Numerical/BalanceSheet **35%** (three).
2. **R04 (missing row) made detection-only.** `ASC 210-10-45-1` for an arbitrary
   omitted line was the same catch-all the audit flagged on R05/R06/R07/R12.

Dataset: **1,231 records**, 521 citable / 710 detection-only.

**Still open:** sample bias (#7); whether the 8 remaining citations are correct
(needs the accountant); the LLM cross-check and human review still unrun.
