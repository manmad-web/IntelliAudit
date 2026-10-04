# Verification record — 4 October 2026

## Hosted pilot update

- Windows with the isolated TLS PostgreSQL database: `python -m unittest discover
  -s tests` runs **115 tests passed**. Without `TEST_DATABASE_URL`, four live
  PostgreSQL checks are skipped; the 111 remaining checks still run.
- Hosted HTTP checks cover login, secure session cookies, revocation, CSRF,
  server-derived reviewer identities, cross-account history isolation, role
  authorization, disabled reviewer imports, full-pilot reveal embargo, opaque
  delayed-repeat routing and curator resolution ordering.
- Whole-protocol tests use an injected clock to verify the seven-day boundary,
  frozen three-case repeat subset, restart persistence, immutable decisions and
  faithful local export restoration without waiting seven calendar days.
- Curator comparisons use preserved initial assessments only and retain separate
  append-only resolutions. They report raw agreement counts, not validated gold.
- Deterministic pilot reconstruction, JavaScript syntax and whitespace checks pass.
- Real PostgreSQL checks cover TLS connections, restart durability, account
  invitations, revocation, atomic rollback, concurrent duplicate suppression,
  the full delayed-repeat protocol and immutable event/resolution tables.
- Browser checks cover curator login, invitation creation, logout, accountant
  login with locked identity fields, case loading, blind submission and disabled
  proposal reveal; no JavaScript errors were observed. Only synthetic accounts
  and disposable local records were used. Final public deployment is pending.

## Previous local pilot verification

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

## Cross-platform pilot checks

The pinned input and generated-artifact hashes describe LF Git blobs. Windows
checkouts made with `core.autocrlf=true` previously failed raw-byte validation
because Git converted line separators to CRLF. `.gitattributes` now keeps JSON,
JSONL and source text at LF in fresh checkouts. The pilot builder also accepts
existing CRLF checkouts by replacing only literal CRLF line separators before
hashing and comparing. It does not parse/reserialize, trim whitespace or alter
escaped newlines inside JSON values. All pinned hashes, company selection, case
IDs and canonical generated artifact bytes remain unchanged; actual content
changes still fail the source pin.

The prepared `docs/ci/dashboard-ci.yml` runs the standard-library test suite and
deterministic pilot reconstruction on Linux and Windows with Python 3.12. It also
asserts that an empty annotation directory leaves publication blocked for all
20 cases. A successful software/deployment check does not make proposed labels
reviewed accounting results.

The CI template is kept outside the executable workflow directory because the current GitHub OAuth credential lacks `workflow` scope. After authorizing that scope, move it to `.github/workflows/dashboard-ci.yml` and push to enable CI. Manual Windows and real PostgreSQL checks described above have passed.
