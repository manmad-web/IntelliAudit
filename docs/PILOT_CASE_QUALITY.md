# Pilot construction and source quality

The v2 dashboard packet is ready for a development review of its software and
annotation workflow. It is **not expert-validated accounting gold**. Its twenty
cases come from five related source-company illustrations, rather than twenty
independent audit engagements. The original v1 packet remains unchanged.

`scripts/build_expert_review_pilot.py` produces `data/review_pilot_v2` from the
frozen v1 bundle. It assigns fresh opaque IDs and Company A–E aliases, replaces
one inherited recognition conclusion in the synthetic revenue component
description, and preserves every statement number, sign, row, and substantive
period-end fact. The original company/CIK, old/new ID mapping, source ID, and
variant relationship are stored in the curator proposal projection.

The neutral replacement is **“credits posted to the revenue account.”** The old
phrase stated that performance obligations were satisfied before the reviewer
had assessed recognition. Removing that phrase reduces a conclusion cue. It
does not prove that the rest of a case is sufficient, insufficient, or free of
other shortcuts. No invoice, contract, delivery record, journal entry, or
standards text has been invented to fill missing evidence.

## What the deterministic check establishes

Run these checks before changing the deployed packet:

```bash
python scripts/build_review_pilot.py --check
python scripts/build_expert_review_pilot.py --check
python scripts/check_pilot_quality.py --pilot data/review_pilot_v2 \
  --check-report data/review_pilot_v2/curator/quality_report.json
python -m unittest discover -s tests -p test_pilot_quality.py -v
```

The checker verifies the manifest inventory and digests, pinned source
projection, explicit USD-million units, canonical money formatting and row
labels, declared simulated revenue edits and dependent subtotals, signed
component sums, withholding transformation, public pseudonyms, derived-row
flags, and absence of the inherited recognition phrase in v2. Mutated-data
tests update the manifest digest deliberately, so substantive checks must
still detect corrupted amounts, units, source IDs, reporting dates, and flags.

The current check finds **zero construction errors** in the twenty-case v2
packet. That means the local transformation is consistent with the preserved
inputs. It does not certify SEC filing fidelity, transactions, professional
qualifications, an accounting conclusion, or a governing paragraph.

The full report is at
`data/review_pilot_v2/curator/quality_report.json`. It includes source mappings,
construction kinds, residuals, and pair relationships and belongs only in the
curator workspace. The default command output omits those fields. Do not send
the full report with a blind review packet. Construction keys are present in
this research repository; any future blinded study must also control reviewers'
and models' access to the repository and old answer keys.

## Original filings and reconstructed rows

The inherited builder selects values from SEC companyfacts and reconstructs a
standard income-statement layout. It selects concepts independently and fills
gaps with computed residuals. The committed base files have no original
accession number or per-fact source period/start/filing locator. Raw
companyfacts snapshots are absent from this checkout. A pinned Git commit and
SHA-256 digest identify the local construction input; they do not identify a
specific original filing fact or verify that the selected facts share a
reporting context.

Every public case therefore states that it is a **reconstructed SEC-derived
illustration with simulated evidence**, rather than an unmodified annual
report or authentic ledger. Known fiscal years and statement period ends stay
unchanged. The original reporting/publication date remains unknown (`null`).
`derived_rows` flags identify the residual rows recorded by the reconstructed
base. Do not label those individual rows as independently reported SEC facts.

For curator inspection, the inherited residual values are below. All amounts
are USD millions; these are construction facts, not findings about the
companies' actual reporting.

- International Paper FY2024: other operating expenses −3,256; other income
  or expense 0; other items +825.
- UnitedHealth FY2024: other operating expenses −268,284; other income or
  expense −12,216; other items −837.
- Freeport-McMoRan FY2022: other operating expenses −725; other income or
  expense −322; other items +31.
- Boston Beer FY2022: other operating expenses −613; other income or expense 0.
- Crocs FY2020: other operating expenses −11; other income or expense −7;
  other items +212.

The UnitedHealth residual is especially large and needs source-context review.
A residual that makes a subtotal foot is not independent evidence of its
economic meaning. Original accession, concept, start/end, currency, scaling,
and presentation context must be reconciled before a source-grounded release.
If that cannot be completed, retain the case as a clearly reconstructed
development illustration or exclude it under the frozen release policy.

## Withholding, related variants, and validity

The inherited packet contains full and cutoff-fact-withheld variants from the
same reconstructed/simulated base. Withholding removes exactly one synthetic
revenue cutoff fact. All remaining component movements reconcile to the
displayed statement, including the simulated variants. Component sums do not
recover a hidden clean revenue total.

Removal alone does **not** establish genuine undecidability. The reviewer must
identify what the remaining supplied evidence permits, which missing fact
would change the conclusion, and whether a supported alternative explanation
exists. The curator's insufficient-evidence proposal remains unvalidated.
An expert may reject that proposal or the case itself.

The variants share recognizable statement amounts and wording. Aliases and a
shuffled order reduce direct company-name cues but do not eliminate memory,
cross-case inference, or prior exposure. Keep each related company/filing/event
group together in any later split. Agreement from a small related development
packet is descriptive; it does not establish independence, a population
reliability estimate, or benchmark accuracy.

## Traceability of the review fields

The workflow asks the reviewer to connect each conclusion to supplied evidence
and separately document authority. Its eight substantive dimensions are:

1. **Judgment:** supported correct/incorrect, insufficient evidence, or ambiguous.
2. **Issue classification:** the error type, if supported, without adopting an
   injected rule automatically.
3. **Affected rows:** explicit statement row identifiers, including uncertainty
   about which assertion is actually affected.
4. **Evidence sufficiency:** sufficient, insufficient, or uncertain, with the
   relevant missing fact or limitation in the reasoning.
5. **Authority disposition:** a governing paragraph, justified absence of one,
   insufficient evidence, or unresolved applicability.
6. **Applicable authority and currency:** exact cited identifiers and the source,
   version/effective-date rationale when actually checked.
7. **Acceptable proof sets:** one or more alternative sufficient sets of supplied
   evidence-unit IDs; a verbatim quote links a claimed observation to its unit.
8. **Reasoning:** how those facts support the judgment, relevant alternatives,
   refutations, assumptions, and unresolved questions.

Confidence is an additional self-report, not a substitute for any of these.
A taxonomy association or the old proposed citation is a candidate, not a
validated governing authority. Exact evidence quotes establish local textual
traceability, not source authenticity. The reviewer may leave applicability
unresolved and request more evidence. Software checks cannot supply a missing
professional judgment.

The machine report retains three publication blockers: original source
accession/period reconciliation; independently checked reviewer qualification
for the intended claim; and human review of domain validity and authority
applicability. See the annotation and release-gate documents for the separate
research-release requirements.
