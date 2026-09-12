#!/usr/bin/env python3
"""Generate docs/dataset_anatomy.svg — a one-company figure of the dataset + metrics."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "dataset_anatomy.svg")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# Illustrative REAL record: Apple FY2023, Inventory misclassified current->non-current.
CLEAN = [("Cash and cash equivalents", "29,965"), ("Accounts receivable, net", "29,508"),
         ("Inventories", "6,331"), ("Other current assets", "14,695"),
         ("Total current assets", "143,566"), ("Property, plant & equip., net", "43,715")]
MOD = [("Cash and cash equivalents", "29,965", 0), ("Accounts receivable, net", "29,508", 0),
       ("Other current assets", "14,695", 0), ("Total current assets", "143,566", 0),
       ("Property, plant & equip., net", "43,715", 0), ("Inventories  ← moved here", "6,331", 1)]

C = dict(ink="#1a2233", sub="#5b6b82", line="#d3dae6", card="#ffffff", bg="#f4f6fb",
         green="#0f9d58", greenbg="#e6f4ea", red="#d93025", redbg="#fce8e6",
         blue="#1a56db", bluebg="#e8effc", amber="#b06000", amberbg="#fdf1df", ink2="#33445c")
S = []
def box(x,y,w,h,fill,stroke,rx=10,sw=1.4): S.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
def txt(x,y,t,size=14,fill=C["ink"],w="400",anchor="start",mono=False,ls=""):
    fam="ui-monospace,Menlo,monospace" if mono else "Inter,Segoe UI,system-ui,sans-serif"
    S.append(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" font-weight="{w}" fill="{fill}" text-anchor="{anchor}"{(" letter-spacing=%r"%ls) if ls else ""}>{t}</text>')
def arrow(x1,y1,x2,y2,col=C["sub"]): S.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="2.2" marker-end="url(#ah)"/>')

W,H=1120,1460
S.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
S.append(f'<defs><marker id="ah" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="{C["sub"]}"/></marker></defs>')
box(0,0,W,H,C["bg"],C["bg"],0,0)

# ---- header
txt(40,52,"IntelliAudit-Bench", 30, C["ink"], "800")
txt(40,78,"Standards-Citation Benchmark for LLM Financial Auditing — dataset anatomy (Apple Inc., FY2023)", 15, C["sub"])
txt(40,104,'Thesis: LLMs can’t cite the governing ASC standard for a violation — even though it’s deterministic in the US-GAAP taxonomy. We measure that gap.', 13.5, C["ink2"], "600")

# ---- pipeline strip
py=128; ph=64; xs=[40,300,560,820]; labs=[
 ("1  Real 10-K (SEC XBRL)","companyfacts → real values",C["bluebg"],C["blue"]),
 ("2  Clean statement","reconciles: A = L + E",C["greenbg"],C["green"]),
 ("3  Inject 1 rule-driven error","rulebook.json recipe",C["redbg"],C["red"]),
 ("4  Ground-truth citation","cross-checked vs linkbase",C["amberbg"],C["amber"])]
for i,(t,s,bg,st) in enumerate(labs):
    box(xs[i],py,240,ph,bg,st); txt(xs[i]+16,py+27,t,14.5,C["ink"],"700"); txt(xs[i]+16,py+48,s,12.5,C["sub"])
    if i<3: arrow(xs[i]+244,py+ph/2,xs[i+1]-4,py+ph/2)

# ---- record anatomy: clean vs modified
ry=224; rh=250; colw=520
txt(40,ry-6,"A record = one clean statement + one injected error", 16, C["ink"], "700")
# clean
box(40,ry,colw,rh,C["card"],C["line"]); box(40,ry,colw,30,C["greenbg"],C["greenbg"],10,0)
txt(58,ry+20,"gt_table_text  (clean, real)  ✓ reconciles",13.5,C["green"],"700")
for i,(lab,val) in enumerate(CLEAN):
    yy=ry+54+i*30; w="700" if "Total" in lab else "400"
    txt(58,yy,f"[row {i}] {lab}",12.5,C["ink"],w,mono=True); txt(540,yy,val,12.5,C["ink"],w,anchor="end",mono=True)
# modified
mx=580
box(mx,ry,colw,rh,C["card"],C["line"]); box(mx,ry,colw,30,C["redbg"],C["redbg"],10,0)
txt(mx+18,ry+20,"modified_statement_text  (error injected)",13.5,C["red"],"700")
for i,(lab,val,hl) in enumerate(MOD):
    yy=ry+54+i*30; w="700" if ("Total" in lab or hl) else "400"; col=C["red"] if hl else C["ink"]
    if hl: box(mx+10,yy-15,colw-20,24,C["redbg"],C["redbg"],6,0)
    txt(mx+18,yy,f"[row {i}] {lab}",12.5,col,w,mono=True); txt(mx+colw-20,yy,val,12.5,col,w,anchor="end",mono=True)

# ---- ground-truth citation card
gy=500; gh=232
txt(40,gy-6,"ground_truth_citations  (what you cross-check against)",16,C["ink"],"700")
box(40,gy,colw,gh,C["card"],C["line"])
rows=[("error_type","Misclassification (current → non-current)"),
      ("affected concept","us-gaap:InventoryNet"),
      ("ASC citation (GT)","ASC 210-10-45-1"),
      ("scored at","topic 210 / subtopic 210-10 / full 210-10-45-1"),
      ("citation_tier","linkbase-verified  ✓"),
      ("linkbase set","[852-10-55-10, 210-10-45-1(b), 210-10-S99-1]"),
      ("dqc_rule","DQC_0015  (verify vs XBRL-US)")]
for i,(k,v) in enumerate(rows):
    yy=gy+34+i*28; txt(58,yy,k,12.5,C["sub"],"600",mono=True); txt(250,yy,v,12.5,C["ink"],"600",mono=True)
# tier explainer
box(580,gy,colw,gh,C["card"],C["line"]); box(580,gy,colw,30,C["amberbg"],C["amberbg"],10,0)
txt(598,gy+20,"Two-tier ground truth (self-documenting)",13.5,C["amber"],"700")
exp=[("linkbase-verified","Rule’s ASC IS in the concept’s real",C["green"]),
     ("","linkbase set → deterministic, trust blindly.",C["ink"]),
     ("expert-authored","Governing standard the linkbase does NOT",C["amber"]),
     ("","tag on the line (e.g. AR→310 not 210,",C["ink"]),
     ("","revenue→606-50 disclosure not 606-25).",C["ink"]),
     ("","→ the HARD cases; human-QC these.",C["ink2"])]
for i,(a,b,cc) in enumerate(exp):
    yy=gy+58+i*26
    if a: txt(598,yy,a,12.5,cc,"700",mono=True)
    txt(598 if not a else 726,yy,b,12,cc if not a else C["ink"],"600" if not a else "400")

# ---- metrics
myy=760; txt(40,myy-6,"Metrics — what you report",16,C["ink"],"700")
# citation metrics card
box(40,myy,colw,196,C["card"],C["line"]); box(40,myy,colw,30,C["bluebg"],C["bluebg"],10,0)
txt(58,myy+20,"Citation accuracy  (the headline)",13.5,C["blue"],"700")
cm=[("EM@topic","did it name ASC 210?"),("EM@subtopic","ASC 210-10?  ← headline"),
    ("EM@full","ASC 210-10-45-1?"),("credit","also OK if in concept’s valid linkbase set")]
for i,(k,v) in enumerate(cm):
    yy=myy+56+i*30; txt(58,yy,k,12.5,C["ink"],"700",mono=True); txt(220,yy,v,12.5,C["sub"],"400")
# detection metrics card
box(580,myy,colw,196,C["card"],C["line"]); box(580,myy,colw,30,C["bluebg"],C["bluebg"],10,0)
txt(598,myy+20,"Detection accuracy  (AuditBench-compatible)",13.5,C["blue"],"700")
dm=[("General Judgment","correct / incorrect  (EM)"),("Error Type","4 types  (EM)"),
    ("Error Entry","row index  (EM)"),("self-check","injected error breaks reconciliation")]
for i,(k,v) in enumerate(dm):
    yy=myy+56+i*30; txt(598,yy,k,12.5,C["ink"],"700",mono=True); txt(770,yy,v,12.5,C["sub"],"400")

# ---- experiment bars
ey=990; txt(40,ey-6,"The experiment (what proves the point)",16,C["ink"],"700")
box(40,ey,W-80,150,C["card"],C["line"])
txt(58,ey+30,"Citation EM  —  same benchmark, two systems:",13.5,C["ink"],"600")
bars=[("Baseline LLM (GPT-4, AuditBench)","26%",0.26,C["red"]),
      ("Baseline LLM (Claude Opus, direct)","~30% (expected)",0.30,C["amber"]),
      ("Our taxonomy-grounded pipeline","~95% (deterministic)",0.95,C["green"])]
bx=430; bw=520
for i,(lab,val,frac,col) in enumerate(bars):
    yy=ey+58+i*30; txt(58,yy+4,lab,12.5,C["ink"],"600")
    box(bx,yy-11,bw,18,"#eef1f7","#eef1f7",9,0); box(bx,yy-11,int(bw*frac),18,col,col,9,0)
    txt(bx+bw+10,yy+4,val,12.5,col,"700")

# ---- dataset scale + provenance
dy=1166; box(40,dy,W-80,120,C["card"],C["line"])
txt(58,dy+30,"Current build",14.5,C["ink"],"800")
scale=[("1,089","records"),("223","real statements (BS/IS/CF)"),("8×10","companies × years"),
       ("675 / 271","linkbase-verified / expert"),("11","rules active")]
sx=58
for n,l in scale:
    txt(sx,dy+62,n,20,C["blue"],"800",mono=True); txt(sx,dy+84,l,11.5,C["sub"]); sx+=210
txt(58,dy+108,"Provenance:  values = SEC EDGAR companyfacts (real BS+IS+CF)   ·   citations = official US-GAAP 2023 linkbase (sha256 b48fbb7b…, 17,800 concepts)   ·   transactions = synthetic (sum to real lines)",11,C["ink2"],"500")

# ---- footer novelty
fy=1316; box(40,fy,W-80,110,C["ink"],C["ink"],12,0)
txt(58,fy+32,"Why it’s novel",15,"#ffffff","800")
nov=["AuditBench: has a citation task but broken GT (GPT-4 prose, 26%, unreleased retriever) — not XBRL, not deterministic.",
     "FinAuditing: real XBRL + DQC, but tasks are concept-ID / relation-type / value-recompute — NO citation output.",
     "AuditFlow: deterministic taxonomy+XBRL verification, but outputs a numeric verdict — citation is never scored.",
     "→  First benchmark to score GOVERNING-ASC citation on real filings with deterministic, cross-checkable ground truth."]
for i,l in enumerate(nov):
    yy=fy+56+i*17; col="#7ee2a8" if i==3 else "#c9d4e6"; wt="700" if i==3 else "400"
    txt(58,yy,l,11.8,col,wt)

S.append("</svg>")
open(OUT,"w").write("\n".join(S))
print("wrote", OUT, os.path.getsize(OUT), "bytes")
