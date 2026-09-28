#!/usr/bin/env python3
"""
Download the SEC files a build needs into data/raw_snapshot/, so the build can
run where SEC is unreachable (e.g. a sandbox). Run this on a machine WITH internet,
commit data/raw_snapshot/, then build anywhere.

    python3 scripts/fetch_raw.py --config configs/ifrs.json --tickers BCE SU VOD NVS \
        --years 2021 2022 2023 --user-agent "Your Name you@university.edu"
    python3 scripts/fetch_raw.py --config configs/usgaap_expansion.json --tickers HD UNH V

What it saves (per company):
  companyfacts_CIK<10 digits>.json  SEC companyfacts, TRIMMED to annual-report facts
                                    (10-K / 20-F / 40-F) for the requested years
                                    (typically 5-10% of the full file)
  filings/<accession>_cal.xml       the filing's own calculation linkbase, one per
                                    annual report used (balance-sheet structure)
  manifest.json                     what was fetched, when, from which URL, sha256

SEC requires a User-Agent with a real contact; pass yours. Stay under 10 requests/s.
Nothing is fabricated: files are SEC's, trimmed only by dropping facts outside the
requested forms and years. The IFRS Accounting Taxonomy is NOT fetched here (licence
terms; download it from ifrs.org yourself and point configs/ifrs.json at it, or build
the committed reference cache with scripts/build_ifrs_ref_cache.py).
"""
import argparse, datetime, hashlib, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from frameworks import get as _fw  # noqa: E402

OUT = os.path.join(ROOT, "data", "raw_snapshot")


def get(url, ua):
    time.sleep(0.15)
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=60).read()


def trim(facts, forms, years):
    keep = {"cik": facts.get("cik"), "entityName": facts.get("entityName"), "facts": {}}
    ys = {int(y) for y in years}
    for ns, concepts in facts.get("facts", {}).items():
        for name, node in concepts.items():
            units = {}
            for u, fl in node.get("units", {}).items():
                sel = [f for f in fl if str(f.get("form", "")).startswith(tuple(forms))
                       and (f.get("fy") in ys or str(f.get("end", ""))[:4].isdigit()
                            and int(str(f.get("end"))[:4]) in ys)]
                if sel:
                    units[u] = sel
            if units:
                keep["facts"].setdefault(ns, {})[name] = {"units": units}
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--tickers", nargs="*", help="subset of the config (default: all phase-1 companies)")
    ap.add_argument("--years", nargs="*", type=int, help="default: the config's fiscal_years")
    ap.add_argument("--user-agent", required=True, help='e.g. "Jane Doe jane@sfu.ca" (SEC policy)')
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(ROOT, a.config)))
    fw = _fw(cfg.get("framework", "us-gaap"))
    years = a.years or cfg["fiscal_years"]
    cos = [c for c in cfg["companies"] if c.get("phase", 1) == 1]
    if a.tickers:
        want = {t.upper() for t in a.tickers}
        cos = [c for c in cfg["companies"] if c["ticker"].upper() in want]
    os.makedirs(os.path.join(OUT, "filings"), exist_ok=True)
    man_p = os.path.join(OUT, "manifest.json")
    manifest = json.load(open(man_p)) if os.path.exists(man_p) else {"files": {}}

    for co in cos:
        cik = str(co["cik"]).zfill(10)
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        try:
            full = json.loads(get(url, a.user_agent))
        except Exception as e:
            print(f"[fail] {co['ticker']}: {e}"); continue
        print(f"{co['ticker']}: EDGAR entity = {full.get('entityName')!r}")
        slim = trim(full, fw["forms"], years)
        path = os.path.join(OUT, f"companyfacts_CIK{cik}.json")
        raw = json.dumps(slim, separators=(",", ":")).encode()
        open(path, "wb").write(raw)
        manifest["files"][os.path.relpath(path, ROOT)] = {
            "url": url, "fetched": datetime.datetime.utcnow().isoformat() + "Z",
            "sha256": hashlib.sha256(raw).hexdigest(), "trimmed_to": {"forms": list(fw["forms"]), "years": years}}

        # one calculation linkbase per annual report whose facts we use
        anchor = slim["facts"].get(fw["namespace"], {}).get(fw["anchors"]["assets"], {})
        accns = sorted({f["accn"] for fl in anchor.get("units", {}).values() for f in fl
                        if f.get("fp") == "FY" and f.get("fy") in set(years) and f.get("accn")})
        for accn in accns:
            dst = os.path.join(OUT, "filings", f"{accn}_cal.xml")
            if os.path.exists(dst):
                continue
            acc = accn.replace("-", "")
            try:
                idx = json.loads(get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/index.json", a.user_agent))
                cal = next((i["name"] for i in idx["directory"]["item"] if i["name"].endswith("_cal.xml")), None)
                if not cal:
                    print(f"   {accn}: no _cal.xml in the filing"); continue
                u = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{cal}"
                data = get(u, a.user_agent)
                open(dst, "wb").write(data)
                manifest["files"][os.path.relpath(dst, ROOT)] = {
                    "url": u, "fetched": datetime.datetime.utcnow().isoformat() + "Z",
                    "sha256": hashlib.sha256(data).hexdigest()}
                print(f"   {accn}: {cal}")
            except Exception as e:
                print(f"   {accn}: failed ({e})")
    json.dump(manifest, open(man_p, "w"), indent=1, sort_keys=True)
    print(f"\nsnapshot: {OUT}  (commit it; builds read it before trying the network)")


if __name__ == "__main__":
    main()
