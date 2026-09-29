# Expansion plan: more companies, and an IFRS edition

Status: plan plus scaffolding. Nothing below has been built from real filings yet;
this environment had no SEC/FASB/IFRS network access. Configs, rulebook, code paths
and tests are in the repo.

## 1. What the benchmark should claim

**Claim:** given a real financial statement and the evidence an auditor would hold,
can a system decide whether a standard is violated and name the one paragraph that
governs the violation, where arithmetic cannot find the fault and the violation
(not the line item) selects the paragraph?

Design facts that support the claim (v0.4):
- citable faults leave the statement footing (0.0% arithmetic-visible);
- supporting facts appear on clean and faulty statements alike, in one template;
- the same concept gets different paragraphs under different facts (R03 → 210-10-45-12,
  R19 → 470-10-45-11; R11 → 330 on inventory, R01 → 210-10-45-1 on the same line);
- clean controls on the exam; opaque ids; one statement version per form.

Do **not** claim: that the citations are deterministic ground truth (they are policy
decisions awaiting accountant review); that a pipeline's score here generalises
(15 rules, and the same team wrote generator and pipeline); first-ever status (see §5).

**Is it valid?** As a controlled diagnostic of rule knowledge and rule application
under evidence: yes, once an accountant signs off on the 15 paragraphs and the blind
LLM run is repeated on v0.4. As a broad measure of auditing competence: not yet.
Too few rules, cash-flow statements still templated, 8 companies. The
expansion below addresses the last two; only accountant time addresses the first.

## 2. Which companies to add (US GAAP)

`configs/usgaap_expansion.json`: 60 phase-1 companies + 11 phase-2. Chosen to break
the four biases Mohsen found (big tech, mega-cap memorisation, no financials, only
presentation faults), and so that each new rule has real statements where it bites:

