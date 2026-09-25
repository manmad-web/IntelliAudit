# Citation policy — which paragraph governs

This is the rule the answer key follows. It is a choice. An accountant can reject it; the disagreements worth having are listed at the end. A string typed into `rulebook.json` is not ground truth until this rule selects it.

## The rule

Name the **one paragraph whose operative sentence the injected fault violates**.

A paragraph is Topic–SubTopic–Section–Paragraph (`210-10-45-1`). A topic (`210`), a subtopic (`210-10`), or a section (`210-10-45`) is not a citation. A subparagraph may be named in the rationale; the scored code stops at the paragraph. Sharing a topic or a subtopic with the concept’s linkbase references does **not** verify a citation. Verification is paragraph-level only (`src/citation_resolver.py`).

Three outcomes:

1. **Presentation wins** — the fault is which section of the statement the line is in, and no subject-topic sentence in the closed list below is the sentence that failed.
2. **Subject wins** — the fault is recognition, measurement, or a classification that a subject topic defines in its own words.
3. **Neither** — arithmetic, existence, omission, sign, or a broken identity. No paragraph governs. The case stays detection-only (`citable: false`) and is left out of citation scoring.

`210-10-45-1` is the current-asset list. It is not a stand-in for “something on a balance sheet is wrong.”

## When presentation wins (210 / 220 / 230)

Presentation topics say **where a line is shown**. They win when the injected fact is a section move and the subject topic is silent on that section.

| Statement | Presentation paragraph | It wins against |
|---|---|---|
| Classified balance sheet, current asset placed in noncurrent | **210-10-45-1** (the current-asset list: cash, receivables, inventory, prepaid expenses) | 330 inventory, 310 receivables. Those topics measure the asset. They do not assign it to a section. |
| Classified balance sheet, operating-cycle liability placed in noncurrent | **210-10-45-8** (payables for materials and supplies, collections in advance of delivery, accruals that arise from operations) | 405, 606. Deferred revenue’s *recognition* is 606; its *current vs noncurrent caption* is 210-10-45-8(b). |
| Classified balance sheet, long-term debt presented entirely as current, with no due-on-demand, callable, or refinancing fact in the record | **210-10-45-12** (current liabilities are not long-term obligations incurred to provide working capital for long periods) | 470. See the debt exception below. |
| Statement of cash flows, a PPE acquisition payment shown in operating rather than investing | **230-10-45-13** (subparagraph (c): payments to acquire property, plant, and equipment are investing outflows) | 360. Topic 360 measures PPE. It does not classify the cash flow. |
| Income statement, an amount in the wrong **caption** (operating vs nonoperating display) and not a recognition or measurement miss | **220-10-45** | 606, 330, and the other subject topics. No current rule injects a pure caption error, so 220 is not asserted. |

## When subject wins (330 / 350 / 606 / 842, and the short debt list)

Subject topics say **what the amount is and when it exists**. They win even though the line also has a presentation reference. The pipeline’s 2.6% came from always preferring the subject topic; that preference is right only for the rows in this list.

| Fault actually injected | Subject paragraph | Why presentation loses |
|---|---|---|
| Revenue recorded before the customer obtains control | **606-10-25-23** (recognize revenue when the performance obligation is satisfied by transferring control) | 220 says where to display revenue. It does not say when control transfers. **606-10-25-1 is the wrong paragraph**: it is the contract-existence test, and the injection is a timing miss, not a missing contract. |
| Inventory carried above net realizable value | **330-10-35-1B** (inventory other than LIFO or the retail method at the lower of cost and NRV) | 210-10-45-1 only lists inventory as a current asset. |
| Goodwill carried without the required impairment | **350-20-35-1** (goodwill is not amortized; it is tested for impairment) | 210 does not measure goodwill. 350-10 (other intangibles) is a different subtopic. |
| Available-for-sale **debt** securities not at fair value | **320-10-35-1** | 210-10-45-1(f) only says marketable securities *of cash available for current operations* are current assets. |
| Operating lease labelled finance, or the reverse | **842-10-25-2** (lessee classification criteria) | 210 classifies current vs noncurrent. It does not decide finance vs operating. This is a classification fault whose sentence lives in the subject topic, so subject wins. |

### The only presentation→subject handoff on the balance sheet

