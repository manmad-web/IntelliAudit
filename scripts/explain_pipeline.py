#!/usr/bin/env python3
"""
Proof-of-work diagnostic: shows (A) the citation really comes from the official
US-GAAP taxonomy linkbase, with the raw XML traversal, and (B) the arithmetic
identity checks are real computations. Run: python3 scripts/explain_pipeline.py
"""
import hashlib, io, json, os, re, sys, zipfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from citation_resolver import CitationResolver, _local, _xlink, _href_attr
import xml.etree.ElementTree as ET
from statement_builder import build_balance_sheet
from edgar_ingest import get_company_facts
import injector, random

def hr(t): print("\n" + "=" * 74 + f"\n {t}\n" + "=" * 74)

# ============================================================ A. TAXONOMY ====
hr("A.  IS IT REALLY USING THE OFFICIAL US-GAAP TAXONOMY?")
cr = CitationResolver()
zb = cr._zip_bytes()
print(f"Source URL   : {cr.zip_url}")
print(f"Downloaded   : {len(zb):,} bytes   sha256={hashlib.sha256(zb).hexdigest()[:16]}…")
with zipfile.ZipFile(io.BytesIO(zb)) as z:
    ref_files = [n for n in z.namelist() if re.search(r"-ref-\d{4}\.xml$", n)]
    print(f"Ref linkbase : {ref_files}")
    raw = z.read(ref_files[0]).decode("utf-8", "replace")
print(f"Linkbase size: {len(raw):,} chars")
cr._build()
print(f"Concepts indexed from linkbase: {len(cr._index):,}")

CONCEPT = "InventoryNet"
hr(f"A.1  RAW LINKBASE TRAVERSAL for us-gaap:{CONCEPT}  (real XML, via ElementTree)")

def trace(concept, zbytes):
    """Walk every ref linkbase file: concept-loc -> arc -> reference node, printing raw parts."""
    shown = 0
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        for name in [n for n in z.namelist() if re.search(r"-ref-\d{4}\.xml$", n)]:
            root = ET.fromstring(z.read(name))
            for link in (e for e in root.iter() if _local(e.tag) == "referenceLink"):
                locs, refs, arcs = {}, {}, []
                for ch in link:
                    lt, lab = _local(ch.tag), _xlink(ch, "label")
                    if lt == "loc":
                        frag = (_href_attr(ch) or "").split("#")[-1]
                        locs[lab] = frag.split("_", 1)[-1]
                    elif lt == "reference":
                        refs[lab] = [(_local(p.tag), (p.text or "").strip()) for p in ch]
                    elif lt == "referenceArc":
                        arcs.append((_xlink(ch, "from"), _xlink(ch, "to")))
                for src, dst in arcs:
                    if locs.get(src) == concept and dst in refs:
                        loc_href = next(_href_attr(c) for c in link if _local(c.tag) == "loc" and _xlink(c, "label") == src)
                        print(f"  [file] {name}")
                        print(f"  [1] loc      : concept fragment '#...{concept}'  (href={loc_href})")
                        print(f"  [2] arc      : {src}  --referenceArc-->  {dst}")
                        parts = refs[dst]
                        print(f"  [3] reference: " + "  ".join(f"<{k}>{v}</{k}>" for k, v in parts if v))
                        print(f"      -> parsed ASC: {cr._asc_from_parts(parts)}\n")
                        shown += 1
                        if shown >= 3:
                            return
trace(CONCEPT, zb)
print(f"[4] parser output (all FASB ASC refs for this concept): {cr.citations(CONCEPT)}")
print("\n--> The citation is EXTRACTED from the <Topic>/<SubTopic>/<Section>/<Paragraph>")
print("    nodes of the official FASB XML above — not from any model's memory.")

# ============================================================ B. ARITHMETIC ==
hr("B.  ARE THE ARITHMETIC CHECKS REAL COMPUTATIONS?")
facts = get_company_facts("320193")
stmt = build_balance_sheet(facts, 2023)
def val(s, c): return next(r["value"] for r in s["rows"] if r.get("concept") == c)
A  = val(stmt, "us-gaap:Assets")
L  = val(stmt, "us-gaap:Liabilities")
E  = val(stmt, "us-gaap:StockholdersEquity")
LE = val(stmt, "us-gaap:LiabilitiesAndStockholdersEquity")
print(f"CLEAN (real Apple FY2023, $M):")
print(f"   Assets                         = {A:>10,}")
print(f"   Liabilities + Equity           = {L:,} + {E:,} = {L+E:>10,}")
print(f"   Total L&E (reported)           = {LE:>10,}")
print(f"   identity Assets == L+E         -> {A == L + E}   (reconciles? {injector.check_reconciles(stmt)})")

hr("B.1  INJECT a numerical error (R07 breaks the accounting equation) and RE-CHECK")
rule = next(r for r in json.load(open(os.path.join(ROOT, "rulebook.json")))["rules"] if r["rule_id"] == "R07_balance_sheet_identity_break")
mod, meta = injector.inject(stmt, rule, random.Random(1))
A2  = val(mod, "us-gaap:Assets")
E2  = val(mod, "us-gaap:StockholdersEquity")
L2  = val(mod, "us-gaap:Liabilities")
print(f"   perturbed line   : {meta['row_label']} ({meta['row_concept']})")
print(f"   original value   : {meta['original_value']:>10,}")
print(f"   erroneous value  : {meta['erroneous_value']:>10,}   (delta {meta['erroneous_value']-meta['original_value']:+,})")
print(f"   recomputed Equity= {E2:,} ; Assets={A2:,} ; L+E={L2+E2:,}")
print(f"   identity Assets == L+E  -> {A2 == L2 + E2}")
print(f"   reconciles?             -> {injector.check_reconciles(mod)}   (error DETECTED by arithmetic: {not injector.check_reconciles(mod)})")
print("\n--> The recompute walks the subtotal `sums` tree and re-adds children;")
print("    the identity is a real equality test, not a stored label.")
