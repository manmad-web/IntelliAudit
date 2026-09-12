# IntelliAudit-Bench

A **standards-citation benchmark** for LLM financial auditing. Unlike AuditBench
(synthetic tables, GPT-4-authored vague citations) and FinAuditing / AuditFlow
(real XBRL, but *detection / numerical* tasks — no citation output), this
benchmark scores whether a system can name the **governing ASC codification
reference** for a financial-statement violation, on **real 10-K data**, with a
**deterministic, cross-checkable citation ground truth**.

> One-line thesis: *citation is a function of concept × violation, the taxonomy
> linkbase alone under-determines it, LLMs fail it (~26%, cf. AuditBench), and a
> taxonomy-grounded pipeline solves it deterministically.*

## How the dataset is built (pipeline)

```
config.json (real companies + 10 fiscal years)
      │
      ▼
edgar_ingest.py ──► REAL 10-K facts from SEC EDGAR companyfacts  (values are never fabricated)
      │
      ▼
statement_builder.py ──► canonical, RECONCILING balance sheet
      │                   (real reported subtotals as anchors + transparent
      │                    residual "Other, net" lines so Assets == Liab + Equity)
      ▼
injector.py ──► RULE-FIRST error injection (rulebook.json)
      │           the rule pre-specifies the violated standard, so the citation
      │           ground truth is known BY CONSTRUCTION (no LLM in the label loop)
      │
      ├──► citation_resolver.py cross-checks each citation against the OFFICIAL
      │     US-GAAP reference linkbase → tags it linkbase-verified vs expert-authored
      │
      ▼
transactions.py ──► synthetic transactions summing to each real line (optional)
      │
      ▼
data/benchmark/records.jsonl   +   scorer.py (hierarchical citation EM)
```

## Why these choices (correcting common assumptions)

| Decision | Why |
|---|---|
| **Real statement values** (SEC EDGAR) | Kills the "synthetic toy" critique that sinks AuditBench-derived work. Every number is a real reported 10-K fact. |
| **Synthetic transactions** | Real filings never publish ledgers. Transactions are optional flavor for the *detection* sub-task; the *citation* task doesn't need them. |
| **Rule-first injection** | The citation must be known *before* injection. If a model authored the citation, "improving citation" would be circular. |
| **Citation cross-checked, two-tier** | A concept has many linkbase references; the *violation* selects the governing one. `linkbase-verified` = deterministic; `expert-authored` = the hard recognition/classification citations the linkbase doesn't tag on the line. |
| **Hierarchical scoring** | Exact-match on one fuzzy string (AuditBench's 26%) is brittle. Score EM at topic / subtopic / full. |

## Record schema (`data/benchmark/records.jsonl`, one JSON per line)

```jsonc
{
  "sample_id": "IA-AAPL-2023-R01_current_noncurrent_asset_misclass-00",
  "metadata": {"company":"Apple Inc.","cik":"0000320193","fiscal_year":2023,
               "statement_type":"BalanceSheet","period":"2023-09-30",
               "unit":"USD millions","source":"SEC EDGAR companyfacts (real 10-K)"},
  "general_judgement": "Incorrect",
  "rule_id": "R01_current_noncurrent_asset_misclass",
  "error_type": "Misclassification",
  "error_identification": {"error_type":"Misclassification","problematic_entry":11,
                           "affected_xbrl_concept":"us-gaap:InventoryNet"},
  "injection_detail": {"row_concept":"us-gaap:InventoryNet","from_section":"CurrentAssets",
                       "to_section":"NoncurrentAssets"},
  "ground_truth_citations": {
    "asc_full":"ASC 210-10-45-1", "asc_subtopic":"ASC 210-10", "asc_topic":"ASC 210",
    "dqc_rule":"DQC_0015", "dqc_verified": false,
    "linkbase_reference_set":["ASC 852-10-55-10","ASC 210-10-45-1((b))","ASC 210-10-S99-1(...)"],
    "linkbase_verified": true,           // rule ASC IS in the concept's real linkbase set
    "citation_tier": "linkbase-verified",
    "weak_citation": false,
    "rationale": "Current assets are ... a current item under non-current misstates classification."
  },
  "modified_statement_text": "[Time]: 2023-09-30 [SEP]\n[row 0]: ... [SEP] ...",  // AuditBench format
  "gt_table_text": "...clean version...",
  "gt_xbrl_json": {"entity":{...},"facts":[{"concept":"us-gaap:...","value":29965,...}]},
  "self_check": {"clean_reconciles": true, "error_breaks_reconciliation": false}
}
```

`linkbase_verified:true` records are **deterministic ground truth you can trust
blindly**. `expert-authored` records are the hard cases — review those manually
(that's your 50%-human-QC set, à la FinAuditing).

## Install & run

```bash
python3 --version            # 3.9+; standard library only (no pip deps required)

# build the benchmark from real filings (small live test)
python3 scripts/build_benchmark.py --companies AAPL MSFT --years 2022 2023

# full config (8 companies x 10 years)
python3 scripts/build_benchmark.py

# offline / fast (skip the linkbase citation cross-check)
python3 scripts/build_benchmark.py --no-citations
```

Outputs land in `data/clean/` (real reconciling statements) and
`data/benchmark/records.jsonl` + `summary.json`.

## Error taxonomy (rulebook.json)

AuditBench's 4 structural types (Missing Row, Numerical Error, Redundant Row,
Misclassification) **plus** domain rules where citation actually bites — current/
non-current classification (ASC 210-10-45), debt refinancing (ASC 470-10-45),
cash-flow classification (ASC 230-10-45), revenue timing (ASC 606-10-25), leases
(ASC 842-10-25), inventory NRV (ASC 330-10-35), the accounting-equation break
(DQC_0004), negative-value (DQC_0015). Each rule carries an injection recipe, a
detection predicate, and its ASC + DQC citation.

## Evaluation

```python
from src.scorer import score_citation, score_detection
# citation EM @ topic / subtopic / full, crediting the concept's valid linkbase set
```

Experiment design: run baseline LLMs (reproduce AuditBench's ~26% Top-1) vs. your
taxonomy pipeline (deterministic) on the same records; the citation-accuracy gap
is the contribution.

## Known limitations / roadmap (be honest in the paper)

1. **Statement builder** uses a fixed concept template + residual plug lines;
   full **presentation-linkbase** fidelity (exact company line ordering) is a TODO.
2. **Balance sheet only** so far; income statement + cash flow builders are next
   (needed for ASC 606 / 230 rules to fire on real data).
3. **DQC ids are `verified:false`** — cross-check against the official XBRL-US DQC
   ruleset before publishing them as ground truth.
4. **`expert-authored` citations need human validation** (recognition/classification
   standards the linkbase doesn't attach to the line).
5. Overlapping-concept residuals can go negative (e.g. lease liab inside "other");
   a concept-overlap check is a refinement.

## Provenance vs. the three baseline papers

- **AuditBench** (2506.17282): format + task ancestor; we fix its broken citation GT.
- **FinAuditing** (2510.08886): real-XBRL + DQC grounding we borrow; we add citation.
- **AuditFlow** (2606.03031): deterministic-verification method; we target citation,
  which it doesn't score — our differentiation.
```
