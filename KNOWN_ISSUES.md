# Known issues — external audit, September 2026

## v0.5 — built from SEC (Sept 2026)

- US GAAP: 70/70 companies, 1,989 statements, 14,963 items; gate passes (16 checks);
  rule system identifies 6,388/6,388 citable items with 1 false alarm in 1,989 controls.
- IFRS: 31/33 companies, 161 balance sheets, 1,382 items. **Gate fails check 14**
  (8 distinct paragraphs, limit 12) because only balance-sheet rules run. All IFRS citations
  are UNVALIDATED: ifrs.org requires a login for the taxonomy and xbrl.ifrs.org was blocked.
- Builder fixes found by the real data: residual plugs were double-counted (dropped Colgate,
  SAP, Molson Coors statements); net-assets IFRS layout (AstraZeneca, BP, Diageo, Rio) was
  unsupported; non-current receivables were captioned like current ones (Caterpillar);
  arithmetic faults could land on lines no subtotal sums (now excluded, gate check 16).
- Filler got WORSE with more companies: income statements 15.9%, cash flows **33.4%** of
  line magnitude (US). The IS/CF template is now the biggest realism problem.
- US linkbase checks used the committed cache (xbrl.fasb.org blocked): concepts first seen in
  the new companies are not cached, so some records that could verify are UNVALIDATED.

## v0.4 status (re-audit after the v0.3 fixes)

v0.3's regression gate passed, but every check it ran read the **answer key**.
Re-auditing v0.3 from the **exam side only** found that the fixes had not reached
the thing a system under test sees:

| v0.3 exam-side finding | measured on v0.3 | v0.4 |
|---|---|---|
| exam-only keyword script (fact phrase → paragraph), no number read | **455/492 = 92.5%** citation | **36.4%** (gate check 8) |
| supporting facts appeared only on the four rules they identified | presence ⇒ error | on every statement incl. controls; max gap 4.0% per statement type (check 10) |
| evidence `[row i]` numbers from the clean statement located structural errors | 606/631 moved/deleted/inserted cases | caption-keyed evidence, no row numbers |
| R06 fabricated rows had their own "posting to this caption" line | 140/140 | removed; fabricated rows have no evidence, like ~35% of real rows |
| exam ids contained the rule name; exam 100% Incorrect | `IA-AAPL-2015-BS-R07_…` | opaque `EX-…` ids; 220 clean controls (12.5%) |
| every citable fault broke footing → arithmetic found it | 100% of moves | **0.0%**: moves recompute subtotals, measurement faults post the other side (check 13) |
| each statement appears ~17 times → diff the copies | not addressed | 17 exam forms, max one version per statement (check 15) |
| `scripts/make_predictions.py` "blind" baselines read the answer key (gold row, `rule_id`) | 2 results files | moved to `results/legacy_v0.3/`; new baselines read `exam.jsonl` only |
| treasury stock added with weight +1, plugged by a −2× residual | 18 balance sheets (J&J FY2023 plug −$151bn) | sign fixed, plug removed; BS filler 4.1% → **1.0%** |
| Walmart/NVIDIA/Alphabet liabilities filed under L&SE shown after equity with no header | 11 balance sheets | re-sectioned under "Non-current liabilities:" |
| captions derived from concept names ("Accounts payable, current" under non-current) | all balance sheets | ordinary captions; the section header carries current/non-current |
| IS/CF evidence signs: "cost of goods sold +108,831; overhead credit −322,968" | every expense/outflow line | expense and outflow lines oriented; contra events 3–25% |

### Mohsen's seven findings — where each stands

