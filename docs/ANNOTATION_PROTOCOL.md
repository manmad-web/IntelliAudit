# Protocol for an expert-reviewed financial reporting benchmark

Version 0.2, 7 October 2026. **Single-expert publication protocol; no completed human review is asserted.**
One accountant is available. This version must be described as single-expert
reviewed once completed, not independently adjudicated gold or a gold-standard
benchmark. A future second-expert study can strengthen validation.
The accompanying empty template and fictional worked example are development
artifacts. Passing the validator establishes record consistency and documented
release gates; it cannot authenticate a reviewer or establish accounting truth.

## Current dashboard pilot: immediate reconciliation v2

The active `pilot-v2` packet contains 20 cases across five consistently
pseudonymized companies. It uses `immediate_reconciliation_v2`: lock all 20
initial assessments before any proposed-answer reveal, then reconcile immediately.
There is no required delayed repeat and no seven-day waiting period for this
version. Record `reliability_status: reliability_not_measured`; reviewing a
proposal or revising an answer is not an independent blind reliability check.
Frozen v1 artifacts, reviewer plans and earlier submissions retain their original
protocol. Do not relabel or migrate them to obtain an earlier reveal.

For the accountant using the dashboard:

1. Sign in with a personal invitation and read the case scope and supplied
   evidence. Statements are reconstructed illustrations, not verbatim filings;
   component movements and period-end facts are synthetic. The dashboard uses
   USD millions, with parentheses denoting negative values. A missing original
   reporting/publication date remains unknown. Neither pseudonyms nor the supplied
   numbers establish an authentic ledger or an allegation about an issuer.
2. Record the judgement, affected rows, evidence sufficiency, authority status
   and reasoning. Keep an uncertainty or insufficient-evidence assessment when
   the supplied facts cannot establish control transfer or paragraph applicability.
   Optional short notes, an error family and an ambiguity tag aid follow-up;
   they do not supply facts missing from the packet. Select the evidence units
   supporting each proof and retain source questions and refutations.
3. Save each initial assessment. It becomes immutable; browser drafts are not
   submitted records. Complete the whole queue of 20 cases independently of the
   proposed answers, previous keys, peers and model output.
4. Once all 20 are locked, deliberately reveal each proposal and record a separate
   reconciliation. Preserve the original judgement and the reason for any change.
   A recommendation can be rejected; missing source or authority evidence remains
   unresolved rather than becoming correct by agreement.
5. Export the workflow history for curator follow-up. Keep invitations and curator
   access private. For the intended review claim, separately check the reviewer's
   actual framework/assertion experience and qualification; an accounting student,
   exam-level candidate or teammate is not automatically a licensed CPA or a
   qualified US-GAAP expert.

Dashboard event exports use an operational envelope, not the publication schema
below. A curator must manually reconcile sources, authority versions, proof
alternatives, qualifications and the release inventory into complete publication
records. Do not fabricate review metadata or convert a saved UI status into gold.
For a new publication record derived from this pilot, explicitly set
`review_plan.protocol_id: immediate_reconciliation_v2`,
`reliability_status: reliability_not_measured`, `repeat_required: false`,
`minimum_repeat_delay_days: 0`, `repeat_selection_frozen_at: null` and
`repeat_strata: []`. Preserve an exposed later review as `expert_reconciliation`,
including truthful exposure flags, rather than calling it `expert_repeat`.

## The claim this benchmark should measure

Start with a narrow US-GAAP revenue recognition/cutoff task: given the facts
available at a specified reporting and investigation date, identify whether a
particular recognition assertion is supported, contradicted, or unresolved,
and identify applicable authority when the conclusion actually requires it.
Do not label an accounting error as intentional fraud. Intent, audit opinion,
materiality and audit risk require separate evidence and task definitions.

The unit is an **assertion in an engagement context**, not an isolated table
cell or an injected rule. A case contains a dated assertion, source provenance,
an initial observation, obtainable evidence, plausible competing explanations,
and expert-reviewed acceptable conclusions and proof alternatives.
Every score must state whether it assesses answer agreement, applicable
authority, evidence support, acquisition efficiency or operational reliability.

