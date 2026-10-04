# Dataset datasheet: provisional source data and review pilot

Status: expert review pending. This document supersedes earlier claims that all
external audit findings were fixed or that the answer key was accounting ground truth.

## Scope and composition

The US-GAAP source has 14,963 items from 1,989 base statements and 70 companies:
1,989 controls, 6,388 provisionally citable faults and 6,586 detection-only faults.
Of the citable labels, 1,363 have a reference-linkbase association and 5,025 are
explicitly unvalidated. The separate IFRS source has 1,382 items from 161 balance
sheets and 31 filers, including 161 controls and 648 unvalidated citable items.
The new review pilot has 20 items, five companies, a narrow revenue-cutoff family,
and zero completed accountant reviews at construction. Its manifest is authoritative
for selection, source hashes and limitations. It is not a held-out model test.

## Construction and provenance

SEC companyfacts and filing calculation structures anchor financial figures.
Income/cash-flow templates, normalization, residual reconciliation, synthetic
component movements and synthetic period-end facts transform those inputs into
exam items. These are not verbatim complete filings or authentic company ledgers.
Use declared currency/scale per item; do not assume all IFRS figures are USD.
Calculation structure does not guarantee original presentation layout.

The capstone's source audit of eight firms found 2,929 signed numeric matches out
of 4,092 rows, plus magnitude-only/derived/unmatched rows and two mismatches.
Eighteen of 226 tables lacked a common accession among matched mapped cells.
These results concern that audited subset, not the whole dataset. See the companion
`research/results/sec_pilot_companies.json` and `sec_accession_consistency.json`.
Original-accession, unit, period, sign and transformation checks remain required.

## Labels and evidence

Rule-first injection supplies author proposals. A reference-linkbase match proves
association, not normative applicability, currency or sufficient supporting facts.
The legacy tag `expert-authored-UNVALIDATED` does not demonstrate an independent
accountant authored or reviewed a record. Some faults intentionally have no single
governing paragraph. Accept alternatives or unresolved outcomes when justified.

The pilot removes one revenue-cutoff fact in ten versions. Residual evidence may
still resolve a case; the proposed insufficiency is a hypothesis for review.
Clean/fault sources can differ on other evidence lines, so paired cases are not
certified minimal counterfactuals. Familiarity across variants can bias review.

## Validation and intended use

Automated regression checks test specified shortcuts and generator consistency.
A generator-aware rule system can exploit a narrow ontology even when these checks
pass. No passing gate proves realistic accounting, absence of all leakage, or
population validity. One accountant will perform blind initial judgments followed
by separate proposal reconciliation. Record expertise, prior exposure, missing
facts and acceptable proof/citation alternatives. No inter-rater validation is
possible with one expert; delayed repeats measure intra-rater consistency only.

Use current records for development and annotation feasibility. Do not label them
a gold-standard release or use inspected cases as a fresh final test. Group company,
base filing, event and variants for splits; preserve revisions and prior scores.

## Reproducibility, distribution and maintenance

Pin generator commit, source/cache files, selection seed and output hashes. Online
refetches may change; determinism applies to fixed inputs and versions, not every
future SEC response. Use a fresh checkout/output directory for historical rebuilds.
`docs/ANNOTATION_PROTOCOL.md` and `docs/RELEASE_GATES.md` define the release process.

Inherited code/data licensing and standards-text redistribution rights remain
unresolved. Public SEC availability is not a blanket public-domain grant for
company-authored filings. Do not redistribute licensed ASC/IFRS text without
permission. Keep operational review identity/backups outside Git; release only
consented, appropriately pseudonymized annotations with explicit rights.