| # | Finding | v0.4 | What is left |
|---|---|---|---|
| 1 | Detection trivial | **Fixed in construction.** Citable faults are invisible to arithmetic; controls are on the exam; no id or format tells. | Unverified until the blind LLM run is repeated on v0.4 (one form per model is enough). Detection-only faults (R04/R05/R06/R07/R12) still break footing — by design, they are the arithmetic gate's job. |
| 2 | Citations guessable | **Fixed.** (error type × statement type) 79% → 34%; exam-only keyword 92.5% → 36%; leave-one-company-out 32%. | See "the citation task is narrow" below. |
| 3 | Answer leaks into the evidence | **Fixed.** Ledger restates the original value in 0.0% of numeric cases; no row numbers; no R06 tell. | Measurement facts state the measurement datum (e.g. NRV = the correct carrying amount). That is the evidence, not a leak; the same template appears as a consistent decoy elsewhere. |
| 4 | Transactions aren't accounting | **Partly.** Signs and contra sizes fixed on every statement. | Still two synthetic movements per line with no opening balance; an accountant will still call it thin. Real ledgers are not published, so evidence stays synthetic. |
| 5 | Citations don't govern the error | **Partly.** `docs/CITATION_POLICY.md` states the governing-paragraph principle; 15 paragraphs, each with a rationale; 177 records paragraph-verified against the linkbase. | 649 records are `expert-authored-UNVALIDATED`. No accountant has reviewed the 15 decisions; the LLM cross-check has not been run on v0.4. |
| 6 | Statements unrealistic | **Partly.** Balance sheets 1.0% filler, real captions. | Cash-flow statements are still a 6-line template: **22.7% filler** (NVIDIA FY2021 77%). Income statements 3.3% overall, but J&J FY2023 shows R&D $457m (real ≈ $15bn) with a −$21.5bn plug — the first matching concept is not always the line the filer used. Row order follows the calculation linkbase, not the presentation linkbase (J&J lists inventories before cash). Needs the filing-linkbase approach applied to IS/CF roles: an online rebuild. |
| 7 | Sample and rule bias | **Largely fixed (v0.5).** 70 US companies across 10 sectors, mid/small caps and loss-makers included; 1,989 statements, 70 clusters. IFRS: 31 filers, 161 balance sheets. | Still no banks, insurers, REITs or utilities (phase 2 needs an unclassified-balance-sheet template). Still 15 US paragraphs. |

### The citation task is narrow — say this before a reviewer does

`scripts/identifiability_check.py` is a ~150-line hand-written rule system that
reads only `exam.jsonl`. It cites **826/826** citable items correctly with **0/220**
false alarms. That was the point (the v0.3 audit found R09/R11 unidentifiable), but
it has a consequence: with 15 governing paragraphs, a system that encodes those 15
rules solves the citation task. The benchmark measures whether a model **knows and
applies** these rules from evidence (compare NRV to carrying amount, apply the
75%/90% lease bright lines, apply the undiscounted-cash-flow step before fair value,
know that a >12-month waiver keeps debt non-current). It does not measure open-ended
standards knowledge.

For a deterministic pipeline this means a high score **on this benchmark alone is
not evidence**: the same team wrote the generator. Credible options, in order of
strength: (1) evaluate the pipeline on benchmarks it was not built against (AuditBench's
original split, FinAuditing); (2) hold out rules — develop the pipeline without
reading `rulebook.json`/`src/evidence.py`, and freeze it before R17–R21 are revealed;
(3) grow the rule set with an accountant well past 15 paragraphs.

### Cannot be fixed (say so in the paper)

- **Real transactions.** Companies do not publish general ledgers. Evidence stays synthetic.
- **Ten years of IFRS XBRL.** SEC required IFRS XBRL from fiscal periods ending after
  15 December 2017; EU ESEF from FY2020. Earlier years exist only as PDFs, which breaks
  the "every value is a tagged fact" guarantee.
- **Proving a governing paragraph.** Which paragraph governs is an accounting judgement.
  It can be made principled (the policy) and validated (accountant agreement, ideally
  two accountants and an agreement statistic). It cannot be made deterministic.
- **Ruling out memorisation** of mega-cap figures. Mitigate with mid/small caps; the
  citation task does not depend on remembering the numbers.
- **DQC ids as labels.** DQC rules are XBRL data-quality checks; they do not describe
  recognition/measurement faults. They could label R07/R12-style faults at most.

---

## Earlier status (kept for the record)

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

Dataset: **1,202 records**, 492 citable (13 linkbase-verified + 479
expert-authored-UNVALIDATED) / 710 detection-only (no-governing-paragraph). See
`data/benchmark/summary.json` for the live, authoritative counts.

**Still open:** sample bias (#7); whether the 8 remaining citations are correct
(needs the accountant); the LLM cross-check and human review still unrun.