Revenue/cutoff is the first annotation family. A shipping date alone does not
establish transfer of control. Review enforceable contract terms, performance
obligations, control indicators, customer acceptance, return/consignment terms,
collectibility and transaction-price issues **to the extent they affect the
specific assertion**. Missing necessary information produces an unresolved
case, not an invented assumption. Inventory measurement and current/noncurrent
classification enter only after the same sourcing and expert-review gates pass;
they are separate strata, not automatic mappings from revenue or generic ASC
210 examples. Financial institutions require their own scope review.

## Source construction before annotation

1. Freeze one reporting entity, filing accession/version, reporting period,
   investigation cutoff and accounting framework. Store the original accession,
   URL and file hash, source location and retrieval timestamp. Companyfacts is
   an index for discovery, not a substitute for the selected filing. Do not
   combine values from different restatements into a purported original table.
2. For each derived value, retain raw lexical value, currency/unit, scaling,
   sign convention, instant versus duration context, dates and exact
   transformation. A `decimals=-6` attribute does not multiply a value by a
   million. Reconcile totals in the selected filing, including custom tags and
   derived lines. Record unresolved discrepancies rather than filling them with
   an unlabeled residual.
3. Separate observed evidence, derived facts and synthetic supplements.
   Synthetic contracts, invoices and journals must be labeled as such and
   internally consistent. A balanced journal is necessary bookkeeping
   consistency, not evidence that recognition is permissible. Public filing
   values do not authenticate invented transactions or contract terms.
4. Preserve event date, document creation date and the date the investigator
   could have obtained each document. Later restatements, enforcement outcomes
   and hindsight explanations remain evaluator-only when they fall after the
   information cutoff. Publicly obtainable evidence before the cutoff may
   include post-year-end receipts, provided the task permits that audit window.
5. Retain source pointers and permitted excerpts. Record redistribution rights
   separately from read access. Do not package proprietary standards text or
   third-party documents under the new code license. The release can contain
   paragraph identifiers, permitted original annotations and reproducible
   source locators without copying protected paragraph text.

## Authority and applicability

Review authoritative sources for the relevant jurisdiction. For US GAAP,
identify the applicable Codification version and relevant SEC requirements
for the registrant; amendment/transition documents establish adoption changes.
For IFRS, identify the issued standard and amendments applicable to the entity
and reporting period, including jurisdictional endorsement where relevant.
These are contextual precedence decisions, not a universal ranking across
jurisdictions. Official implementation material has the authority actually
assigned to that material; explain its role rather than treating every official
web page as a governing paragraph.

Use taxonomy references and secondary commentary to discover candidates.
Neither their presence nor a concept-name match establishes applicability.
For every accepted paragraph, record:

- Canonical identifier, authoritative locator, checked version/hash and date;
  effective period, transition/adoption basis, jurisdiction and entity scope.
- The precise assertion it governs: presentation, recognition, measurement,
  disclosure or another stated issue. Presentation and subject-specific
  paragraphs may both matter for different assertions.
- Required observed facts, applicable exceptions and counterevidence; an
  explanation connecting those facts to the paragraph's conditions.
- Scope decision and unresolved assumptions. The fiscal year alone is not
  proof of an entity's adoption date or transition election.

Annotate **sets of acceptable citation sets**. Alternatives are OR choices;
within a set, all listed authorities are required. This can represent either
of two legitimate paragraphs, or two paragraphs needed together. Do not select
one convenient label after seeing model output. Extra citations are separately
checked for unsupported applicability; a long list containing the answer does
not earn strict joint success.

Use these authority dispositions precisely:

| Disposition | Meaning | Citation evaluation |
|---|---|---|
| `governing_paragraph` | Evidence and scope support at least one reviewed authority set. | Evaluate against the accepted sets and support requirements. |
| `no_governing_paragraph` | Review establishes that this task's conclusion does not require a specific standards paragraph, such as a deliberately scoped arithmetic reconciliation. | Require justified citation abstention; exclude from exact-paragraph denominator. |
| `insufficient_evidence` | Missing facts or unresolved applicability prevent deciding which authority governs. | Evaluate justified uncertainty/needed evidence; do not call absent retrieval a valid no-paragraph case. |
| `out_of_scope` | Assertion, entity or framework is outside the registered benchmark scope. | Exclude prospectively and retain the reason/count. |
| `unresolved` | Annotation work has not reached a decision. | Development only; never evaluation gold. |

