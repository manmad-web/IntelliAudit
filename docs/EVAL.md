> **Current status (3 October 2026):** Historical construction/policy notes below do not establish expert-reviewed gold. The benchmark-first workflow in [TEAM_HANDOFF](TEAM_HANDOFF.md) and its annotation/release gates control new research. Paid evaluation is paused pending the review pilot. Linkbase membership is association, not accounting applicability.

# Evaluation protocol (v0.4)

## 1. Give a system the exam, never the key

1. Input: `data/benchmark/exam.jsonl`. Each item has an opaque `exam_id`, a `form`,
   `metadata`, `statement_text` and `transaction_data` (ledger movements plus
   "Supporting facts (period-end reviews)"). No labels.
2. The system writes one line per item:
   ```json
   {"exam_id": "EX-…", "predicted_judgement": "Correct" | "Incorrect",
    "predicted_asc": "ASC 606-10-25-23" | null,
    "predicted_error_type": "Numerical Error", "predicted_row": 12}
   ```
   `predicted_asc: null` means "no single paragraph governs" (or abstain).
3. Only then run `python3 scripts/score_predictions.py <file> [--form N]`.

If `answer_key.jsonl` or `records.jsonl` is readable by the process that produces
predictions, the run is not blind. Separate the environments.

## 2. One item at a time, or one form at a time

Every statement appears in ~17 versions (one per applicable rule plus a clean
control). A system that reads several versions of the same statement can diff them
and find the injected row with no accounting at all. Either feed items one at a time
with no memory across items, or score one form (`--form N`); a form holds at most one
version of each statement. Report which you did.

## 3. What is scored

- **Judgement** over every item, including the 220 clean controls. Report false
  alarms on controls separately; a system that calls everything Incorrect scores 87.5%
  accuracy and 100% false alarms.
- **Citation** only over `citable: true` items (826). Detection-only faults (no
  governing paragraph) and controls are skipped, not counted as misses.
  Exact match at topic / subtopic / paragraph; strict (the governing paragraph, not
  any reference the concept carries).
- **Error type and row** over injected items.

## 4. Reference points (exam-only, `scripts/make_predictions.py`)

| System | Judgement acc. | False alarms | ASC paragraph EM |
|---|---|---|---|
| statement-type prior (always Incorrect, one paragraph per statement type) | 87.5% | 100% | 25.4% |
| `identifiability_check.py` (hand-written rules by the benchmark authors) | — | 0% | 100% |

The second row is a ceiling, not a result: it shows every citable item is derivable
from the exam, and that 15 encoded rules are enough to solve the citation task. See
`KNOWN_ISSUES.md` before comparing a deterministic pipeline against it.

## 5. Before quoting a number

```bash
python3 scripts/check_triviality.py        # must print GATE PASSED
```

Say which items were scored (all / one form), which citation tier they fall in
(`linkbase-verified` vs `expert-authored-UNVALIDATED`), and that the unvalidated
tier has not been reviewed by an accountant.
