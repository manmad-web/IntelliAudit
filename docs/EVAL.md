# Evaluation protocol

How to take this benchmark honestly, in three rules.

## 1. Score from content, never from the ID

`sample_id` looks like `IA-AAPL-2015-BS-R01_current_noncurrent_asset_misclass-00`
— it literally contains the injected rule's name. **Never parse `sample_id` to
recover `rule_id` or the error type.** A system (or a scorer) that does this is
reading the answer off the filename, not auditing the statement. Only
`error_identification`, `ground_truth_citations`, etc. inside `answer_key.jsonl`
are legitimate labels, and only at scoring time (rule 2).

## 2. Exam in, key only at score time

1. Feed the system **only** `data/benchmark/exam.jsonl` — it has no labels, just
   `modified_statement_text` + `gt_transaction_data` + `metadata`.
2. Collect predictions: `{sample_id, predicted_asc, predicted_error_type, predicted_row}`.
3. **Only then** load `data/benchmark/answer_key.jsonl` and run
   `python3 scripts/score_predictions.py` to join on `sample_id` and grade.

If your evaluation harness has `answer_key.jsonl` in scope while the system is
still producing predictions, that's a leak — split the process/environment so
the key is genuinely unavailable during inference, not just "unused by convention."

## 3. Read `citable` before scoring citation

`ground_truth_citations.citable` is `false` for ~59% of records (710/1202) —
these are `no-governing-paragraph` cases (e.g. an arbitrary numeric
perturbation) where no single ASC paragraph is the correct answer. Citation
accuracy must be computed **only over `citable: true` records** (492/1202).
Scoring citation over all 1202 records silently rewards/punishes systems for a
question that has no right answer on 59% of the data.

## Before quoting any number

Run the regression gate — it fails loudly if the benchmark has quietly become
guessable or started leaking its own answers:

```bash
python3 scripts/check_triviality.py
```

See `KNOWN_ISSUES.md` for what's still open (sample/rule bias, and the planned
LLM cross-check + human review of `expert-authored-UNVALIDATED` citations,
neither of which has been run yet) before treating any citation number as final.