`no_governing_paragraph` is not shorthand for “the reviewer could not find a
paragraph.” `insufficient_evidence` can concern authority while the numerical
conclusion is decidable; record decision sufficiency and authority sufficiency
separately. Mere source absence is not affirmative evidence that an event did
not occur. Evaluate non-occurrence only when completeness of the relevant
register or other negative-evidence assumptions is reviewed.

## Single-expert review, student preparation and uncertainty resolution

One qualified accountant reviews **every case proposed for release**, including
controls, insufficient-evidence cases and every accepted citation/proof
alternative. Record framework and assertion expertise, verified qualification
basis and the accountable verifier using a pseudonymous ID in public artifacts.
Do not fabricate credentials, attestations, timestamps or completed reviews.
A credential alone does not establish expertise in the particular assertion.

A student may prepare source bundles, document transformations, and submit an
independent provisional annotation. Preserve that draft separately as
`student_draft`. It is not a second expert review. Hide the student recommendation,
existing answer key and model outputs during the accountant's first-pass review.
After the accountant completes the frozen blind protocol (all 20 initial
assessments in v2; initial assessments and required repeats in v1), the student
draft may be opened for error checking. Record whether any draft was actually seen and any
subsequent change. The case constructor cannot be presented as an independent
reviewer of their own construction.

Before a pilot, calibrate the manual with the accountant on a small separate
development packet. Freeze terminology and scope; calibration cases cannot
become final test cases. The current 20-case blind development packet can then
measure review effort and expose ambiguous definitions. Its inputs use newly randomized
opaque IDs, contain the actual evidence and provenance placeholders, and omit
old answer keys, suggested citations, model answers and expected conclusions.
The mapping back to source cases is curator-only. Random opaque identifiers
hide task labels, but do not remove substantive cues already present in the
evidence or authenticate synthetic transactions.

Each accountant first-pass record stores the source-bundle hash, manual version,
submission timestamp, conclusion, authority disposition, acceptable authority
sets, proof alternatives, support/refutation facts, missing requirements and
rationale. Preserve this immutable submission before showing other annotations.
A curator can obtain missing documents without suggesting an outcome; log the
intervention. A filesystem key next to a JSON file does not enforce blinding:
use separate reviewer packets and an access-controlled curator workspace.

### Legacy delayed-repeat protocol v1

The following allocation and delay apply only to `delayed_repeat_v1`. Absence of
`review_plan.protocol_id` identifies this legacy protocol for compatibility;
it never opts a historical record into the immediate workflow. Existing frozen
dashboard v1 plans keep their three repeats and seven-day delay. The v2 pilot
instead discloses that independent delayed reliability was not measured.

Select **10–20% of the intended reviewed corpus** for a delayed blind repeat,
stratified across company, conclusion, assertion type and ambiguity level.
Select and freeze this subset before model evaluation, without favoring easy
cases or disagreements. Schedule a new opaque-ID packet at least seven days
later, in a shuffled order, with no access to the previous answer. Preserve
both submissions. Record departures from the delay or blinding rule. For small
packets use the nearest achievable count and state the rounding rule; for 16
cases, two or three repeats are feasible. The full release should disclose the
actual repeat fraction and strata rather than extrapolate from a tiny pilot.

Report delayed **intra-rater stability**, including conclusion/authority
confusion matrices, citation-set agreement and proof changes. This is not
inter-rater agreement, independent adjudication or evidence that two experts
agree. Do not report an inter-rater kappa from a student-accountant pair or two
passes by the same person. Paired repeat stability can reveal inconsistency,
but stable judgments may still be wrong. Memory and incomplete blinding remain
limitations even after a week.

### Final resolution for either protocol

After the complete first pass and any required legacy repeat, the accountant resolves student
queries and self-disagreements in an explicit `single_expert_resolution` record,
explaining changes or retaining uncertainty. An unresolved critical source,
contract, scope or authority issue must produce insufficient evidence or
exclusion; it must not be decided by majority model vote. A second qualified
specialist consultation is an optional future strengthening step, not an
already completed check. Do not delay the documented development release merely
because that second reviewer is unavailable, but keep the claim bounded.

