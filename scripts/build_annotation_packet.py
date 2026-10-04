"""Build a blind development-review packet from public inputs only.

No scoring key, model prediction or authority recommendation is read. The
curator mapping must be outside the packet; access control is an operational
requirement, not something an opaque identifier alone can provide.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import random
import secrets

try:
    from .validate_annotations import digest, validate_record
except ImportError:  # direct script execution
    from validate_annotations import digest, validate_record

HERE = Path(__file__).resolve().parent
METADATA_FIELDS = ("cik", "company", "fiscal_year", "period", "statement_type", "unit")


def public_view(row: dict) -> dict:
    if not isinstance(row.get("statement_text"), str) or not isinstance(row.get("transaction_data"), str):
        raise ValueError("Each input needs statement_text and transaction_data strings; answer-key files are not inputs.")
    metadata = row.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    result = {"metadata": {key: metadata[key] for key in METADATA_FIELDS if key in metadata},
              "statement_text": row["statement_text"], "transaction_data": row["transaction_data"]}
    # Only scalar whitelisted metadata can cross the reviewer boundary.
    if any(not isinstance(value, (str, int, float, type(None))) or isinstance(value, bool) for value in result["metadata"].values()):
        raise ValueError("Metadata values must be public scalar values")
    return result


def select_company_balanced(rows: list[dict], count: int, rng: random.Random) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        view = public_view(row)
        company = view["metadata"].get("cik") or view["metadata"].get("company")
        if not company:
            raise ValueError("Each case needs a public company identifier for balanced development sampling")
        groups[str(company)].append(row)
    if not 1 <= count <= len(rows):
        raise ValueError("Requested packet size must be between one and available input count")
    names = sorted(groups)
    rng.shuffle(names)
    for members in groups.values():
        rng.shuffle(members)
    selected = []
    while len(selected) < count:
        for company in names:
            if groups[company] and len(selected) < count:
                selected.append(groups[company].pop())
    rng.shuffle(selected)
    return selected


def build_packet(rows: list[dict], count: int, *, seed: str | None = None) -> tuple[dict, dict, dict[str, dict]]:
    seed = secrets.token_hex(32) if seed is None else seed
    rng = random.Random(int(seed, 16))
    selected = select_company_balanced(rows, count, rng)
    template = json.loads((HERE.parent / "review" / "annotation_template.json").read_text())
    cases, mapping, annotations = [], [], {}
    used_ids = set()
    for row in selected:
        view = public_view(row)
        reviewer_id = "review_" + f"{rng.getrandbits(96):024x}"
        while reviewer_id in used_ids:
            reviewer_id = "review_" + f"{rng.getrandbits(96):024x}"
        used_ids.add(reviewer_id)
        case = {"review_id": reviewer_id, **view}
        cases.append(case)
        annotation = json.loads(json.dumps(template))
        annotation.update(annotation_id="annotation_" + reviewer_id, case_id=reviewer_id)
        annotation["scope"].update(assertion_family="other", assertion="Unresolved: expert must scope the assertion(s) from the evidence.",
                                   source_case_kind="hybrid", scope_limitations=["Development triage packet; source accessions, units, periods and authority applicability require reconciliation.",
                                   "The supplied transaction narrative is synthetic support, not authenticated bookkeeping.",
                                   "No expected conclusion, affected row or governing paragraph is supplied."])
        annotation["split"].update(assignment="development", initial_view_sha256=digest(view), observable_bundle_sha256=digest(view))
        annotation["notes"] = ["No human review has been performed.", "This blank packet template is development-only; resolve statement dates and source provenance before assigning an accounting conclusion.",
                               "One packet can contain multiple assertions. Create separately linked assertion records rather than forcing one label for the whole statement."]
        assert not validate_record(annotation)
        annotations[reviewer_id] = annotation
        mapping.append({"review_id": reviewer_id, "source_case_id": row.get("case_id") or row.get("exam_id"), "observable_sha256": digest(view)})
    packet = {"packet_version": "0.1.0", "purpose": "Blind development annotation; not independently adjudicated gold", "human_review_performed": False,
              "review_model": "single_qualified_accountant", "n_cases": len(cases), "cases": cases,
              "instructions": ["Review the supplied evidence without accessing old keys, model responses or another review.",
                               "Distinguish synthetic narratives from original filing evidence. Reconcile accession, unit, period and investigation date.",
                               "Identify assertion(s), required facts, refutations, uncertainty and applicable authoritative paragraph sets independently.",
                               "Use no_governing_paragraph only when a scoped conclusion requires no standards paragraph; missing knowledge/evidence is not that state.",
                               "Record unresolved items. The blank annotation template does not certify review or accounting correctness."]}
    private = {"purpose": "CURATOR ONLY: withhold this mapping and seed from reviewers", "seed": seed, "packet_sha256": digest(packet), "mapping": mapping}
    return packet, private, annotations


def render_html(packet: dict) -> str:
    sections = []
    for number, case in enumerate(packet["cases"], 1):
        metadata = " · ".join(f"{key}: {value}" for key, value in case["metadata"].items())
        fields = ["Assertion(s) reviewed and scope", "Selected filing accession / raw source / units / dates", "Observed facts and source locations", "Refutations and source reliability",
                  "Conclusion and evidence sufficiency", "Missing information and possible resolving evidence", "Authority source / paragraph sets / version / effective date / entity scope",
                  "Alternative sufficient proofs and deletion checks", "Uncertainty, exclusions and rationale", "Reviewer ID / timestamp / review effort"]
        worksheet = "".join(f"<label>{escape(field)}<textarea aria-label='{escape(field)}'></textarea></label>" for field in fields)
        sections.append(f"<section><h2>{number}. {escape(case['review_id'])}</h2><p class='metadata'>{escape(metadata)}</p>"
                        f"<div class='evidence'><article><h3>Statement as supplied</h3><pre>{escape(case['statement_text'])}</pre></article>"
                        f"<article><h3>Supplied synthetic supporting narrative</h3><pre>{escape(case['transaction_data'])}</pre></article></div>"
                        f"<h3>Blank reviewer worksheet</h3><div class='worksheet'>{worksheet}</div></section>")
    return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; form-action 'none'; base-uri 'none'">
<title>Blind accountant development packet</title><style>
body{font:16px/1.5 system-ui,sans-serif;color:#172231;background:#f4f6f8;margin:0 auto;max-width:1500px;padding:28px}
h1,h2,h3{line-height:1.2}.notice{background:#fff3ce;border-left:5px solid #9a6b00;padding:18px}section{background:white;margin:32px 0;padding:24px;border:1px solid #ccd5dd}
.metadata{color:#526070}.evidence{display:grid;grid-template-columns:1fr 1fr;gap:24px}pre{white-space:pre-wrap;font:13px/1.55 ui-monospace,monospace;overflow-wrap:anywhere}
label{display:block;font-weight:600;margin:16px 0}textarea{display:block;box-sizing:border-box;width:100%;min-height:88px;font:15px/1.4 inherit;border:1px solid #9faebd;padding:8px}
@media(max-width:800px){.evidence{grid-template-columns:1fr}body{padding:10px}section{padding:14px}}@media print{body{background:white;padding:0;font-size:11pt}section{break-before:page;border:0;padding:0}.evidence{display:block}textarea{min-height:56px}h2,h3{break-after:avoid}}
</style><h1>Blind accountant development packet</h1><div class="notice"><strong>No human review has been performed.</strong>
This packet contains supplied statements and synthetic support, not a validated benchmark. Old keys, expected answers, affected-row labels and model outputs are excluded.
Review original source accessions, units, periods and authoritative versions before assigning labels. One accountant is available; this is a single-expert workflow.</div>
<p>The worksheet is editable for working notes. This offline page does not save changes automatically: use Print to PDF to retain notes or enter them in the accompanying JSON templates.
Do not share the curator mapping with the reviewer. A future delayed repeat uses new opaque IDs and hides prior answers.</p>""" + "\n".join(sections) + "</html>\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--curator-output", required=True, type=Path)
    parser.add_argument("--n", type=int, default=16, help="development packet size; default 16")
    parser.add_argument("--all", action="store_true", help="include all supplied public cases; still development-only")
    args = parser.parse_args()
    output, private_path = args.output.resolve(), args.curator_output.resolve()
    if private_path == output or output in private_path.parents:
        parser.error("curator mapping must be outside the reviewer packet")
    if output.exists() or private_path.exists():
        parser.error("refusing to overwrite an existing packet or curator mapping")
    try:
        rows = [json.loads(line) for line in args.inputs.read_text().splitlines() if line.strip()]
        packet, private, annotations = build_packet(rows, len(rows) if args.all else args.n)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    private.update(input_file_sha256=sha256(args.inputs.read_bytes()).hexdigest(), created_at=datetime.now(timezone.utc).isoformat())
    output.mkdir(parents=True)
    (output / "annotations").mkdir()
    (output / "packet.json").write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n")
    (output / "packet.html").write_text(render_html(packet))
    for reviewer_id, annotation in annotations.items():
        (output / "annotations" / (reviewer_id + ".json")).write_text(json.dumps(annotation, indent=2) + "\n")
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_text(json.dumps(private, indent=2) + "\n")
    private_path.chmod(0o600)
    print(json.dumps({"reviewer_packet": str(output), "n_cases": packet["n_cases"], "packet_sha256": private["packet_sha256"],
                      "curator_mapping": str(private_path), "human_review_performed": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
