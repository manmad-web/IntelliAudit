# Verification record — 7 October 2026

## Expert-facing pilot v2

- Windows regression run: **151 test cases, 146 passed and five live PostgreSQL
  integration cases skipped locally**. The branch CI runs those external checks
  separately against an isolated TLS PostgreSQL service, as well as Linux and
  Windows regression jobs.
- Both frozen v1 and new v2 packets rebuild deterministically. The v2 quality
  inventory checks all 20 cases/five aliases for format, units, source projection,
  component totals, statement arithmetic and hidden construction identifiers.
  These mechanical checks do not establish original filing or accounting validity.
- Actual browser verification used two clearly synthetic localhost accounts.
  Practice saved zero study events; instructions, tables, evidence categories,
  exact accessible form labels, optional standards questions, case-quality flags
  and draft restoration were checked. A proposal was denied at 19/20 and appeared
  automatically after the twentieth response. Revising proposal feedback preserved
  the original assessment. Cross-account history requests were denied.
- Proposal exposure is idempotent: reopening an available case reuses its first
  exposure record. Initial decisions and resolutions remain immutable. Earlier
  frozen v1 plans retain their aliases, delay, and backup restoration behavior.
- JavaScript syntax and whitespace checks pass. Browser QA accounts are software
  testers, not independently qualified accounting experts or human usability participants.
- Original accessions/per-fact periods, reviewer qualifications, and domain/authority
  validity remain explicitly pending in the private curator inventory. Empty
  annotations continue to fail the publication release gate.

Screenshots of the actual local test workspace are saved in `docs/assets/`.
The current deployment continues to use the existing Render Free and Supabase Free
services; follow `DEPLOYMENT.md` to verify a newly deployed commit before sharing.

## Previous verification — 4 October 2026

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
  and disposable local records were used. The public service subsequently deployed
  successfully on 4 October using Render Free and Supabase Free.

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

`.github/workflows/dashboard-ci.yml` runs the standard-library test suite and
deterministic pilot reconstruction on Linux and Windows with Python 3.12. It also
asserts that an empty annotation directory leaves publication blocked for all
20 cases. A successful software/deployment check does not make proposed labels
reviewed accounting results.

GitHub workflow authorization is now available and the CI configuration is enabled. Windows and an isolated Linux Python 3.12 container both passed all 115 tests against the TLS PostgreSQL test database. The saved pilot also passed deterministic reconstruction on both platforms.