For a future dual-expert extension, obtain independent qualified reviews from
two people before discussion and use a third qualified adjudicator for material
disagreements. Preserve those records under a separately versioned protocol.
The current schema and release validator intentionally enforce only the declared
single-expert workflow and do not imply that extension has occurred.

Report exclusions, unresolved cases, revisions after repeat, accountant effort
and student effort separately. New valid alternatives discovered after freeze
require a versioned erratum and symmetric rescoring of all systems. Existing
keys remain provisional until reviewed through this workflow.

## Sufficient evidence and refutation

For each supported conclusion, the accountant identifies one or more **minimal
sufficient proof sets relative to the annotated evidence universe**. A set
contains facts, source joins, governing authority if needed, and explicitly
reviewed assumptions. Alternative valid paths are allowed. Edges must identify
the same invoice, customer, contract, shipment, receipt and reporting period
where those joins are required; shared keywords are not a join.

Delete each fact from a proposed proof and ask whether the same definitive
conclusion remains supported. Record the result and rationale. Failure of this
test means the set is sufficient but not minimal, or the deletion test needs
review. This is an annotation check, not a proof of global logical minimality.
Every proof also identifies relevant refutations and explains why they are
resolved or why they invalidate the conclusion. Opposing facts cannot simply
be omitted from a high-scoring submitted witness.

For cases with insufficient evidence, annotate the missing fact requirements
and which obtainable evidence could resolve them. Some cases deliberately
remain unidentifiable even after all permitted acquisitions. Those cases test
calibrated abstention, not failed retrieval. Do not require a definitive proof
for a conclusion that the evidence cannot support.

The process score checks server-observed acquisitions, provenance joins,
sufficient proof recovery and treatment of contradictory evidence. It does
not claim access to a model's internal reasoning or prove causal use of a
quoted document. A correct guessed label receives answer credit but no
evidence-supported success credit. Report both.

## Leakage, memorization and counterfactual checks

Before test freeze, run all applicable checks and retain code, inputs, outputs
and reviewer disposition. `not_applicable` requires a reason and cannot be used
to avoid a relevant failed test.

1. Scan every actual inference payload, tool catalog, filename, ID, metadata
   and error message for gold/rule labels, corrected values, proof edges,
   paragraph keys and split markers. Audit the runner's filesystem, network
   and cross-case memory; opaque IDs alone do not isolate gold.
2. Evaluate label-only, statement-type-only, formatting/position, document-count,
   evidence-presence and source-company baselines. Fit mappings on development
   data only. Report class balance and uncertainty; choose failure thresholds
   prospectively rather than after inspecting the final test.
3. Pair minimally changed facts that reverse or resolve the conclusion while
   preserving style, amounts and irrelevant risk motifs where possible.
   Independently review that the intervention changes the target assertion and
   does not introduce unrelated impossibilities. Also include **invariant**
   perturbations, such as harmless formatting changes, that should not change
   the conclusion. Do not make every pair opposite by construction.
4. Remove or withhold a required fact: a valid system should lose definitive
   support when no alternative proof remains. Add plausible refuting evidence
   and test whether the model revises appropriately. Preserve realistic source
   reliability differences rather than assuming every document is true.
5. Probe memorization using controlled entity masking, recomputed magnitude
   perturbations and genuinely later source events where feasible. These are
   stress tests, not proof of a training-data cutoff. Public SEC reports and
   published generators can remain memorized or reconstructible.
6. Check near duplicates, shared templates and related events across splits.
   Counterfactuals, source variants, original/restated versions and all cases
   sharing a company/event must remain in one dependency group. Keep the final
   test undisclosed until evaluation is complete, then follow the release policy.

## Splits, inference and statistical claims

Construct dependency groups **before augmentation** using connected components
over company, filing, event and pair identifiers. Assign whole components to a
split, including any group connected through a shared filing or event. The
validator rejects directly shared group IDs in different assigned splits;
curation must also normalize aliases and detect implicit relationships that a
string comparison cannot discover. Development results already inspected in
this repository cannot be relabeled as final test results.

With only five to ten companies, final population claims must remain narrow.
Do not distribute eight firms across many tiny splits and call the resulting
interval precise. A sensible sequence is a development annotation pilot,
followed by fresh held-out company/event components when affordable. Leave-one-
company-out development analysis is useful for diagnosis; repeated model
selection on those folds does not create a blinded final test.

