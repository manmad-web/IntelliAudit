#!/usr/bin/env python3
"""
Human statement captions for us-gaap concepts.

v0.3 derived every balance-sheet caption from the concept name
("Retained earnings accumulated deficit", "Accounts receivable, net, current",
"Liabilities and stockholders equity"). Two problems:

  * No filer writes captions like that, so the statement reads as generated.
  * The ", current" / ", non-current" suffix travels with a row when it is
    moved. "Accounts payable, current" sitting under non-current liabilities
    is a string-match tell, not an accounting judgement. Real statements rely
    on the section header, so the caption here does too.

Unknown concepts fall back to the old derived label, minus the suffix.
"""
import re

DISPLAY = {
    # current assets
    "CashAndCashEquivalentsAtCarryingValue": "Cash and cash equivalents",
    "CashCashEquivalentsAndShortTermInvestments": "Cash, cash equivalents and short-term investments",
    "ShortTermInvestments": "Short-term investments",
    "MarketableSecuritiesCurrent": "Marketable securities",
    "MarketableSecuritiesNoncurrent": "Marketable securities",
    "AvailableForSaleSecuritiesCurrent": "Available-for-sale securities",
    "AvailableForSaleSecuritiesNoncurrent": "Available-for-sale securities",
    "AvailableForSaleSecuritiesDebtSecuritiesCurrent": "Available-for-sale debt securities",
    "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent": "Available-for-sale debt securities",
    "AccountsReceivableNetCurrent": "Accounts receivable, net",
    "ReceivablesNetCurrent": "Receivables, net",
    "NontradeReceivablesCurrent": "Vendor non-trade receivables",
    "IncomeTaxesReceivable": "Income taxes receivable",
    "InventoryNet": "Inventories",
    "PrepaidExpenseAndOtherAssetsCurrent": "Prepaid expenses and other current assets",
    "OtherAssetsCurrent": "Other current assets",
    "DeferredTaxAssetsNetCurrent": "Deferred tax assets",
    "DeferredTaxAssetsLiabilitiesNetCurrent": "Deferred income taxes, net",
    "AssetsHeldForSaleNotPartOfDisposalGroupCurrentOther": "Assets held for sale",
    "AssetsOfDisposalGroupIncludingDiscontinuedOperationCurrent": "Assets of discontinued operations",
    "AssetsCurrent": "Total current assets",
    # non-current assets
    "PropertyPlantAndEquipmentNet": "Property, plant and equipment, net",
    "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization":
        "Property, plant and equipment, including finance lease assets, net",
    "OperatingLeaseRightOfUseAsset": "Operating lease right-of-use assets",
    "FinanceLeaseRightOfUseAsset": "Finance lease right-of-use assets",
    "CapitalLeasesBalanceSheetAssetsByMajorClassNet": "Capital lease assets, net",
    "Goodwill": "Goodwill",
    "IntangibleAssetsNetExcludingGoodwill": "Intangible assets, net",
    "FiniteLivedIntangibleAssetsNet": "Intangible assets, net",
    "LongTermInvestments": "Long-term investments",
    "OtherLongTermInvestments": "Other investments",
    "EquitySecuritiesWithoutReadilyDeterminableFairValueAmount": "Non-marketable equity securities",
    "DeferredIncomeTaxAssetsNet": "Deferred income taxes",
    "DeferredTaxAssetsNetNoncurrent": "Deferred income taxes",
    "DeferredTaxAssetsGrossNoncurrent": "Deferred income taxes",
    "DeferredTaxAssetsLiabilitiesNetNoncurrent": "Deferred income taxes, net",
    "DisposalGroupIncludingDiscontinuedOperationAssetsNoncurrent": "Non-current assets of discontinued operations",
    "OtherAssetsNoncurrent": "Other non-current assets",
    "AssetsNoncurrent": "Total non-current assets",
    "Assets": "Total assets",
    # current liabilities
    "AccountsPayableCurrent": "Accounts payable",
    "AccountsPayableTradeCurrent": "Accounts payable",
    "AccountsPayableOtherCurrent": "Other payables",
    "AccruedLiabilitiesCurrent": "Accrued liabilities",
    "EmployeeRelatedLiabilitiesCurrent": "Accrued compensation",
    "AccruedIncomeTaxesCurrent": "Income taxes payable",
    "ContractWithCustomerLiabilityCurrent": "Deferred revenue",
    "DeferredRevenueCurrent": "Deferred revenue",
    "DeferredRevenueAndCreditsCurrent": "Deferred revenue and credits",
    "CommercialPaper": "Commercial paper",
    "ShortTermBorrowings": "Short-term borrowings",
    "DebtCurrent": "Short-term debt",
    "LongTermDebtCurrent": "Current portion of long-term debt",
    "ConvertibleDebtCurrent": "Convertible notes, current portion",
    "CapitalLeaseObligationsCurrent": "Capital lease obligations due within one year",
    "OperatingLeaseLiabilityCurrent": "Operating lease liabilities",
    "FinanceLeaseLiabilityCurrent": "Finance lease liabilities",
    "OtherLiabilitiesCurrent": "Other current liabilities",
    "DepositsReceivedForSecuritiesLoanedAtCarryingValue": "Collateral received for securities loaned",
    "LiabilitiesOfDisposalGroupIncludingDiscontinuedOperationCurrent": "Liabilities of discontinued operations",
    "LiabilitiesCurrent": "Total current liabilities",
    # non-current liabilities
    "LongTermDebtNoncurrent": "Long-term debt",
    "LongTermDebt": "Long-term debt",
    "LongTermDebtAndCapitalLeaseObligations": "Long-term debt, including capital leases",
    "ConvertibleDebtNoncurrent": "Convertible notes",
    "CapitalLeaseObligationsNoncurrent": "Long-term capital lease obligations",
    "OperatingLeaseLiabilityNoncurrent": "Operating lease liabilities",
    "FinanceLeaseLiabilityNoncurrent": "Finance lease liabilities",
    "DeferredIncomeTaxLiabilitiesNet": "Deferred income taxes",
    "DeferredTaxLiabilitiesNoncurrent": "Deferred income taxes",
    "DeferredIncomeTaxesAndOtherLiabilitiesNoncurrent": "Deferred income taxes and other",
    "AccruedIncomeTaxesNoncurrent": "Long-term income taxes payable",
    "LiabilityForUncertainTaxPositionsNoncurrent": "Income taxes payable, non-current",
    "ContractWithCustomerLiabilityNoncurrent": "Deferred revenue",
    "DeferredRevenueNoncurrent": "Deferred revenue",
    "PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent": "Employee benefit obligations",
    "LiabilitiesOfDisposalGroupIncludingDiscontinuedOperationNoncurrent": "Non-current liabilities of discontinued operations",
    "OtherLiabilitiesNoncurrent": "Other non-current liabilities",
    "LiabilitiesNoncurrent": "Total non-current liabilities",
    "Liabilities": "Total liabilities",
    # temporary equity
    "RedeemableNoncontrollingInterestEquityCarryingAmount": "Redeemable noncontrolling interest",
    "TemporaryEquityValueExcludingAdditionalPaidInCapital": "Convertible notes, temporary equity",
    # equity
    "PreferredStockValue": "Preferred stock",
    "PreferredStockValueOutstanding": "Preferred stock",
    "ConvertiblePreferredStockNonredeemableOrRedeemableIssuerOptionValue": "Convertible preferred stock",
    "CommonStockValue": "Common stock",
    "CommonStocksIncludingAdditionalPaidInCapital": "Common stock and additional paid-in capital",
    "AdditionalPaidInCapital": "Additional paid-in capital",
    "RetainedEarningsAccumulatedDeficit": "Retained earnings",
    "AccumulatedOtherComprehensiveIncomeLossNetOfTax": "Accumulated other comprehensive income (loss)",
    "TreasuryStockValue": "Treasury stock, at cost",
    "MinorityInterest": "Noncontrolling interests",
    "StockholdersEquity": "Total stockholders' equity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": "Total equity",
    "LiabilitiesAndStockholdersEquity": "Total liabilities and stockholders' equity",
    # ifrs-full subtotals (names that do not collide with us-gaap ones)
    "CurrentAssets": "Total current assets",
    "NoncurrentAssets": "Total non-current assets",
    "CurrentLiabilities": "Total current liabilities",
    "NoncurrentLiabilities": "Total non-current liabilities",
    "Equity": "Total equity",
    "EquityAttributableToOwnersOfParent": "Equity attributable to owners of the parent",
    "EquityAndLiabilities": "Total equity and liabilities",
    "RightofuseAssets": "Right-of-use assets",
    "CurrentTaxAssetsNoncurrent": "Non-current tax assets",
    "CurrentTaxLiabilitiesNoncurrent": "Non-current tax liabilities",
    "CurrentTaxAssetsCurrent": "Current tax assets",
    "CurrentTaxLiabilitiesCurrent": "Current tax liabilities",
    "AdditionalPaidinCapital": "Additional paid-in capital",
    "PropertyPlantAndEquipmentIncludingRightofuseAssets": "Property, plant and equipment (incl. right-of-use assets)",
    "NoncontrollingInterests": "Non-controlling interests",
    "IssuedCapital": "Issued capital",
    "SharePremium": "Share premium",
    "TreasuryShares": "Treasury shares",
    "OtherReserves": "Other reserves",
    "CashAndCashEquivalents": "Cash and cash equivalents",
    "Inventories": "Inventories",
    "NetDeferredTaxAssets": "Deferred tax assets",
    "NetDeferredTaxLiabilities": "Deferred tax liabilities",
    "DeferredTaxAssets": "Deferred tax assets",
    "DeferredTaxLiabilities": "Deferred tax liabilities",
    "LeaseLiabilities": "Lease liabilities",
    "CurrentLeaseLiabilities": "Lease liabilities",
    "NoncurrentLeaseLiabilities": "Lease liabilities",
    "IntangibleAssetsOtherThanGoodwill": "Intangible assets other than goodwill",
    "PropertyPlantAndEquipment": "Property, plant and equipment",
    "TradeAndOtherCurrentReceivables": "Trade and other receivables",
    "TradeAndOtherCurrentPayables": "Trade and other payables",
}

