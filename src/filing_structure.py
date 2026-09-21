#!/usr/bin/env python3
"""
AUDIT FIX #6 (real fix) — build statements from each FILING'S OWN calculation
linkbase instead of a generic template.

Why the earlier attempts failed: the us-gaap `stm/` linkbases are a generic
FASB template, not any filer's structure, so laying a filing out against them
left a large unnamed "(residual)" plug (26%, with a $194bn line on Apple).

Every filing ships its own `*_cal.xml` defining exactly which concepts roll into
each subtotal, in order, with weights. `companyfacts` gives us the accession
number of the 10-K each fact came from, so we can fetch that filing's linkbase
and reproduce the real statement. Apple FY2017 resolves to exactly 6 children of
AssetsCurrent — all of which companyfacts reports — so the residual disappears.
"""
import collections, json, os, urllib.request
import xml.etree.ElementTree as ET

UA = {"User-Agent": "IntelliAudit Research contact@example.edu"}
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "filings")


def _local(t):
    return t.rsplit("}", 1)[-1]


def _xl(e, n):
    for k, v in e.attrib.items():
        if _local(k) == n:
            return v


def _get(url, timeout=40):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def calc_linkbase(cik, accn):
    """Download + cache a filing's calculation linkbase XML."""
    os.makedirs(CACHE, exist_ok=True)
    key = os.path.join(CACHE, f"{accn}_cal.xml")
    if os.path.exists(key):
        return open(key, "rb").read()
    acc = accn.replace("-", "")
    idx = json.loads(_get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/index.json"))
    names = [i["name"] for i in idx["directory"]["item"]]
    cal = next((n for n in names if n.endswith("_cal.xml")), None)
    if not cal:
        raise FileNotFoundError(f"no _cal.xml in {accn}")
    raw = _get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{cal}")
    open(key, "wb").write(raw)
    return raw


def balance_sheet_tree(cik, accn):
    """
    Return (tree, roots) for the filing's balance-sheet role.
      tree : parent concept -> [(child concept, weight)] in presentation order
    """
    root = ET.fromstring(calc_linkbase(cik, accn))
    best, best_tree = None, None
    for link in root.iter():
        if _local(link.tag) != "calculationLink":
            continue
        role = (_xl(link, "role") or "").upper()
        if not ("BALANCESHEET" in role or "FINANCIALPOSITION" in role or "BALANCESHEETS" in role):
            continue
        if "PARENTHETICAL" in role:
            continue
        locs, arcs = {}, []
        for ch in link:
            lt = _local(ch.tag)
            if lt == "loc":
                locs[_xl(ch, "label")] = (_xl(ch, "href") or "").split("#")[-1].split("_", 1)[-1]
            elif lt == "calculationArc":
                arcs.append((_xl(ch, "from"), _xl(ch, "to"),
                             float(_xl(ch, "weight") or 1), float(_xl(ch, "order") or 0)))
        tree = collections.defaultdict(list)
        for fr, to, w, o in sorted(arcs, key=lambda a: a[3]):
            p, c = locs.get(fr), locs.get(to)
            if p and c:
                tree[p].append((c, w))
        # prefer the role that actually contains the asset side
        score = len(tree.get("Assets", [])) + len(tree.get("AssetsCurrent", []))
        if best is None or score > best:
            best, best_tree = score, tree
    return best_tree or {}


# section inference from the filing's own tree
_SECTION_BY_PARENT = {
    "AssetsCurrent": "CurrentAssets",
    "LiabilitiesCurrent": "CurrentLiabilities",
    "StockholdersEquity": "Equity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": "Equity",
    "Liabilities": "NoncurrentLiabilities",
    "Assets": "NoncurrentAssets",
    "LiabilitiesAndStockholdersEquity": "LiabilitiesAndEquity",
}


def flatten(tree):
    """
    Walk the filing's tree and yield ordered (concept, section, kind, parent).
    A concept that is itself a parent becomes a subtotal; leaves become lines.
    """
    out = []

    def walk(node, section):
        for child, _w in tree.get(node, []):
            sect = _SECTION_BY_PARENT.get(child, section)
            if child in tree:                     # it's a subtotal
                walk(child, sect)
                out.append((child, _SECTION_BY_PARENT.get(child, section), "subtotal", node))
            else:
                out.append((child, section, "line", node))

    roots = [r for r in ("LiabilitiesAndStockholdersEquity", "Assets") if r in tree]
    for r in roots:
        walk(r, _SECTION_BY_PARENT.get(r, "Other"))
        out.append((r, _SECTION_BY_PARENT.get(r, "Other"), "total", None))
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from edgar_ingest import get_company_facts, concept_value
    f = get_company_facts("320193")
    cv = concept_value(f, "us-gaap:Assets", 2017)
    t = balance_sheet_tree("320193", cv["accn"])
    print(f"Apple FY2017 balance-sheet tree: {len(t)} parents")
    for c, s, k, p in flatten(t):
        print(f"   {k:<9} {s:<20} {c}")
