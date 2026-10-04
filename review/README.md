# Publication annotation records

This directory owns the canonical publication-record schema and unreviewed
examples. It does not contain completed accountant annotations.

- `annotation.schema.json`: JSON Schema Draft 2020-12 structural contract.
- `annotation_template.json`: empty draft, with no reviewer or accepted answer.
- `annotation_example_unreviewed.json`: fictional candidate proofs showing the
  format; no accounting expert has approved them.
- `release_readiness.json`: generated status for the stated case manifest.
  Check its timestamp and hashes; regenerate after any relevant change.
- `annotations/`: place completed versioned publication records here after
  actual review. Do not copy dashboard workflow records here as a shortcut.

See `docs/ANNOTATION_PROTOCOL.md` and `docs/RELEASE_GATES.md` from the repository
root. The default machine gate is:

```bash
python scripts/check_release_readiness.py
```

Current empty records deliberately produce `release_ready: false` and exit 1.
Passing draft validation does not establish review or eligibility. Passing
release checks establishes documented consistency, not source authenticity or
accounting truth. One-accountant completion supports a single-expert-reviewed
claim with delayed intra-rater stability, not independent expert consensus.

The test suite uses explicitly labeled, in-memory mock attestations to exercise
the gate. These mocks must never be exported as reviewed benchmark cases.
