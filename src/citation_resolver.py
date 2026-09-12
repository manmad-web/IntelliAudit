#!/usr/bin/env python3
"""
Deterministic citation ground-truth engine.

Resolves a us-gaap concept -> the FASB ASC codification references that the
OFFICIAL US-GAAP reference linkbase attaches to it. This is the correct,
namespace-robust replacement for taxonomy_graph.py's regex/`loc_<Concept>`
approach: we resolve locators by their xlink:href fragment (the real concept id),
not by a guessed label prefix, and we parse with ElementTree using local-names so
we don't care whether the codification parts live in the `ref` or a custom
`codification-part` namespace.

Caches the taxonomy zip locally so it downloads once.

    from citation_resolver import CitationResolver
    cr = CitationResolver()
    cr.citations("AccountsReceivableNetCurrent")   # -> ['ASC 210-10-45-4', ...]
"""
import io, os, re, urllib.request, zipfile
import xml.etree.ElementTree as ET

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
ZIP_URL = "https://xbrl.fasb.org/us-gaap/2023/us-gaap-2023.zip"


def _local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _href_attr(elem):
    for k, v in elem.attrib.items():
        if _local(k) == "href":
            return v
    return None


def _xlink(elem, name):
    for k, v in elem.attrib.items():
        if _local(k) == name:
            return v
    return None


class CitationResolver:
    def __init__(self, zip_url=ZIP_URL):
        self.zip_url = zip_url
        self._index = None  # concept_id -> list of ordered ref-part dicts

    # ---- taxonomy fetch (cached) -------------------------------------------
    def _zip_bytes(self):
        os.makedirs(CACHE, exist_ok=True)
        path = os.path.join(CACHE, "us-gaap-2023.zip")
        if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
            return open(path, "rb").read()
        req = urllib.request.Request(self.zip_url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=60).read()
        open(path, "wb").write(data)
        return data

    # ---- build concept -> references index ---------------------------------
    def _build(self):
        if self._index is not None:
            return
        zb = self._zip_bytes()
        index = {}
        with zipfile.ZipFile(io.BytesIO(zb)) as z:
            ref_files = [n for n in z.namelist() if re.search(r"-ref-\d{4}\.xml$", n)]
            for name in ref_files:
                self._parse_ref_linkbase(z.read(name), index)
        self._index = index

    def _parse_ref_linkbase(self, xml_bytes, index):
        root = ET.fromstring(xml_bytes)
        # iterate every referenceLink
        for link in root.iter():
            if _local(link.tag) != "referenceLink":
                continue
            locs = {}          # label -> concept_id (from href fragment)
            refs = {}          # label -> ordered list of (partname, text)
            arcs = []          # (from_label, to_label)
            for child in link:
                lt = _local(child.tag)
                label = _xlink(child, "label")
                if lt == "loc":
                    href = _href_attr(child) or ""
                    frag = href.split("#", 1)[1] if "#" in href else href
                    concept = frag.split("_", 1)[1] if "_" in frag else frag
                    locs[label] = concept
                elif lt == "reference":
                    parts = [(_local(p.tag), (p.text or "").strip()) for p in child]
                    refs[label] = parts
                elif lt == "referenceArc":
                    arcs.append((_xlink(child, "from"), _xlink(child, "to")))
            for src, dst in arcs:
                concept = locs.get(src)
                parts = refs.get(dst)
                if concept and parts:
                    index.setdefault(concept, []).append(parts)

    # ---- public API ---------------------------------------------------------
    def _asc_from_parts(self, parts):
        d = {k: v for k, v in parts}
        publisher = d.get("Publisher", "")
        name = d.get("Name", "")
        # FASB Accounting Standards Codification references only
        if publisher and publisher != "FASB":
            return None
        if name and "Codification" not in name and "Accounting Standards" not in name:
            return None
        topic, sub = d.get("Topic"), d.get("SubTopic")
        sec, para = d.get("Section"), d.get("Paragraph")
        sub_p = d.get("Subparagraph")
        if not topic:
            return None
        code = topic
        for seg in (sub, sec, para):
            if seg:
                code += f"-{seg}"
        if sub_p:
            code += f"({sub_p})"
        return f"ASC {code}"

    def references(self, concept_id):
        """All raw reference-part dicts attached to a concept."""
        self._build()
        return self._index.get(concept_id, [])

    def citations(self, concept_id):
        """Deduped FASB ASC codes attached to a concept, in linkbase order."""
        out, seen = [], set()
        for parts in self.references(concept_id):
            asc = self._asc_from_parts(parts)
            if asc and asc not in seen:
                seen.add(asc)
                out.append(asc)
        return out


if __name__ == "__main__":
    cr = CitationResolver()
    tests = [
        "AccountsReceivableNetCurrent", "InventoryNet",
        "CashAndCashEquivalentsAtCarryingValue", "Assets",
        "LiabilitiesAndStockholdersEquity",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "OperatingLeaseRightOfUseAsset", "LongTermDebtNoncurrent",
    ]
    print("Building index from official US-GAAP 2023 reference linkbase...\n")
    for c in tests:
        cites = cr.citations(c)
        print(f"us-gaap:{c}")
        print(f"    {cites if cites else '(no FASB ASC reference in linkbase)'}\n")
