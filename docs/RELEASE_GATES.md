# Review workflow and release gates

The current v2 pilot is **unreviewed development material**. The publication
schema supports a single qualified expert workflow. Completing it supports a *single-expert-reviewed*
release, not two-expert agreement, independently adjudicated gold, a guaranteed
gold standard or a publication claim. This document does not authorize anyone
to contact the accountant; the team arranges review itself.

The canonical annotation schema and machine checks live in IntelliAudit.
Financial-audit-capstone remains the consumer for model experiments and paper
artifacts. Do not maintain a second divergent annotation schema there.

## Three distinct kinds of record

| Record | Purpose | Can it become evaluation gold automatically? |
|---|---|---|
| Public pilot input | Statement and supplied evidence shown to the reviewer/model. | No. It contains no recommended answer. |
| Dashboard workflow review | Working observations, queries, flags and reviewer decisions. | No. A saved or completed UI status does not certify source/authority/proof validity. |
| Publication annotation | Versioned assertion, provenance, authority, acceptable proofs, recorded expert review and final resolution under `review/annotation.schema.json`. | Only after actual completion and all case/dataset gates; no automatic promotion. |

No converter may infer qualified review from a dashboard flag or silently
populate a paragraph from the old answer key. A proposed citation, taxonomy
association, model suggestion or deterministic rule mapping remains a candidate
until the accountant checks the specific assertion, facts, exceptions and
effective authority. An empty set of annotations is a blocked release.

## Team responsibilities

**Curator/data steward.** Freeze the 20-case pilot input manifest, select the
review order and withhold mappings, old keys and model outputs. Maintain original
source accessions and versions, document hashes, visible/obtainable dates,
synthetic-data labels and release rights. Fix missing source files without
suggesting answers. Preserve all review versions and immutable hashes. A hash is
an integrity check, not a cryptographic signature proving who reviewed a case.

**Student research assistant.** Check file readability, units, arithmetic and
source locators, and optionally prepare a provisional `student_draft`. Keep it
out of the accountant's first-pass packet. Students may raise questions after
that first pass; they do not count as another qualified accountant. Do not mark
a credential as verified without actually checking the stated basis.

**Accountant.** Review every proposed release case, including clean and
insufficient-evidence cases. Identify the assertion(s) rather than accepting
an injected rule. Check source credibility, evidence sufficiency, refutations,
authority scope and dates, acceptable citation sets, and alternative proofs.
Record unresolved items and exclusions. The accountant can reject a case or
require more evidence; a desired class balance does not override that decision.

**Methods/evaluation lead.** Keep model outputs hidden from the accountant,
freeze the scoring and eligible denominators, run leakage and source-memorization
controls, preserve failures, group related cases before splitting, and report
the single-expert limitation. An analyst cannot relabel disagreements to improve
model scores. No new paid model run is required to complete annotation tooling.

## The current 20-case development review sequence (v2)

The active `pilot-v2` packet uses `immediate_reconciliation_v2`, with five
pseudonymized companies and 20 initial assessments. It opens reconciliation
immediately after the complete initial pass. It does not measure independent
delayed intra-rater reliability. Retain the explicit
`reliability_status: reliability_not_measured` disclosure in derived publication
records and reports. Earlier `pilot` v1 artifacts and frozen participant plans
retain their original delay and repeat subset; no automatic migration occurs.

1. Confirm that the public packet contains no old answers, recommended citations,
   model responses, source-rule names or mappings to opposite-label pairs. Use
   the dashboard's blind mode and the packet manifest. Source provenance can be
   furnished without exposing proposed conclusions.
2. Calibrate the accountant on separate examples and freeze the manual version.
   Then collect the accountant's first pass on all 20 pilot cases independently
   of student drafts, old keys and model outputs. Log review time and missing
   sources. Do not pretend a supplied synthetic transaction narrative is an
   authentic ledger.
3. Lock all 20 initial assessments before revealing any proposed answer. Then
   let the accountant intentionally reveal each proposal for comparison. There
   is no required delayed repeat in v2. A post-reveal assessment is reconciliation,
   not an independent blind repeat or a reliability measurement.
4. Let the accountant resolve queries and disagreements with the proposals.
   Retain the original and reconciliation submissions and a reason for every change.
   Unresolved critical evidence or applicability becomes insufficient evidence
   or exclusion. Do not force one governing paragraph when multiple valid sets
   exist, and do not confuse absent retrieval with `no_governing_paragraph`.
5. Produce full publication records under the canonical schema. This may require
   several assertion records from one statement; preserve dependency links and
   issue a new manifest if the unit changes. Source accessions/units/periods and
   every accepted authority/proof must be reconciled, not merely marked done.
6. Freeze the release inventory and run the gate below. Keep an exclusion log
   mapping earlier candidate manifests to the final manifest and explaining all
   removals. Review the exclusion process before consulting model performance;
   dropping hard failures after seeing results invalidates a confirmatory claim.

