# Legacy v0.3 prediction files — do not quote

These two files were produced by the v0.3 `scripts/make_predictions.py`, which read
`records.jsonl` (the answer key joined to the exam):

* `pred_conceptonly.jsonl` used the **gold** affected concept.
* `pred_stage0mapper.jsonl` used the gold error type, the gold concept, the
  `self_check` flag, branched on `rule_id`, and copied the **gold row** as its
  `predicted_row`.

Neither is a blind prediction, and both are keyed to v0.3 `sample_id`s. They are
kept only so earlier numbers can be traced. The v0.4 `scripts/make_predictions.py`
builds its baselines from `exam.jsonl` alone.
