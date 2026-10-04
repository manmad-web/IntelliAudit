# Verification record — 4 October 2026

- `python -m unittest discover -s tests -v`: **85 tests passed**. Includes blind
  endpoint leakage checks, saved-review-before-reveal, immutable first submissions,
  reviewer separation, scoped/atomic imports, annotation checks and pilot construction.
- `python scripts/build_review_pilot.py --check`: saved 20-case/five-company pilot
  matches deterministic reconstruction with pinned source hashes.
- Live Chromium/Playwright test: case loading, blind submission, reload with answers
  hidden, explicit reveal, reconciliation, export/import and identity switching
  passed. Desktop (1512 pixels) and mobile (390 pixels) checked; no horizontal
  overflow on mobile or JavaScript runtime errors. Only temporary synthetic review
  records were created. Optional reproduction: `python scripts/smoke_review_browser.py`
  with Playwright and a Chromium browser available; neither is needed to use the app.
- Full twenty-case blind HTML packet built from public inputs only; curator alias
  mapping remains separate and preserves the pilot IDs.
- Release gate: **blocked as expected**, twenty required cases, zero completed
  publication annotations, no completed accountant or repeat review.
- `git diff --check` and JavaScript syntax check passed.

These checks establish tested software behavior, not accounting correctness,
reviewer qualifications, scientific novelty or publication readiness. No paid
model calls were made during this continuation. The legacy source benchmark
exam/key files were not rewritten.
