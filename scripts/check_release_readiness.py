"""Machine-readable publication-record gate; never approves human accounting.

Dashboard workflow records are deliberately not accepted as publication gold.
Every frozen final case must have a full, single-expert annotation record.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

try:
    from .validate_annotations import SCHEMA_PATH, validate_batch, validate_record
except ImportError:
    from validate_annotations import SCHEMA_PATH, validate_batch, validate_record

ROOT = Path(__file__).resolve().parents[1]


def manifest_case_ids(manifest: dict) -> list[str]:
    if not isinstance(manifest, dict):
        raise ValueError("case manifest must be an object")
    if isinstance(manifest.get("case_ids"), list):
        case_ids = manifest["case_ids"]
    elif isinstance(manifest.get("cases"), list):
        case_ids = [item.get("case_id") or item.get("review_id") for item in manifest["cases"] if isinstance(item, dict)]
        if len(case_ids) != len(manifest["cases"]):
            raise ValueError("cases entries must be objects")
    else:
        raise ValueError("case manifest requires case_ids[] or cases[] with case_id/review_id")
    if not case_ids or any(not isinstance(case_id, str) or not case_id for case_id in case_ids):
        raise ValueError("the frozen final case inventory must be nonempty and have valid IDs")
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("duplicate IDs in frozen final case inventory")
    return case_ids


def assess_release(annotation_dir: Path, case_manifest: Path | None, *, complete_dataset: bool = True) -> dict:
    blockers, records, file_hashes = [], [], {}
    expected = []
    manifest_hash = None
    if case_manifest is None:
        blockers.append({"code": "missing_case_manifest", "detail": "An explicit frozen final case inventory is required; checking only submitted easy cases is not sufficient."})
    else:
        try:
            raw = case_manifest.read_bytes()
            expected = manifest_case_ids(json.loads(raw))
            manifest_hash = sha256(raw).hexdigest()
        except (OSError, ValueError, TypeError) as exc:
            blockers.append({"code": "invalid_case_manifest", "detail": str(exc)})
    files = sorted(annotation_dir.glob("*.json")) if annotation_dir.is_dir() else []
    if not files:
        blockers.append({"code": "no_annotations", "detail": "No completed publication annotation records were found. Empty annotation sets never pass."})
    for path in files:
        try:
            raw = path.read_bytes()
            record = json.loads(raw)
            if not isinstance(record, dict):
                raise ValueError("annotation must be a JSON object")
            file_hashes[path.name] = sha256(raw).hexdigest()
            records.append(record)
        except (OSError, ValueError) as exc:
            blockers.append({"code": "unreadable_annotation", "file": path.name, "detail": str(exc)})
    actual = [record.get("case_id") for record in records if isinstance(record.get("case_id"), str)]
    missing, unexpected = sorted(set(expected) - set(actual)), sorted(set(actual) - set(expected))
    if missing:
        blockers.append({"code": "missing_case_reviews", "case_ids": missing})
    if unexpected:
        blockers.append({"code": "cases_outside_final_inventory", "case_ids": unexpected})
    for error in validate_batch(records, release=True, complete_dataset=complete_dataset):
        blockers.append({"code": "annotation_gate_failure", "detail": error})
    if records and not expected:
        blockers.append({"code": "coverage_not_established", "detail": "Records cannot pass without the complete frozen final inventory."})
    statuses = Counter(record.get("status", "missing_status") if isinstance(record.get("status", "missing_status"), str) else "invalid_status" for record in records)
    independently_qualified_experts = {
        reviewer.get("reviewer_id")
        for record in records for reviewer in (record.get("reviewers", []) if isinstance(record.get("reviewers", []), list) else [])
        if isinstance(reviewer, dict) and reviewer.get("role") == "accounting_expert" and reviewer.get("qualification_verified") is True
    }
    passing_records = sum(not validate_record(record, release=True) for record in records)
    return {
        "gate_version": "0.1.0", "checked_at": datetime.now(timezone.utc).isoformat(),
        "release_ready": not blockers, "meaning": "Consistency of documented single-expert publication prerequisites; this does not authenticate human review or accounting correctness and does not publish anything.",
        "permitted_review_claim": "single-expert reviewed, only after actual accountant completion; never dual-expert adjudicated gold",
        "annotation_directory": str(annotation_dir), "case_manifest": str(case_manifest) if case_manifest else None,
        "expected_case_count": len(expected), "annotation_record_count": len(records), "records_passing_release_checks": passing_records,
        "status_counts": dict(statuses), "declared_qualified_expert_count": len(independently_qualified_experts),
        "repeat_fraction_checked": complete_dataset, "blocker_count": len(blockers), "blockers": blockers,
        "source_hashes": {"schema_sha256": sha256(SCHEMA_PATH.read_bytes()).hexdigest(),
                          "validator_sha256": sha256(Path(__file__).with_name("validate_annotations.py").read_bytes()).hexdigest(),
                          "gate_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                          "case_manifest_sha256": manifest_hash, "annotation_files": file_hashes},
        "not_checked_by_this_gate": ["The identity, credentials, independence and actual work of a human reviewer.",
                                     "Normative accounting correctness, source authenticity, authority licensing and semantic equivalence of proofs.",
                                     "Secure reviewer/model access boundaries, statistical power, model-comparison fairness and scientific novelty."]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=ROOT / "review" / "annotations")
    parser.add_argument("--case-manifest", type=Path, default=ROOT / "data" / "review_pilot" / "manifest.json")
    parser.add_argument("--output", type=Path, help="optional JSON status artifact")
    parser.add_argument("--development-subset", action="store_true", help="skip full-corpus repeat-fraction calculation; all case-level review gates still apply")
    args = parser.parse_args()
    report = assess_release(args.annotations, args.case_manifest, complete_dataset=not args.development_subset)
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if report["release_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