ASC **210-10-45-7** does not itself classify debt. It points at Section 470-10-45 for exactly three transactions: due-on-demand loans, callable debt, and short-term obligations expected to be refinanced. **470-10-45-14** (intent and ability to refinance) wins over 210 **only when the record contains that fact**.

This dataset does not. R03 moves `LongTermDebtNoncurrent` into current liabilities and supplies no refinancing, demand, or callable fact (those facts belong to the evidence work, not this policy). Until one of the three facts is in the record, 470 does not win, and the citation is 210-10-45-12.

## When neither wins

These stay detection-only. Do not put 210-10-45-1 back on them.

| Rule | Fault | Why there is no paragraph |
|---|---|---|
| R04 | A line is missing | Completeness. No paragraph says “this arbitrary line must appear.” |
| R05 | A line’s number is wrong | Arithmetic. Not a recognition or measurement standard. |
| R06 | A fabricated line | Existence. |
| R07 | Assets ≠ liabilities + equity | The identity is definitional. No ASC paragraph states it. |
| R12 | A non-negative element is negative | A data-quality condition, not a Codification paragraph. |

## What may be asserted

- **`linkbase-verified`** — the official US-GAAP reference linkbase attaches **this paragraph** (subparagraphs ignored, section-or-higher ignored) to the affected concept. `CitationResolver.paragraph_verified` is the only check that may set this. A subtopic hit is not enough.
- **`expert-authored-UNVALIDATED`** — this policy names the paragraph, and the linkbase does not attach it to the line. Recognition and measurement paragraphs are usually in this tier, because the linkbase tags disclosure and presentation references on the concept, not the recognition sentence. The tier means “an accountant still has to accept or reject this,” not “checked.”
- Anything else is dropped (`asc: null`, `citable: false`).

DQC rule ids are not ground truth. They are not emitted, and the rulebook does not carry id strings.

## How the key is applied

`rulebook.json` states, for each citable rule, the paragraph this policy selects, `citation_tier: expert-authored-UNVALIDATED`, and the clause (`presentation` or `subject`). At the next rebuild — not on this branch — `citation_resolver.paragraph_verified` may upgrade a record to `linkbase-verified` only on a paragraph match. It may not invent a different paragraph, and it may not verify a section-only code.

## Guessability gate, and what it cannot see

`scripts/check_triviality.py` scores citation guessability as the majority `asc_full` inside each `(error type × statement type)` bucket, on citable rows only, and **fails above 60%**. That limit stays. The script is not changed here.

The limit does not detect a citation that is constant for a rule but identical for every account on that statement. A new rule that maps “everything on the income statement” to one paragraph fails the spirit of the gate even if the percentage still passes. Any rule added after this policy must **vary by account** (inventory → 330, goodwill → 350, leases → 842), not by statement type alone. This branch does not regenerate `exam.jsonl` or `records.jsonl`, so the gate still measures the previous build.

## Where an accountant should disagree

These are decided, not hedged. Push back here:

1. **Debt.** Many reviewers will say every current/noncurrent debt question is ASC 470-10-45, because 210-10-45-7 points at that section. This policy refuses that unless the record has one of the three facts 45-7 names. R03 is therefore 210-10-45-12, not 470.
2. **R02’s paragraph.** 210-10-45-5 only requires a *total* of current liabilities. The policy uses 45-8. A reviewer who thinks the definition in the Glossary, or 45-9’s twelve-month test, is the governing sentence should say so.
3. **Revenue timing.** 606-10-25-30 (when control indicators are met) is a defensible alternative to 606-10-25-23. 606-10-25-1 is not.
4. **Inventory method.** 330-10-35-1B excludes LIFO and the retail method (those stay on 330-10-35-1C / market). The filings do not disclose the method, so 1B over-claims if the filer is on LIFO.
5. **Goodwill.** The loss *amount* after ASU 2017-04 is developed in later paragraphs of 350-20-35. 350-20-35-1 is the “test, do not amortize” sentence. A reviewer can call that one step too high.
6. **Marketable securities vs AFS debt.** 320-10-35-1 is the AFS debt subsequent-measurement sentence. Equity securities are ASC 321. R15’s eligible set still contains unlabeled `MarketableSecurities*` concepts, which is why the rule is `expert-authored-UNVALIDATED` and not verified.
7. **Lease paragraph.** 842-10-25-2 is the criteria list. A reviewer may prefer 842-10-25-1 (the requirement to classify) as the sentence that failed.
