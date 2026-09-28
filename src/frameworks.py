#!/usr/bin/env python3
"""
Accounting-framework registry. US GAAP is the built benchmark; IFRS is the
planned second, separate dataset (docs/EXPANSION_PLAN.md).

Everything that differs by framework lives here, so the generator can stay one
code path while the two datasets stay separate (own config, own rulebook, own
output directory, own citation grammar).
"""

FRAMEWORKS = {
    "us-gaap": {
        "namespace": "us-gaap",
        "forms": ("10-K",),                      # annual reports carrying the XBRL facts
        "currency": "USD",                       # companyfacts unit to read
        "citation": "ASC",                       # 'ASC 210-10-45-1'
        "taxonomy_zip": "https://xbrl.fasb.org/us-gaap/2023/us-gaap-2023.zip",
        "anchors": {                             # section roots in a filing's calculation tree
            "assets": "Assets", "assets_current": "AssetsCurrent",
            "liabilities_current": "LiabilitiesCurrent", "liabilities": "Liabilities",
            "equity": "StockholdersEquity", "equity_nci": "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            "liabilities_and_equity": "LiabilitiesAndStockholdersEquity",
        },
        "rulebook": "rulebook.json",
        "out_dir": "data/benchmark",
        "clean_dir": "data/clean",
    },
    "ifrs": {
        "namespace": "ifrs-full",
        # Foreign private issuers file IFRS XBRL on SEC EDGAR with 20-F (40-F for
        # Canada). Required for periods ending after 15 Dec 2017, so SEC gives
        # roughly FY2018 onward, not ten years. EU ESEF filings (filings.xbrl.org)
        # start with FY2020 annual reports.
        "forms": ("20-F", "40-F"),
        "currency": None,                        # presentation currency varies (EUR, GBP, ...)
        "citation": "IFRS",                      # 'IAS 1.66', 'IFRS 15.31'
        "taxonomy_zip": None,                    # IFRS Accounting Taxonomy zip: set in configs/ifrs.json
        "anchors": {
            "assets": "Assets", "assets_current": "CurrentAssets",
            "liabilities_current": "CurrentLiabilities", "liabilities": "Liabilities",
            "equity": "Equity", "equity_nci": "Equity",
            "liabilities_and_equity": "EquityAndLiabilities",
        },
        "rulebook": "rulebook_ifrs.json",
        "out_dir": "data/ifrs/benchmark",
        "clean_dir": "data/ifrs/clean",
    },
}


def get(name):
    try:
        return FRAMEWORKS[name]
    except KeyError:
        raise ValueError(f"unknown framework {name!r}; expected one of {sorted(FRAMEWORKS)}")


def split_concept(concept, default_ns="us-gaap"):
    """'ifrs-full:Inventories' -> ('ifrs-full', 'Inventories')."""
    if ":" in (concept or ""):
        ns, name = concept.split(":", 1)
        return ns, name
    return default_ns, concept
