# Team handoff: benchmark first

Status: 4 October 2026 (Pacific). Read this before changing labels or running models.

## What changed

The previous dashboard displayed the answer while collecting a review. The default
now supports an initial blind judgment, an explicit proposal reveal, and a separate
reconciliation. Server-side append-only events preserve the initial submission;
review identity and dataset fingerprint travel with exports. Curator browsing is
an explicit separate mode. A deterministic 20-case, five-company annotation pilot
and a canonical annotation schema/release checker have been added.

The pilot and software are preparation, not completed accountant validation.
No new paid model run or improved model accuracy is claimed in this update.
The existing 48-case capstone results remain immutable development evidence.

## Responsibilities and order

| Role (team assigns a person) | Next deliverable | Completion evidence |
|---|---|---|
| Dataset custodian | Run pilot checks; distribute blind packet only | Manifest and packet hashes; disclosure of any prior answer exposure |
| One accountant | Complete initial reviews, then reconciliation | All 20 first-pass records locked before revealing proposals; dated exports |
| Data/provenance owner | Reconcile accession, units, periods and synthetic evidence | Cell/document source trail and unresolved-case register |
| Annotation owner | Curate review into release schema; document alternatives | Gate report; no unresolved scored fields silently dropped |
| Method owner (capstone) | Freeze applicable retrieval/evidence protocol after review | Corpus/prompt/model IDs, budgets and ablations pinned |
| Analysis/artifact owner | Reproduce results and prepare draft | Raw predictions, denominators, costs, per-company outcomes, reproduction log |

Do not select cases, citations or exclusions based on which model wins. The
accountant may reject the author's proposed label. Retain ambiguous and insufficient
evidence judgments; do not force a paragraph to improve an accuracy table.

## Accountant session

1. Custodian verifies pilot source hashes and starts the default dashboard locally.
2. Reviewer records qualifications and any authorship/answer exposure. Reviews all
   20 cases using only public evidence, selecting sufficient proof alternatives
   where possible and recording uncertainty and missing evidence.
3. Export the first pass. Preselect 10–20% for delayed repeat review, ideally at
   least two weeks later (the machine gate requires at least seven days), with
   shuffled aliases and no access to first answers or proposals. Report intra-rater
   consistency only; related cases may still create memory effects.
4. After the repeat, reveal proposals and reconcile. Record every revision and
   reason; never replace initial or repeated judgments.
5. Curator completes source and dated authority/applicability fields, preserves
   alternatives and unresolved cases, and runs release readiness checks.

The server enforces the complete first pass, a seven-day delay and the frozen
three-case repeat subset before proposal reveal. Repeat aliases and hidden prior
answers are persisted across restarts. Hosted mode adds separate invitation
accounts and a curator workspace; use [deployment instructions](DEPLOYMENT.md)
before sharing the pilot URL.
Maintain that separation in the session plan. The repository includes source keys:
operational blinding assumes the reviewer does not inspect them. It is not a
security boundary against a reviewer deliberately searching for answers.

## Files and ownership

- `data/review_pilot/public_cases.jsonl`: permitted case content.
- `data/review_pilot/curator/proposals.jsonl`: unreviewed proposals and pairing; do not distribute in blind packets.
- `review/`, `docs/ANNOTATION_PROTOCOL.md`: canonical annotation contract and instructions.
- `scripts/check_release_readiness.py`: machine-checkable readiness; fails closed on missing reviews.
- `reviews/`: local operational records, excluded from Git; export and back up securely.
- Companion capstone `research/TEAM_HANDOFF.md`: measured experiments and manuscript status.

Do not commit reviewer identities, local databases, credentials, downloaded
proprietary standards text or review backups. Publish consented/appropriately
pseudonymized annotation records after rights and release checks.
