#!/usr/bin/env python3
"""
AUDIT FIX #6 — use the US-GAAP taxonomy's OWN classified balance-sheet
presentation linkbase instead of a hand-written concept template.

v0.1 laid statements out from a ~30-concept template, so every balance the
template didn't name fell into an unnamed "(residual)" plug — 26% of balance
sheet magnitude, with a $194bn plug line on Apple FY2017. That plug also had no
transactions, which is precisely the signature of our injected "Redundant Row",
so Stage 0B could not tell them apart.

`us-gaap-2023/stm/us-gaap-stm-sfp-cls-pre-2023.xml` is the authoritative
classified Statement of Financial Position: 686 concepts in the order FASB
publishes them, grouped under abstract headers. Laying a filing out against that
means every concept the company actually reported gets its real name and its
real position, and the residual collapses to whatever genuinely remains.
"""
import os, xml.etree.ElementTree as ET, zipfile

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "us-gaap-2023.zip")
PRE_BS = "us-gaap-2023/stm/us-gaap-stm-sfp-cls-pre-2023.xml"

# nearest abstract ancestor -> our section bucket
_SECTION_OF_ABSTRACT = [
    ("AssetsCurrentAbstract", "CurrentAssets"),
    ("AssetsNoncurrentAbstract", "NoncurrentAssets"),
    ("LiabilitiesCurrentAbstract", "CurrentLiabilities"),
    ("LiabilitiesNoncurrentAbstract", "NoncurrentLiabilities"),
    ("StockholdersEquityAbstract", "Equity"),
    ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterestAbstract", "Equity"),
]


def _local(t):
    return t.rsplit("}", 1)[-1]


def _xl(e, n):
    for k, v in e.attrib.items():
        if _local(k) == n:
            return v


def ordered_balance_sheet_concepts(zip_path=CACHE):
    """
    Return [(concept, section)] in FASB's published order for a classified
    balance sheet. Abstract (header) concepts are dropped; only reportable
    line concepts are returned.
    """
    with zipfile.ZipFile(zip_path) as z:
        root = ET.fromstring(z.read(PRE_BS))

    out, seen = [], set()
    for link in root.iter():
        if _local(link.tag) != "presentationLink":
            continue
        locs, arcs = {}, []
        for ch in link:
            lt = _local(ch.tag)
            if lt == "loc":
                frag = (_xl(ch, "href") or "").split("#")[-1]
                locs[_xl(ch, "label")] = frag.split("_", 1)[-1]
            elif lt == "presentationArc":
                arcs.append((_xl(ch, "from"), _xl(ch, "to"),
                             float(_xl(ch, "order") or 0)))

        parent = {t: f for f, t, _ in arcs}

        def section_for(label):
            """walk up to the nearest abstract we recognise"""
            seen_up, cur = set(), label
            while cur and cur not in seen_up:
                seen_up.add(cur)
                name = locs.get(cur, "")
                for abs_name, sect in _SECTION_OF_ABSTRACT:
                    if name == abs_name:
                        return sect
                cur = parent.get(cur)
            return None

        for f, t, order in sorted(arcs, key=lambda a: a[2]):
            concept = locs.get(t)
            if not concept or concept.endswith("Abstract") or concept in seen:
                continue
            sect = section_for(t)
            if sect:
                seen.add(concept)
                out.append((f"us-gaap:{concept}", sect))
    return out


if __name__ == "__main__":
    cs = ordered_balance_sheet_concepts()
    print(f"{len(cs)} reportable concepts from the classified SFP presentation linkbase")
    from collections import Counter
    for s, n in Counter(s for _, s in cs).most_common():
        print(f"   {s:<24} {n}")
    print("\nfirst 10 in published order:")
    for c, s in cs[:10]:
        print(f"   {s:<20} {c}")


# ── calculation tree: the concepts that actually roll INTO each subtotal ──────
CAL_BS = ["us-gaap-2023/stm/us-gaap-stm-sfp-cls-cal-2023.xml",
          "us-gaap-2023/stm/us-gaap-stm-sfp-cls1-cal-2023.xml",
          "us-gaap-2023/stm/us-gaap-stm-sfp-cls2-cal-2023.xml"]


def calculation_tree(zip_path=CACHE):
    """parent concept -> [(child concept, weight)] for the classified SFP."""
    import collections
    tree = collections.defaultdict(list)
    with zipfile.ZipFile(zip_path) as z:
        for f in CAL_BS:
            if f not in z.namelist():
                continue
            root = ET.fromstring(z.read(f))
            for link in root.iter():
                if _local(link.tag) != "calculationLink":
                    continue
                locs, arcs = {}, []
                for ch in link:
                    lt = _local(ch.tag)
                    if lt == "loc":
                        locs[_xl(ch, "label")] = (_xl(ch, "href") or "").split("#")[-1].split("_", 1)[-1]
                    elif lt == "calculationArc":
                        arcs.append((_xl(ch, "from"), _xl(ch, "to"), float(_xl(ch, "weight") or 1)))
                for fr, to, w in arcs:
                    p, c = locs.get(fr), locs.get(to)
                    if p and c and (c, w) not in tree[p]:
                        tree[p].append((c, w))
    return tree


def resolve_reported_leaves(subtotal, is_reported, tree, max_depth=6):
    """
    Walk DOWN the calculation tree from `subtotal` and return the concepts the
    filer actually reports, at whatever depth they report them — so we never
    double-count a parent and its children, and never emit aggregates the filer
    didn't use. This is what collapses the residual plug.
    """
    out, seen = [], set()

    def walk(c, w, depth):
        if depth > max_depth or c in seen:
            return
        seen.add(c)
        if is_reported(c):
            out.append((c, w))
            return
        for ch, cw in tree.get(c, []):
            walk(ch, w * cw, depth + 1)

    for ch, cw in tree.get(subtotal, []):
        walk(ch, cw, 1)
    return out