RESIDUAL = {
    "CurrentAssets": "Other current assets, net",
    "NoncurrentAssets": "Other non-current assets, net",
    "Assets": "Other assets, net",
    "CurrentLiabilities": "Other current liabilities, net",
    "NoncurrentLiabilities": "Other non-current liabilities, net",
    "Liabilities": "Other liabilities, net",
    "Equity": "Other equity, net",
    "LiabilitiesAndEquity": "Other liabilities and equity, net",
}

_SUFFIX = re.compile(r",\s*(?:non-current|noncurrent|current)$", re.I)


def derived_label(concept):
    """Fallback: split the concept name, drop the current/non-current suffix."""
    n = (concept or "").split(":")[-1]
    if n.startswith("Current") and n.endswith("Noncurrent"):     # ifrs-full 'CurrentXNoncurrent'
        return "Non-current " + derived_label(n[len("Current"):-len("Noncurrent")]).lower()
    n = n.replace("Rightofuse", "RightOfUse").replace("Paidin", "PaidIn")
    if n.endswith("Noncurrent") and len(n) > len("Noncurrent"):
        # a genuinely non-current line keeps its qualifier (Caterpillar's long-term
        # finance receivables must not read like a misplaced current receivable)
        return derived_label(n[:-len("Noncurrent")]) + ", non-current"
    words = re.findall(r"[A-Z][a-z0-9]*|[A-Z]+(?![a-z])", n)
    s = " ".join(words)
    s = s.replace(" Net Current", ", net").replace(" Net Noncurrent", ", net")
    s = s.replace(" Current", "").replace(" Noncurrent", "").replace(" Net", ", net")
    s = (s[0].upper() + s[1:].lower()) if s else n
    return _SUFFIX.sub("", s)


def display_label(concept):
    bare = (concept or "").split(":")[-1]
    return DISPLAY.get(bare) or derived_label(concept)