| Need | Companies (examples) | Why |
|---|---|---|
| Inventory / NRV / LIFO | Hershey, Dollar General, Caterpillar, Exxon, Chevron, Valero, Sherwin-Williams, Micron, Nucor | LIFO filers test the 330-10-35-1B carve-out (policy disagreement #4); real write-downs (Valero 2020, Micron 2023) |
| Goodwill impairment | AT&T (2020/22/23), Comcast (Sky 2022), Molson Coors, Owens Corning, Polaris, Crocs | real impairments, so the R14 story is not only synthetic |
| Covenants / going-concern pressure | Carnival, Royal Caribbean, Delta, United (2020–22) | real covenant waivers: the R19 contrast has real counterparts |
| DTA valuation allowances | Intel (2024), Tesla (released 2023), Lucid, Peloton, Beyond Meat, Boeing | full and partial allowances, releases |
| Leases | McDonald's, Darden, Starbucks, Shake Shack, Target, Home Depot, FedEx | operating/finance mix; lease-heavy balance sheets |
| Over-time revenue, contract assets/liabilities | Lockheed Martin, General Dynamics, Boeing, Salesforce, Adobe, Oracle, Cisco | 606 timing beyond "premature revenue" |
| Receivables / credit losses | Snap-on, Caterpillar, McKesson, HCA, GM | finance receivables; large trade receivables |
| Negative equity (unusual but legal) | McDonald's, Starbucks, HP, Oracle, HCA, McKesson, AbbVie | stops "negative equity ⇒ error" shortcuts |
| Fiscal-year diversity | Nike/Oracle/Darden/FedEx (May), Cisco (Jul), Micron (Aug), HP (Oct), Adobe/Carnival (Nov), Walmart/Target/Salesforce (Jan), McKesson (Mar) | the period is not a proxy for anything |
| Mid/small caps (less memorised) | Boston Beer, Crocs, Lululemon, Tractor Supply, Shake Shack, Polaris, Owens Corning, Snap-on | memorisation control |
| Phase 2 — unclassified balance sheets | JPMorgan, Bank of America, KeyCorp, Zions; MetLife, Travelers, Progressive; Prologis, Simon; Duke, NextEra | the 17% of v0.1 rules undefined for banks/insurers; needs a new template and rule families (ACL 326 on loans, AFS/HTM 320, insurance 944, regulatory assets 980) |

Budget: at ~10 years × 3 statements × ~17 versions, 60 companies ≈ 30,000 items.
That is more than the evaluation needs. Keep all companies and sample one version per
statement per form, so the clusters (companies) go up 8 → 68 while the exam stays
reviewable. Confidence intervals should be clustered by company.

CIKs were written from memory; the build now skips any company whose EDGAR
`entityName` does not match the configured name.

## 3. IFRS edition — is it possible, and is it novel?

### Possible: yes, with the same architecture

| Piece | US GAAP (built) | IFRS (scaffolded) |
|---|---|---|
| Real values | SEC companyfacts `us-gaap`, 10-K | SEC companyfacts `ifrs-full`, 20-F/40-F (FY2018+); or EU ESEF iXBRL via filings.xbrl.org (FY2020+) |
| Statement structure | filing `_cal.xml` | same; IFRS roles are "StatementOfFinancialPosition", anchors `CurrentAssets` / `EquityAndLiabilities` (implemented) |
| Taxonomy graph | FASB US-GAAP reference linkbase (Topic-Subtopic-Section-Paragraph) | IFRS Accounting Taxonomy reference linkbase (Name/Number/Paragraph → `IAS 36.59`), same XBRL 2.1 structure (`IfrsCitationResolver`, tested on a fixture) |
| Rulebook | `rulebook.json` (20 rules) | `rulebook_ifrs.json` (23 rules, DRAFT, 13 ready to run) |
| Output | `data/benchmark/` | `data/ifrs/benchmark/` (separate; shares only code) |

Run once network is available:
```bash
# point configs/ifrs.json "taxonomy_zip" at a local IFRS Accounting Taxonomy zip first
python3 scripts/build_benchmark.py --config configs/ifrs.json
python3 scripts/split_dataset.py   --config configs/ifrs.json
python3 scripts/check_triviality.py --config configs/ifrs.json
```

Constraints that cannot be engineered away:
- **Years.** SEC IFRS XBRL starts with fiscal periods ending after 15 Dec 2017; ESEF with
  FY2020. Ten years is not available as tagged facts.
- **Currency.** Values stay in the presentation currency (EUR, GBP, JPY…); never convert.
- **Extension concepts.** IFRS filers use more company-specific extensions than US filers;
  expect more residual lines until presentation linkbases are used.
- **Statements.** Balance sheet only for now; the IS/CF builders are us-gaap templates
  (the same IS/CF work the US set still needs).
- **Standards text licensing.** Both the FASB Codification and IFRS Standards are licensed.
  Paragraph *identifiers* are fine; do not redistribute paragraph text in the dataset.

### Novel: the contrastive part is; "IFRS" alone is not enough

Closest prior work, from a search on 2026-09-28 (read these before writing related work):
- **FinRule-Bench** (arXiv 2603.11339): real statements + human-curated accounting
  principles, "grounded in US GAAP and IFRS"; tasks are rule verification, selecting the
  violated principle **from a provided rule set**, and multi-violation diagnosis. That
  overlaps the "which rule is violated" idea. Differences to state: closed-set principle
  choice vs open-set codification paragraph; no taxonomy-linked, XBRL-concept-grounded
  answer key; no evidence-dependent paragraph selection; no framework contrast pairs.
- **FinReporting** (arXiv 2604.05966, ACL 2026 demo): cross-jurisdiction (US, Japan,
  China) reporting workflow with a canonical ontology. Cross-framework, but extraction
  and verification, not violation citation.
- **FinAuditing** (arXiv 2510.08886) says its design "can be extended to other regulatory
  environments such as IFRS". They have not done it; you would be doing what they
  flagged as future work.
- **AuditBench** (2506.17282), **AuditFlow** (2606.03031), **FinTagging** (2505.20650),
  **AuditFraudBench** (2606.08345): US GAAP only; none score a paragraph-level citation
  against an official taxonomy.

What is new if you build it: **the same fact pattern with a different verdict or paragraph
by framework.** `rulebook_ifrs.json` marks 8 such rules (`framework_contrast`):

| Fact in the evidence | US GAAP | IFRS |
|---|---|---|
| dividends paid shown in operating cash flows | violation, 230-10-45-15 | permitted, IAS 7.34 (Correct) |
| covenant breach, waiver for >12 months obtained **after** period-end | non-current OK, 470-10-45-11 | current, IAS 1.74 |
| undiscounted flows > carrying amount, fair value < carrying amount | no loss, 360-10-35-17 | loss if recoverable amount < carrying, IAS 36.59 |
| inventory write-down reversed after NRV recovers | prohibited (330-10-35-14) | required, IAS 2.33 |
| development costs meeting the criteria capitalised | violation, 730-10-25-1 | required, IAS 38.57 |
| lessee operating vs finance relabel | violation, 842-10-25-2 | no such split, IFRS 16.22 |
| LIFO | permitted | violation, IAS 2.25 |
| valuation allowance vs "probable" recognition | 740-10-30-5 | IAS 12.24 |

Keep the two datasets separate as planned, but release a small **paired split** (the same
statement shape and the same facts, one US-GAAP and one IFRS answer). "Does the model apply
the framework it was told to apply?" is a question no benchmark in the list answers, and it
is where LLMs trained mostly on US content should fail in an informative way.

### What the IFRS rules still need
- IFRS-worded fact templates for goodwill (CGU, recoverable amount), PP&E (no undiscounted
  step), DTA (probable taxable profit), debt (waiver timing), R&D (research vs development);
- two ops: `delete_pair` (IFRS 16 lessee leases off balance sheet) and a relabel for the
  IAS 7.34 dividends item;
- verification of the `ifrs-full` concept names and of every paragraph against the
  taxonomy release used; accountant review, as for US GAAP.

## 4. How the papers help

- **AuditBench** — task format and the 26% citation baseline. Its citations were GPT-4
  prose; this benchmark replaces them with paragraph identifiers. The statement-type prior
  in `scripts/make_predictions.py` scores 25.4% at paragraph level, which is roughly where
  AuditBench's GPT-4 number sits; quote that as a sanity check, not a result.
- **FinAuditing / FinMR (TheFinAI)** — the FinMR task is 332 real filings labelled by DQC
  rules. It gives you what this benchmark cannot: **real** (not injected) errors with
  institutional labels. Use it as the out-of-distribution test for your pipeline
  (the capstone's AuditPatch already runs on it). Its FinSM result (retrieval over 18k
  concepts < 13%) is also why the capstone's concept mapper is the bottleneck.
  Note there are two unrelated "FinMR" datasets; the Auckland one (CFA/FRM exam questions)
  is not relevant.
- **AuditFlow** — separate search from verification: LLM finds, symbolic code decides. That
  is the argument for your pipeline, and the reason your pipeline must be evaluated on data
  it was not co-designed with.

## 5. Notes for the capstone pipeline (`pipeline-stage0-1-2-evals`)

- **The taxonomy graph cannot find recognition/measurement paragraphs.** In v0.4 no
  subject-clause rule (R09–R21) is paragraph-verified on a single record: the linkbase
  attaches disclosure and presentation references to the affected concepts, not
  326-20-30-1, 360-10-35-17, 470-10-45-11 and the rest. (5 R20 records use a concept missing
  from the offline cache, so "none" is unconfirmed for those.) Presentation rules verify: R08
  and R16 in 100% of records, R01 in 43%. Concept → linkbase → topic will keep choosing
  210/310/360-10-50. The missing stage is violation → clause (presentation vs
  subject) → paragraph, which `docs/CITATION_POLICY.md` spells out. Implement it from the
  policy text, not from `rulebook.json`, or the result is circular.
- **Hold-out protocol.** Freeze the pipeline, then reveal R17–R21. If the taxonomy graph plus
  policy find those paragraphs unaided, that is the finding.
- `core/taxonomy_graph.py` resolves locators by the `loc_<Concept>` label pattern (regex).
  The IFRS taxonomy does not follow that label convention; port the IFRS work to
  href-fragment resolution (as `src/citation_resolver.py` does) and to IAS/IFRS reference
  parts. `concept_citation.SUBJECT_RULES` needs an IFRS table (IAS 2, IAS 36, IFRS 16,
  IAS 12, IAS 38, IFRS 15, IFRS 9, IAS 16, IAS 7, IAS 1).
- Stage 0 (arithmetic) will, correctly, abstain on every citable v0.4 item. That is now a
  property of the benchmark, not a bug: report Stage 0 on detection-only items and Stage 1/2
  on citable items.

## 6. Naming

arXiv 2608.07688, "IntelliAudit: Using Large Language Models to Evaluate Audit Controls"
(ISO 27001 IT audit), lists Mohammad A. Tayebi as an author. If that is the same group,
agree on names before submission. If not, pick another name for this benchmark.

## 7. Review of the proposed IFRS plan (Sept 2026)

A plan circulated in the team proposed five IFRS error types with citations and a
12-company Canada/Europe list. Keep its structure (same error types as US GAAP, separate
dataset, citation tiers, jurisdiction metadata); fix these before using it:

**Error types.** Keep the same types in both editions so the two datasets are comparable:
AuditBench's four (Missing Row, Numerical Error, Redundant Row, Misclassification) with sign
errors as a Numerical-Error rule (R12/I12). Only the citations differ by framework.

| Proposed mapping | Problem | Use instead |
|---|---|---|
| Misclassification → IAS 1.60 | 1.60 requires presenting a current/non-current split; the criteria are 1.66 (assets) and 1.69 (liabilities) | IAS 1.66 / 1.69 / 1.70 (rulebook_ifrs I01–I03) |
| lease classification → IFRS 16.47 | 16.47 is lessee *presentation*; IFRS 16 has no lessee operating/finance classification | IFRS 16.22 for an unrecognised lease (I10); no lessee classification rule |
| Missing line → IAS 1.112 | 1.112 is about the content of the notes; a complete set of statements is IAS 1.10 | detection-only for an arbitrary missing line; IFRS 16.22 only when the missing line is a lessee's ROU asset/lease liability |
| Fabricated line → IAS 1.29 / IFRS 8.10 | 1.29 is materiality and aggregation; IFRS 8.10 defines an operating segment; neither governs an invented line | detection-only (no governing paragraph), as in US GAAP |
| Sign error → IAS 1.54–55 / IAS 7.18–21 | 1.54 lists line items; 7.18–21 are direct vs indirect method; neither says anything about signs | detection-only |
| "IFRS taxonomy has fewer paragraph links" | unverified; every IFRS Taxonomy element carries references | measure it once the taxonomy is downloaded |

**Companies.** Shopify reports under US GAAP. Couche-Tard and Canadian Tire are not SEC
registrants, and SEDAR+ has no mandatory XBRL, so their statements are PDFs only.
Switzerland is not in the EU, so Novartis is not an ESEF filer; use its SEC 20-F. For
Canada, use 40-F filers (RBC, BCE, Suncor, CNQ). BCE, Suncor and Vodafone were added to
`configs/ifrs.json`; the rejected ones are listed there with reasons.

**Size.** 12 companies × 3 years × ~2 errors ≈ 72 items is too small for per-rule numbers.
Use every available year (SEC IFRS XBRL from FY2018, ESEF from FY2020) and every applicable
rule per statement, as the US set does.

**US list.** The 12-company US proposal is mostly covered: AAPL, MSFT, WMT, JNJ are built;
HD, XOM, BA, CAT were in the expansion config; UNH and V were added. JPM stays phase 2
(unclassified bank balance sheet). R&D is ASC 730, not 720; asset retirement obligations
(ASC 410) would need a new rule.