Preregister the supported-success metric, eligible authority denominator,
noninferiority/equivalence margins, failure handling, budget and stopping rule.
Margins must reflect meaningful auditing consequences and be chosen before
seeing test differences. Non-significance is not equivalence; equivalence
requires the entire paired interval inside both margins, and noninferiority
requires its lower bound above the negative margin. Report clean specificity,
missed errors, false citations, necessary/unnecessary abstention and their
cluster-level distributions, not just an aggregate citation percentage.

Use paired comparisons on the same cases and observation/tool budget. Account
for company/event dependence; case augmentation does not increase independent
sample size. Before committing a study size, simulate operating characteristics
under plausible company heterogeneity and effect sizes using development data.
If power or margin precision is inadequate, state an estimation study rather
than claiming equivalence. Cluster bootstrap with eight clusters is fragile;
publish per-company results and sensitivity analyses. Provider failures and
stopped runs stay visible and can make a model-quality comparison inconclusive.

Use one frozen frontier comparator and cheap/open-weight arms. Give the
frontier the same observable evidence and tools for the main model comparison;
full-evidence and oracle arms are separate diagnostics. Compare the same small
model with and without the proposed method to isolate the method effect.
Log actual model/provider IDs, input hashes, prompts, tokens, dollars, retries,
latency and tool-acquisition units. API dollars and simulated evidence costs
are different resources.

## Novelty and feasibility gates

AuditFlow already combines structured financial graphs, typed tools,
deterministic checks and budgeted agents. FinancialAuditBench already constructs
consistent synthetic engagements and expert-reviewed workpaper tasks. Evidence
graphs, multi-agent labels, balanced journals and a finite budget alone are
not new contributions.

The hypothesis to investigate is **decision-calibrated evidence acquisition
with expert-reviewed alternative proofs and dated authority
applicability**, tested under controlled ambiguity, refutations and cost.
Its incremental scientific value would be a reproducible evaluation of when
small models know what missing evidence could change a conclusion, and when
they should abstain. A systematic search and close-method ablations must still
establish novelty. The annotation protocol is an experimental contribution
proposal, not an already accepted methodological advance.

Begin with 12–24 development assertions from the chosen revenue/cutoff scope,
including supported issues, supported controls and genuinely insufficient
evidence. This is a workload calibration target, not a powered study size or
representative benchmark. Time sourcing and expert review; include delayed-repeat effort only for the legacy protocol;
inspect disagreement and exclusion causes. Expand only after the rubric and
source quality stabilize. Set the final size and release claims from actual
reviewer capacity, dependency structure and preregistered precision goals.

## Schema, validator and release gate

Canonical files in this repository:

- `review/annotation.schema.json`: portable JSON Schema Draft 2020-12 structural contract.
- `review/annotation_template.json`: empty draft; never counts as completed annotation.
- `review/annotation_example_unreviewed.json`: fictional example showing alternative
  proof structure and unresolved authority; no real reviewer or human gold.
- `scripts/validate_annotations.py`: standard-library structural and semantic validator
  for this schema, including batch group-split checks and optional release gates.

The existing empty template retains legacy defaults for compatibility. When
manually preparing a record for the current pilot, explicitly populate the v2
protocol and non-measurement fields described above. Changing those fields does
not create a review, verify a source, or make an empty draft eligible.

```bash
python scripts/validate_annotations.py review/annotation_template.json
python scripts/validate_annotations.py review/annotation_example_unreviewed.json
python scripts/validate_annotations.py --release annotations/*.json
python scripts/validate_annotations.py --print-gold-hash annotations/case.json
python -m unittest discover -s tests -p test_annotation_validation.py -v
```

Draft validation permits documented unknowns. Release validation requires
source completeness, qualified expert review, documented uncertainty resolution,
frozen gold, applicable authority or a justified abstention state, reviewed
proof alternatives, completed leakage checks and a frozen assigned split.
Failures must be resolved, excluded prospectively, or left in development.
The validator never upgrades a record or supplies a human-review flag.
An eligible record is not sufficient for a benchmark release: dataset-level
sampling, honest reliability disclosure (and legacy intra-rater stability statistics), source rights, secure execution and an
independent tagged-release reproduction remain additional gates.