This development pilot was selected after earlier exploratory work. If model
predictions already exist, newly reviewed labels enable a **retrospective
re-evaluation**, with all label changes and systems rescored symmetrically.
They do not turn those predictions into a new untouched confirmatory experiment.
Keep any designated new-company replication inputs uninspected by method
developers while that comparison is active. A later fresh benchmark release
needs a separately frozen protocol and company/event-disjoint test design.

## Legacy v1 records

`delayed_repeat_v1`, including older publication records without an explicit
`review_plan.protocol_id`, retains its seven-day minimum delay, frozen repeat
selection and full-corpus 10–20% allocation. Preserve both blind submissions,
shuffle fresh opaque aliases, hide previous answers, and reconcile only after
the required repeats. The dashboard's existing frozen 20-case v1 plans selected
three cases. A mixed v1/v2 inventory must be separated into explicitly versioned
cohorts; it cannot claim one homogeneous review protocol.

## What the machine gate enforces

`scripts/validate_annotations.py` checks the portable structural schema plus
cross-field references, hashes, chronology and group consistency. With
`--release`, it requires the declared single-expert workflow, appropriate
qualified-review metadata, a documented final resolution, completed repeat
where selected under v1, or explicit non-measurement disclosure and no delayed
repeat under v2, frozen provenance, and a resolved supported/insufficient state.
It checks full accepted ASC paragraph identifiers, authority version/effective
date/jurisdiction/framework/entity scope, and required applicability facts.
An accepted proof cannot rely on inaccessible post-cutoff evidence or label a
missing fact as observed. Every accepted proof requires relative-minimality
deletion checks and a refutation assessment.

`scripts/check_release_readiness.py` also requires **every case in the explicit
final inventory** to have a passing publication annotation. It rejects empty,
missing, duplicate, unexpected, operational-only or incomplete records. Full
corpus checks require a homogeneous review protocol. Legacy v1 requires 10–20%
delayed-repeat allocation; v2 requires zero repeats and an explicit statement that
independent delayed reliability was not measured. Records must match a review
protocol declared in the case manifest. Case-level review gates remain in effect
even when a development subset skips aggregate checks.
Output is JSON, and blocked readiness returns a nonzero exit code.

```bash
# Draft checks succeed without claiming any review occurred.
python scripts/validate_annotations.py review/annotation_template.json
python scripts/validate_annotations.py review/annotation_example_unreviewed.json

# Empty/incomplete records intentionally return exit code 1 and release_ready:false.
python scripts/check_release_readiness.py \
  --annotations review/annotations \
  --case-manifest data/review_pilot_v2/manifest.json \
  --output review/release_readiness.json

# Full publication-record checks after the accountant has actually completed work.
python scripts/validate_annotations.py --release --complete-dataset review/annotations/*.json
python -m unittest discover -s tests -p test_annotation_validation.py -v
```

Hashes are generated without modifying a record:

```bash
python scripts/validate_annotations.py --print-review-hashes review/annotations/CASE.json
python scripts/validate_annotations.py --print-gold-hash review/annotations/CASE.json
```

The gold digest covers source metadata, values, facts, authority, proof sets and
the final decision. A later edit requires explicit revision, a new resolution
and a new freeze. Do not recompute hashes to conceal an unreviewed change.
The validator cannot verify that a credential is real, that a human performed
the stated work, or that the governing paragraph is semantically correct.

Workflow exports (`schema_version: 2` envelopes containing immutable
`schema_version: 1` events) are separate from publication annotations
(`schema_version: 0.1.0`). The curator manually transfers and verifies the
decision, source/authority/proof information and qualification evidence;
neither export, invitation creation nor a completed dashboard status performs
that work. An exposed later assessment can use `expert_reconciliation` with
truthful exposure flags; it cannot be called `expert_repeat` in v2. Empty
templates and operational event exports continue to fail publication readiness.

## Additional scientific gates

- **Validity:** evidence genuinely supports the task; source/version fidelity,
  realistic assumptions and authority applicability have been checked by the
  accountant. Review disagreement and exclusion causes rather than hiding them.
- **Reliability:** v2 reports independent delayed reliability as not measured.
  Legacy v1 may report delayed intra-rater stability after actual collection
  and analysis, with memory/blinding and one-expert limits. Post-reveal changes
  and proposal agreement do not measure blind stability or expert consensus.
- **Leakage:** inspect actual model/reviewer payloads and access boundaries;
  measure metadata, formatting and rule-guessing controls. Keep all related
  company/filing/event/pair components together before splitting.
- **Evaluation:** preregister supported-success and abstention metrics, eligible
  denominators, model/tool budgets and any meaningful equivalence margin. A
  nonsignificant result does not establish equivalence; few companies make
  uncertainty and population claims especially limited.
- **Rights and reproducibility:** release only permitted evidence/annotations,
  retain authority pointers rather than unauthorized standards text, and have
  a teammate reproduce the tagged artifact. A software test is not an accounting
  review. A passing machine gate does not publish the dataset.
- **Novelty:** compare directly with AuditFlow's graphs/tools/checkers and
  FinancialAuditBench's consistent synthetic engagements. The proposed advance
  is an experimentally tested treatment of incomplete evidence, alternative
  sufficient proofs, refutations and dated authority under cost constraints;
  this remains a hypothesis until the literature and ablations support it.
