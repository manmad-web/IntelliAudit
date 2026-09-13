#!/usr/bin/env python3
"""Generate docs/pipeline_onepager.svg — one-page visual: what we solve, the two
lanes (benchmark factory + auditor pipeline), who built what, results, novelty."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "pipeline_onepager.svg")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

C = dict(ink="#151d2b", sub="#5a6a80", line="#d5dbe6", bg="#f5f7fb", card="#ffffff",
         blue="#1a56db", bluebg="#e8effc", green="#0f9d58", greenbg="#e6f4ea",
         red="#d93025", redbg="#fce8e6", amber="#b06000", amberbg="#fdf1df",
         purple="#6b3fa0", purplebg="#efe8f7", ink2="#2c3a4f")
S = []
def box(x,y,w,h,fill,stroke,rx=10,sw=1.3): S.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
def t(x,y,s,sz=13,f=C["ink"],w="400",a="start",mono=False):
    fam="ui-monospace,Menlo,monospace" if mono else "Inter,Segoe UI,system-ui,sans-serif"
    S.append(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{sz}" font-weight="{w}" fill="{f}" text-anchor="{a}">{s}</text>')
def arr(x1,y1,x2,y2,col=C["sub"],wd=2.2): S.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="{wd}" marker-end="url(#a)"/>')

W,H=1180,1580
S.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
S.append(f'<defs><marker id="a" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="{C["sub"]}"/></marker></defs>')
box(0,0,W,H,C["bg"],C["bg"],0,0)

# ---- header
t(40,50,"IntelliAudit — one page",28,C["ink"],"800")
t(40,76,"Can an AI auditor not just FIND an error in a financial statement, but CITE the exact accounting rule it breaks?",14.5,C["ink2"],"600")

# ---- WHAT WE SOLVE
box(40,96,W-80,86,C["card"],C["line"])
t(58,122,"What we're solving (plain words)",15,C["blue"],"800")
t(58,146,"LLMs can often say “this statement looks wrong,” but they can’t reliably name the rule — the FASB ASC codification section — that governs the violation.",12.8,C["ink"])
t(58,166,"There was no fair way to grade that skill. We build the exam (a benchmark with a trustworthy answer key) AND show a rule-grounded auditor can pass it.",12.8,C["ink"])

# ---- DOMAIN GLOSSARY strip
gy=196
box(40,gy,W-80,64,C["purplebg"],C["purple"])
t(58,gy+22,"Domain terms",12.5,C["purple"],"800")
gloss=[("XBRL","machine-readable filing format"),("US-GAAP taxonomy","the dictionary of accounting concepts"),
       ("reference linkbase","concept → ASC citation map"),("ASC codification","the FASB rulebook (e.g. 606 Revenue)"),
       ("DQC","Data Quality Committee machine rules"),("concept×violation","the citation depends on BOTH")]
gx=58
for k,v in gloss:
    t(gx,gy+42,k,11.5,C["purple"],"700"); t(gx,gy+57,v,10,C["ink2"]); gx+=188

# ---- TWO LANES
ly=280
t(40,ly-4,"The pipeline: two lanes that meet",15,C["ink"],"800")

# Lane A: benchmark factory (YOURS)
box(40,ly+10,540,300,C["card"],C["blue"],12,1.6)
box(40,ly+10,540,30,C["bluebg"],C["bluebg"],12,0)
t(58,ly+31,"LANE A · BENCHMARK FACTORY  — makes the exam",13,C["blue"],"800")
t(58,ly+49,"repo: manmad-web/IntelliAudit  (YOURS)",10.5,C["sub"],"600",mono=True)
stepsA=[("1  Real 10-K facts","SEC EDGAR companyfacts (real $)","edgar_ingest.py"),
        ("2  Canonical statement","BS / IS / CF that reconciles (A=L+E)","statement_builder.py"),
        ("3  Inject 1 error, rule-first","the ASC citation is known BEFORE injection","rulebook.json + injector.py"),
        ("4  Verify citation","cross-check vs official linkbase → tiers","citation_resolver.py"),
        ("5  Records + grader","records.jsonl + hierarchical EM","scorer.py")]
yy=ly+68
for a,b,c in stepsA:
    t(58,yy,a,12,C["ink"],"700"); t(300,yy,b,10.3,C["ink2"]); t(58,yy+15,c,9.5,C["blue"],"600",mono=True); yy+=48

# Lane B: auditor pipeline (OLD/TEAM)
box(600,ly+10,540,300,C["card"],C["green"],12,1.6)
box(600,ly+10,540,30,C["greenbg"],C["greenbg"],12,0)
t(618,ly+31,"LANE B · AUDITOR PIPELINE  — takes the exam",13,C["green"],"800")
t(618,ly+49,"repo: financial-audit-capstone (OLD / team)",10.5,C["sub"],"600",mono=True)
stepsB=[("Stage 0  deterministic gate","math + accounting identities; 0% false alarms","stage0a/0b.py"),
        ("Stage 1  taxonomy citation","concept → ASC from FASB linkbase","taxonomy_graph.py"),
        ("        subject vs presentation","330/470/606 vs 210/220/230 union","concept_citation.py"),
        ("Stage 2  focused LLM","only on abstains; picks a grounded cite","stage2_llm.py"),
        ("AuditPatch  repair track","81.5% exact fix on real DQC filings","finmr_repair.py")]
yy=ly+68
for a,b,c in stepsB:
    t(618,yy,a,12,C["ink"],"700"); t(860,yy,b,10.0,C["ink2"]); t(618,yy+15,c,9.5,C["green"],"600",mono=True); yy+=48

# meeting point
my=ly+320
box(40,my,W-80,66,C["amberbg"],C["amber"])
t(58,my+24,"WHERE THEY MEET  — the combine (NEW glue)",12.5,C["amber"],"800")
t(58,my+44,"integration/adapter.py  turns a benchmark record into the item the auditor expects (and hands over the GOLD concept, skipping the weak mapper).",11.3,C["ink"])
t(58,my+60,"integration/eval_pipeline.py  runs the Stage-1 citation SELECTOR (not the full auditor) as an upper-bound recoverability check — a real end-to-end run is TODO.",10.6,C["ink"])
arr(310,my,310,my-4); arr(870,my,870,my-4)

# ---- RESULTS
ry=my+86
t(40,ry-4,"Recoverability: on our data the right citation IS reachable (upper bound)",15,C["ink"],"800")
box(40,ry+8,W-80,164,C["card"],C["line"])
t(58,ry+34,"Citation topic — selector check (NOT the auditor’s accuracy):",12.5,C["ink"],"600")
bars=[("AuditBench: correct cite even IN the candidate set (oracle)","26.2%",0.262,C["red"]),
      ("IntelliAudit-Bench: concept-only heuristic pick","50.9%",0.509,C["amber"]),
      ("IntelliAudit-Bench: answer recoverable from taxonomy  [UPPER BOUND, by construction]","100%",1.0,C["green"])]
bx=560; bw=470; yy=ry+62
for lab,val,frac,col in bars:
    t(58,yy+4,lab,10.3,C["ink"],"600")
    box(bx,yy-11,bw,17,"#eef1f7","#eef1f7",8,0); box(bx,yy-11,int(bw*frac),17,col,col,8,0)
    t(bx+bw+10,yy+4,val,12,col,"800"); yy+=34
t(58,ry+164-24,"The 100% is TRUE BY CONSTRUCTION (rule-first injection makes the citation recoverable) — an upper bound, not a finding.",10.3,C["red"],"700")
t(58,ry+164-8,"The auditor’s REAL accuracy is a separate experiment: a blind-LLM baseline (expect ~26%) + running the actual staged pipeline.",10.3,C["ink2"],"600")

# ---- WHO BUILT WHAT
wy=ry+176
box(40,wy,560,150,C["card"],C["line"])
t(58,wy+26,"Who built what",13.5,C["ink"],"800")
prov=[("YOURS (new repo)","the benchmark: real data, injection, citation GT, scorer",C["blue"]),
      ("OLD (team capstone)","the auditor: Stage 0–2, taxonomy graph, AuditPatch",C["green"]),
      ("NEW glue","adapter + eval runner that make them one system",C["amber"])]
yy=wy+50
for a,b,col in prov:
    t(58,yy,a,11.5,col,"800"); t(230,yy,b,10.3,C["ink2"]); yy+=30

# ---- NOVELTY
box(620,wy,520,150,C["ink"],C["ink"],12,0)
t(638,wy+26,"Why it’s novel",13.5,"#ffffff","800")
nov=["First benchmark to score the GOVERNING ASC citation —",
     "on REAL filings, with a DETERMINISTIC, cross-checkable answer key.",
     "AuditBench: broken GPT citation labels.  FinAuditing/FinMR: no",
     "citation output.  AuditFlow: numeric verdict only.",
     "+ finding: citation = f(concept × violation); taxonomy alone",
     "under-determines it — which is why LLMs (and naive lookup) miss."]
yy=wy+50
for i,l in enumerate(nov):
    t(638,yy,l,10.6,"#7ee2a8" if i in (0,) else "#c9d4e6","700" if i==0 else "400"); yy+=17

# footer
t(40,H-16,"Provenance: values = SEC EDGAR (real) · citations = US-GAAP 2023 linkbase · transactions = synthetic · 1,089 records, 8 firms × 10 yrs × BS/IS/CF",10,C["sub"])
S.append("</svg>")
open(OUT,"w").write("\n".join(S)); print("wrote",OUT,os.path.getsize(OUT),"bytes")
