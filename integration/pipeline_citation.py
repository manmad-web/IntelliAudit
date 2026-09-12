#!/usr/bin/env python3
"""
========================= PROVENANCE: OLD REPO (vendored) =====================
This file is VENDORED (copied, read-only) from the capstone auditor pipeline:
    dakshkashyap/financial-audit-capstone  @ pipeline-stage0-1-2-evals
    approaches/stage1_taxonomy_citation/concept_citation.py
It is NOT IntelliAudit-Bench original code. It is included here so the
integration eval can run the pipeline's citation-selection logic against the
benchmark without cloning the whole capstone repo. Attribution: capstone team
(daksh / irvin / man-mad). Keep in sync with the source if that repo changes.
==============================================================================

What it does: given a us-gaap concept + statement type, predict the governing
ASC *topic* — a single deterministic pick (best_topic) and a union candidate set
(candidate_topics = subject-matter ∪ presentation ∪ taxonomy arcs). Never reads
ground-truth labels, so using it on the benchmark is not leakage.
"""
from __future__ import annotations
import re
from typing import List, Optional, Set

# statement-location (presentation) topics — where a line is shown
STMT_PRESENTATION = {"cash_flow": "230-10-45", "balance_sheet": "210-10-45", "income_statement": "220-10"}

# subject-matter rules: concept-name substring → governing ASC topic (first match wins)
SUBJECT_RULES: List[tuple] = [
    (r"Goodwill", "350"),
    (r"IntangibleAssets|FiniteLived|IndefiniteLived|AmortizationOfIntangible", "350"),
    (r"Inventory", "330"),
    (r"PropertyPlantAndEquipment|Depreciation|AccumulatedDepreciation", "360"),
    (r"Lease|RightOfUseAsset", "842"),
    (r"Receivable|AllowanceForDoubtful|AllowanceForCreditLoss", "310"),
    (r"DeferredTax|IncomeTax|CurrentFederalTax|CurrentStateTax|TaxExpenseBenefit", "740"),
    (r"ShareBasedComp|StockBasedComp|ShareBasedPayment|AllocatedShareBased", "718"),
    (r"ResearchAndDevelopment", "730"),
    (r"LongTermDebt|ShortTermDebt|NotesPayable|LineOfCredit|DebtInstrument|"
     r"CommercialPaper|SecuredDebt|UnsecuredDebt|ConvertibleDebt", "470"),
    (r"CommonStock|AdditionalPaidInCapital|RetainedEarnings|TreasuryStock|"
     r"PreferredStock|StockholdersEquity|MinorityInterest", "505"),
    (r"AvailableForSale|MarketableSecurities|DebtSecurities|HeldToMaturity|"
     r"TradingSecurities|EquitySecurities", "320"),
    (r"BusinessCombination|BusinessAcquisition|AssetAcquisition", "805"),
    (r"ForeignCurrency|ForeignExchange|TranslationAdjustment", "830"),
    (r"Pension|Postretirement|DefinedBenefit|RetirementBenefit", "715"),
    (r"Revenue|RevenueFromContract|ContractWithCustomer", "606"),
    (r"EarningsPerShare", "260"),
    (r"FairValue", "820"),
    (r"Contingenc|Commitment|LossContingency|Guarantee", "450"),
    (r"AssetRetirementObligation", "410"),
    (r"Restructuring", "420"),
]

_SECTION_STMT = {
    "operating_activities": "cash_flow", "operating_adjustments": "cash_flow",
    "operating_working_capital": "cash_flow", "investing": "cash_flow",
    "financing": "cash_flow", "ending_cash": "cash_flow",
    "current_assets": "balance_sheet", "noncurrent_assets": "balance_sheet",
    "assets_subtotal": "balance_sheet", "current_liabilities": "balance_sheet",
    "noncurrent_liabilities": "balance_sheet", "equity": "balance_sheet",
    "equity_subtotal": "balance_sheet", "revenue": "income_statement",
    "operating_expenses": "income_statement", "operating_expenses_subtotal": "income_statement",
    "nonoperating": "income_statement", "income_tax": "income_statement",
    "net_income": "income_statement", "eps": "income_statement",
}
TOPIC_FAMILY = {"225": "220", "605": "606"}   # superseded → successor


def topic_of(asc: Optional[str]) -> Optional[str]:
    if not asc:
        return None
    m = re.match(r"\s*(\d{3})", asc)
    return m.group(1) if m else None


def family(topic: Optional[str]) -> Optional[str]:
    return TOPIC_FAMILY.get(topic, topic) if topic else None


def _bare(concept: Optional[str]) -> str:
    return (concept or "").replace("us-gaap:", "")


def subject_topic(concept: Optional[str]) -> Optional[str]:
    bare = _bare(concept)
    if not bare:
        return None
    for pat, topic in SUBJECT_RULES:
        if re.search(pat, bare):
            return topic
    return None


def presentation_citation(statement_type: Optional[str], section: Optional[str] = None) -> Optional[str]:
    st = statement_type if statement_type in STMT_PRESENTATION else _SECTION_STMT.get(section or "")
    return STMT_PRESENTATION.get(st or "")


def best_topic(concept, statement_type, section=None, taxonomy_best=None) -> Optional[str]:
    """Single deterministic pick: subject-matter → presentation → taxonomy."""
    return subject_topic(concept) or topic_of(presentation_citation(statement_type, section)) or taxonomy_best


def candidate_topics(concept, statement_type, section=None, taxonomy_topics=None) -> List[str]:
    """Union candidate set: {subject} ∪ {presentation} ∪ {taxonomy arcs}."""
    out: List[str] = []
    seen: Set[str] = set()

    def add(t):
        t = topic_of(t) if t and "-" in t else t
        if t and t not in seen:
            seen.add(t); out.append(t)

    add(subject_topic(concept))
    add(topic_of(presentation_citation(statement_type, section)))
    for t in (taxonomy_topics or []):
        add(t)
    return out
