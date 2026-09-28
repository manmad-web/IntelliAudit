# IntelliAudit-Bench

A **standards-citation benchmark** for LLM financial auditing. Real 10-K statements
(SEC EDGAR); each exam item is either a clean control or carries one injected fault,
with ledger evidence and period-end supporting facts. For a citable fault, the
answer is the **one FASB ASC paragraph that governs the violation**
(`ASC 330-10-35-1B`, `ASC 470-10-45-11`, …), selected by a written policy and
cross-checked against the FASB reference linkbase.

> **Status (v0.4, Sept 2026).** Mohsen's audit findings on detection triviality, citation guessability and leakage are fixed, and the regression gate now also reads the exam. Still open: 8 companies (expansion configs ready, need SEC access), cash-flow statements still templated (23% filler), and no accountant has reviewed the 15 governing paragraphs. Read [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) before quoting a number.

## What an item looks like

```
[row 1]: Inventories | $13,565 [SEP]             <- statement as shown (foots; arithmetic finds nothing)
...
Transaction evidence — Johnson & Johnson FY2023 (BalanceSheet) ...
[Accounts payable] purchases on credit: +11,128 (increase); payments to vendors: −1,496 (decrease)
...
Supporting facts (period-end reviews):
- Inventories: period-end valuation memo — inventories at cost 13,565; estimated selling
  prices less costs of completion, disposal and transportation 11,181.
- Goodwill: impairment test ... reporting unit fair value 145,960; carrying amount 122,184.
- Long-term debt (25,881): covenant compliance review — was in compliance ...
```
Answer key: `Incorrect`, Numerical Error, row 1, **ASC 330-10-35-1B**. The goodwill and
debt facts are consistent decoys; clean controls carry the same kinds of facts.

## How the dataset is built

```
config.json (companies × fiscal years)             configs/usgaap_expansion.json, configs/ifrs.json
      │
edgar_ingest.py ─► real 10-K facts (SEC companyfacts)
statement_builder.py ─► BS from each filing's own calculation linkbase (IS/CF: template)
normalize.py ─► calc-weight signs, sectioning, real captions (values unchanged)
      │
injector.py + rulebook.json ─► one fault per item (or a clean control)
      │   citable faults keep the statement footing:
      │     moves recompute subtotals; measurement faults post the other side of the entry
      ├─► citation_resolver.py: paragraph-level check vs the FASB reference linkbase
      │                         (offline: data/reference/us-gaap-2023_ref_cache.json)
      ├─► transactions.py: ledger movements keyed by caption
      └─► evidence.py: contrastive supporting facts on every statement
      │
split_dataset.py ─► exam.jsonl (opaque ids, forms) | answer_key.jsonl | statements_clean.jsonl
check_triviality.py ─► 15-check gate, 8 of them exam-only
```

## Run

```bash
python3 --version                                   # 3.9+; standard library only

python3 scripts/build_benchmark.py --offline        # rebuild from committed data/clean (no network)
python3 scripts/build_benchmark.py                  # online: refetch SEC facts + filing linkbases
python3 scripts/split_dataset.py
python3 scripts/check_triviality.py                 # must print GATE PASSED
python3 scripts/identifiability_check.py            # every citable item derivable from the exam?
python3 scripts/make_dataset_card.py
python3 -m unittest discover -s tests               # 36 tests

python3 scripts/score_predictions.py results/<your_predictions>.jsonl [--form N]
```

Rebuilds are byte-identical.

## Numbers (v0.4, `data/benchmark/summary.json`)

1,756 items = 1,536 injected + 220 clean controls, from 220 real statements
(8 companies × FY2015–2024 × BS/IS/CF). 826 citable items over **15 governing
paragraphs in 11 topics**; 178 paragraph-verified against the linkbase, 648
`expert-authored-UNVALIDATED`; 710 detection-only (no single paragraph governs).

| Gate check | v0.3 | v0.4 |
|---|---|---|
| citation guessable from (error type × statement type) | 79.2% | 34.3% |
| exam-only: fact keyword → paragraph, no number read | 92.5% | 36.4% |
| citable faults visible to arithmetic | 100% of moves | 0.0% |
| evidence row numbers locating the injected row | 606/631 | none printed |
| balance-sheet unnamed filler | 4.1% | 1.0% |
| clean controls on the exam | 0 | 220 |

Exam-only reference points: a statement-type prior scores **25.4%** exact paragraph;
the authors' hand-written rule system scores **100%** (see "narrow task" in KNOWN_ISSUES).

## Error taxonomy

AuditBench's four types (Missing Row, Numerical Error, Redundant Row, Misclassification)
split into **detection-only** faults (R04, R05, R06, R07, R12: arithmetic, existence,
sign, identity) and **citable** faults:

| Clause | Rules → paragraph |
|---|---|
| presentation | R01 → 210-10-45-1 · R02 → 210-10-45-8 · R03 → 210-10-45-12 · R08 → 230-10-45-13 · R16 → 230-10-45-15 |
| subject | R09 → 606-10-25-23 · R10 → 842-10-25-2 · R11 → 330-10-35-1B · R14 → 350-20-35-1 · R15 → 320-10-35-1 · R17 → 326-20-30-1 · R18 → 360-10-35-17 · R19 → 470-10-45-11 · R20 → 740-10-30-5 · R21 → 730-10-25-1 |

Why each paragraph wins: [`docs/CITATION_POLICY.md`](docs/CITATION_POLICY.md).

## Multi-error split

`data/benchmark_multi/`: 1,100 items (1–3 faults each, plus 220 clean controls) on the same
real statements; the single-error benchmark is unchanged. See
[`docs/MULTI_ERROR.md`](docs/MULTI_ERROR.md).

## IFRS edition (separate dataset, scaffolded)

`rulebook_ifrs.json` (23 draft rules, 8 of them framework contrasts where the same facts
flip the verdict), `configs/ifrs.json` (36 SEC 20-F/40-F IFRS filers), IFRS citation
grammar and linkbase resolver, output under `data/ifrs/`. Not built yet. See
[`docs/EXPANSION_PLAN.md`](docs/EXPANSION_PLAN.md).

## Documents

[`docs/EVAL.md`](docs/EVAL.md) protocol · [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) ·
[`docs/CITATION_POLICY.md`](docs/CITATION_POLICY.md) · [`docs/EXPANSION_PLAN.md`](docs/EXPANSION_PLAN.md) ·
[`docs/DATASHEET.md`](docs/DATASHEET.md) · [`docs/PROVENANCE.md`](docs/PROVENANCE.md) ·
[`data/dataset_card.json`](data/dataset_card.json)

## Relation to the baseline papers

- **AuditBench** (2506.17282): format and task ancestor; its GPT-4 prose citations are replaced by paragraph identifiers.
- **FinAuditing / FinMR** (2510.08886): real XBRL filings with DQC labels; use it as the out-of-distribution test for any pipeline tuned here.
- **AuditFlow** (2606.03031): symbolic verification, LLM search; it does not score citations.
- **FinRule-Bench** (2603.11339): closest prior work on "which principle is violated" (closed rule set, US GAAP and IFRS). Must be cited and contrasted.
