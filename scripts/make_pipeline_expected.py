#!/usr/bin/env python3
"""docs/intelliaudit_pipeline_expected.svg — Stage 0->1->2 as one flow, with the
numbers to EXPECT (measured vs projected clearly marked) and the result tables needed."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "intelliaudit_pipeline_expected.svg")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
C = dict(ink="#141c2b", sub="#5a6a80", line="#d5dbe6", bg="#f5f7fb", card="#ffffff",
         blue="#1a56db", bluebg="#e8effc", green="#0f9d58", greenbg="#e6f4ea",
         red="#d93025", redbg="#fce8e6", amber="#b06000", amberbg="#fdf1df",
         purple="#6b3fa0", purplebg="#efe8f7", ink2="#2c3a4f")
S = []
def box(x,y,w,h,fill,stroke,rx=10,sw=1.3): S.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
def t(x,y,s,sz=13,f=C["ink"],w="400",a="start",mono=False):
    fam="ui-monospace,Menlo,monospace" if mono else "Inter,Segoe UI,system-ui,sans-serif"
    S.append(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{sz}" font-weight="{w}" fill="{f}" text-anchor="{a}">{s}</text>')
def arr(x1,y1,x2,y2,col=C["sub"],wd=2.4): S.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="{wd}" marker-end="url(#a)"/>')

W,H=1180,1360
S.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
S.append(f'<defs><marker id="a" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="{C["sub"]}"/></marker></defs>')
box(0,0,W,H,C["bg"],C["bg"],0,0)
t(40,48,"IntelliAudit pipeline — Stage 0 → 1 → 2 as one, and what to expect",24,C["ink"],"800")
t(40,72,"Numbers marked ✓ are measured on the benchmark; ▲ are projected (the runs still to do).",13,C["ink2"],"600")

# INPUT
box(40,96,220,60,C["card"],C["line"]); t(58,120,"INPUT",12.5,C["sub"],"800"); t(58,140,"exam record: statement + txs",11,C["ink"])
arr(260,126,300,126)
# STAGE 0
box(300,96,300,110,C["greenbg"],C["green"],12,1.6)
t(318,120,"STAGE 0 · deterministic gate",13,C["green"],"800")
t(318,140,"arithmetic + accounting identities",11,C["ink"])
t(318,158,"✓ 0% false alarms  ·  fires 44%",11,C["green"],"700")
t(318,176,"✓ cite precision 95% on what it fires",11,C["green"],"700")
t(318,194,"(SymPy checks; no LLM)",10,C["sub"])
# branch
arr(600,130,660,130,C["green"]); t(608,122,"FIRE 44%",9.5,C["green"],"700")
arr(450,206,450,250,C["amber"]); t(456,232,"ABSTAIN 56%",9.5,C["amber"],"700")

# FIRE path -> Stage 1 cite -> output
box(660,96,300,110,C["bluebg"],C["blue"],12,1.6)
t(678,120,"STAGE 1 · taxonomy citation",13,C["blue"],"800")
t(678,140,"gold/real concept → US-GAAP linkbase → ASC",10.5,C["ink"])
t(678,158,"✓ exact ASC for detected errors",11,C["blue"],"700")
t(678,176,"deterministic, cannot hallucinate",10.5,C["sub"])
t(678,194,"(fires path → ~95% precise citation)",10.5,C["blue"],"600")
arr(960,150,1010,150,C["blue"]);

# ABSTAIN path -> Stage 2 LLM
box(300,250,300,120,C["amberbg"],C["amber"],12,1.6)
t(318,274,"STAGE 2 · focused LLM",13,C["amber"],"800")
t(318,294,"the hard 56%: misclassification,",10.5,C["ink"])
t(318,310,"redundant, sign, measurement",10.5,C["ink"])
t(318,328,"— the concept×violation cases —",10.5,C["ink2"])
t(318,346,"▲ blind LLM ~26%; + taxonomy",11,C["amber"],"700")
t(318,362,"▲ candidates injected → ~40–50% (TODO)",11,C["amber"],"700")
arr(600,300,660,300,C["amber"])
box(660,250,300,120,C["purplebg"],C["purple"],12,1.6)
t(678,274,"(optional) AuditPatch · repair",13,C["purple"],"800")
t(678,294,"deterministic fix + certificate",10.5,C["ink"])
t(678,312,"✓ 81.5% exact repair (FinMR/DQC)",11,C["purple"],"700")
t(678,330,"replace_fact_value → revalidate",10.5,C["sub"])
arr(960,300,1010,300,C["purple"])

# OUTPUT
box(1010,150,150,200,C["ink"],C["ink"],12,0)
t(1085,180,"OUTPUT",12,"#fff","800",a="middle")
for i,l in enumerate(["judgment","error type","+ row","ASC citation","corrected /","repaired"]):
    t(1085,206+i*22,l,11,"#c9d4e6","600",a="middle")

# ---- WHAT TO EXPECT (combined)
ey=410
t(40,ey-4,"What to expect — combined citation on all 1,089 records",16,C["ink"],"800")
box(40,ey+8,W-80,150,C["card"],C["line"])
t(58,ey+34,"Correct citations = deterministic (461) + Stage-2 LLM’s share of the 606 abstains:",12.5,C["ink"],"600")
rows=[("Deterministic gate alone (✓ measured)","461 / 1089  =  42%  citation recall  @  95% precision",0.42,C["green"]),
      ("+ Stage 2 blind LLM on the 606 (▲ ~26% of them)","≈ 618 / 1089  ≈  57%  (projected)",0.57,C["amber"]),
      ("+ Stage 2 with taxonomy candidates (▲ ~40%)","≈ 703 / 1089  ≈  65%  (projected)",0.65,C["blue"]),
      ("AuditBench reference (blind GPT-4)","26%",0.26,C["red"])]
bx=560; bw=470; yy=ey+62
for lab,val,frac,col in rows:
    t(58,yy+4,lab,10.6,C["ink"],"600")
    box(bx,yy-11,bw,16,"#eef1f7","#eef1f7",8,0); box(bx,yy-11,int(bw*frac),16,col,col,8,0)
    t(bx+bw+8,yy+4,val,10,col,"700"); yy+=30
t(58,ey+150-8,"So expect the FULL pipeline ~55–65% citation vs a blind LLM’s ~26% — the gap is the contribution. The 100% you saw before was fake (label-leaking).",10.4,C["red"],"700")

# ---- RESULTS YOU NEED
ry=590
t(40,ry-4,"The result tables the paper needs",16,C["ink"],"800")
tables=[
 ("Table 1 — Detection", ["General-Judgment EM on exam + CLEAN statements","Precision / Recall / F1  ·  false-alarm rate on the 223 clean","per error-type: which errors Stage 0 catches (arith) vs misses (classif.)"], C["green"]),
 ("Table 2 — CITATION (headline)", ["EM @ topic / subtopic / full-paragraph","rows: blind-LLM baseline · deterministic gate · FULL pipeline","split by tier: linkbase-verified vs expert-authored","citation Precision / Recall / F1  (abstention-aware)"], C["blue"]),
 ("Table 3 — Ablation (why each piece matters)", ["LLM-alone  →  +Stage 0 gate  →  +taxonomy candidates  →  full","key number: clean-split false alarms 50% → ~29% at fixed model","−taxonomy / −gate: show each removal hurts"], C["amber"]),
 ("Table 4 — Repair (optional, AuditPatch)", ["exact-repair rate (81.5%) · regressions (0) · coverage (178/332)","only if you include the repair track / second paper"], C["purple"]),
]
yy=ry+16
for title,items,col in tables:
    box(40,yy,W-80,26+len(items)*20,C["card"],col,10,1.2)
    t(58,yy+20,title,12.5,col,"800")
    for i,it in enumerate(items):
        t(70,yy+40+i*20,"• "+it,11,C["ink"],"500")
    yy+=26+len(items)*20+12

# footer
t(40,H-16,"Honest caveats: report precision against the CLEAN set (not the all-error exam); the deterministic gate inverts injection predicates, so validate on held-out / real errors too.",10,C["sub"])
S.append("</svg>")
open(OUT,"w").write("\n".join(S)); print("wrote",OUT,os.path.getsize(OUT),"bytes")
