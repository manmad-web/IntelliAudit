"""Validate annotation records without inventing review or accounting truth.

The structural checker implements only the JSON Schema keywords used by the
bundled schema. It is deliberately not a general-purpose JSON Schema engine.
Semantic/release checks are additional to the portable structural schema.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE.parent / "review" / "annotation.schema.json"
GROUP_FIELDS = ("company_group_ids", "filing_group_ids", "event_group_ids", "pair_group_ids")
DECISION_FIELDS = ("conclusion", "authority_disposition", "acceptable_citation_sets", "accepted_proof_ids", "missing_fact_requirements")


def digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def gold_digest(record: dict) -> str:
    """Hash the entire decision-bearing state, not just its final label."""
    return digest({key: record[key] for key in ("scope", "sources", "cells", "facts", "authorities", "proof_sets", "gold")})


def review_digest(review: dict) -> str:
    return digest({key: value for key, value in review.items() if key != "submission_sha256"})


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed


def _matches_type(value: Any, kind: str) -> bool:
    return {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "null": value is None,
        "boolean": isinstance(value, bool), "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
    }[kind]


def structural_errors(value: Any, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    root = schema if root is None else root
    if "$ref" in schema:
        name = schema["$ref"].removeprefix("#/$defs/")
        return structural_errors(value, root["$defs"][name], root, path)
    errors = []
    kinds = schema.get("type")
    if kinds is not None:
        kinds = [kinds] if isinstance(kinds, str) else kinds
        if not any(_matches_type(value, kind) for kind in kinds):
            return [f"{path}: expected type {kinds}"]
    if "const" in schema and (value != schema["const"] or isinstance(value, bool) != isinstance(schema["const"], bool)):
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: unsupported value {value!r}")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        errors.extend(f"{path}.{key}: required" for key in schema.get("required", []) if key not in value)
        if schema.get("additionalProperties") is False:
            errors.extend(f"{path}.{key}: unknown field" for key in value if key not in properties)
        for key in value.keys() & properties.keys():
            errors.extend(structural_errors(value[key], properties[key], root, f"{path}.{key}"))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: too few items")
        if schema.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):
            errors.append(f"{path}: duplicate items")
        for index, item in enumerate(value):
            errors.extend(structural_errors(item, schema.get("items", {}), root, f"{path}[{index}]"))
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: empty string")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{path}: invalid pattern")
        try:
            if schema.get("format") == "date":
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError()
                date.fromisoformat(value)
            elif schema.get("format") == "date-time":
                _time(value)
            elif schema.get("format") == "uri" and not urlparse(value).scheme:
                raise ValueError()
        except ValueError:
            errors.append(f"{path}: invalid {schema['format']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
    return errors


def validate_record(record: dict, *, release: bool = False, schema: dict | None = None) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text()) if schema is None else schema
    errors = structural_errors(record, schema)
    if errors:
        return errors

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    indexes = {}
    for collection, key in (("sources", "document_id"), ("cells", "cell_id"), ("facts", "fact_id"),
                            ("authorities", "authority_id"), ("proof_sets", "proof_id"),
                            ("reviewers", "reviewer_id"), ("reviews", "review_id"), ("leakage_checks", "check_id")):
        indexes[collection] = {entry[key]: entry for entry in record[collection]}
        require(len(indexes[collection]) == len(record[collection]), f"{collection}: duplicate identifiers")

    def refs(values: list, collection: str, context: str) -> None:
        for value in values:
            require(value in indexes[collection], f"{context}: unknown {collection} reference {value}")

    scope, gold, split = record["scope"], record["gold"], record["split"]
    start, end, cutoff = scope["reporting_period_start"], scope["reporting_period_end"], scope["investigation_cutoff"]
    require(not (start and end and start > end), "scope: reporting dates reversed")
    for source in record["sources"]:
        label = source["document_id"]
        require(source["is_synthetic"] == (source["source_kind"] == "synthetic"), f"{label}: inconsistent synthetic provenance")
        if source["initially_visible"] or source["obtainable"]:
            require(not (cutoff and source["available_at"] and source["available_at"] > cutoff), f"{label}: evidence available after investigation cutoff")
        require(not (source["document_date"] and source["available_at"] and source["available_at"] < source["document_date"]), f"{label}: availability precedes document creation")
    for cell in record["cells"]:
        refs([cell["document_id"]], "sources", cell["cell_id"])
        require(not (cell["period_start"] and cell["period_end"] and cell["period_start"] > cell["period_end"]), f"{cell['cell_id']}: reversed cell period")
        if cell["period_kind"] == "instant":
            require(cell["period_start"] in (None, cell["period_end"]), f"{cell['cell_id']}: instant cell has duration context")
    for fact in record["facts"]:
        refs([fact["document_id"]], "sources", fact["fact_id"])
        refs(fact["source_cell_ids"], "cells", fact["fact_id"])
        source = indexes["sources"].get(fact["document_id"])
        if source and source["is_synthetic"]:
            require(fact["origin"] != "observed", f"{fact['fact_id']}: synthetic evidence labeled observed")
    for authority in record["authorities"]:
        refs(authority["required_fact_ids"] + authority["refutation_fact_ids"], "facts", authority["authority_id"])
        require(not (authority["effective_from"] and authority["effective_to"] and authority["effective_from"] > authority["effective_to"]), f"{authority['authority_id']}: reversed effective dates")
    for proof in record["proof_sets"]:
        refs(proof["fact_ids"] + proof["refutation_fact_ids"], "facts", proof["proof_id"])
        refs(proof["authority_ids"], "authorities", proof["proof_id"])
        refs(proof["minimality"]["reviewer_ids"], "reviewers", proof["proof_id"])
        for edge in proof["edges"]:
            require(edge["from_fact_id"] in proof["fact_ids"] and edge["to_fact_id"] in proof["fact_ids"], f"{proof['proof_id']}: edge endpoint outside proof")
            require(edge["from_fact_id"] != edge["to_fact_id"], f"{proof['proof_id']}: self-edge is not a source join")
        for test in proof["minimality"]["deletion_tests"]:
            require(test["removed_fact_id"] in proof["fact_ids"], f"{proof['proof_id']}: deletion test outside proof")
    for record_decision in [gold, *record["reviews"]]:
        refs(record_decision["accepted_proof_ids"], "proof_sets", "decision")
        for alternative in record_decision["acceptable_citation_sets"]:
            require(bool(alternative), "decision: empty acceptable citation alternative")
            refs(alternative, "authorities", "decision")
        disposition = record_decision["authority_disposition"]
        if disposition == "governing_paragraph":
            require(bool(record_decision["acceptable_citation_sets"]), "decision: governing paragraph requires an accepted authority set")
        else:
            require(not record_decision["acceptable_citation_sets"], "decision: non-governing disposition cannot carry accepted authority sets")
    for review in record["reviews"]:
        refs([review["reviewer_id"]], "reviewers", review["review_id"])
        refs(review["support_fact_ids"] + review["refutation_fact_ids"], "facts", review["review_id"])
        reviewer = indexes["reviewers"].get(review["reviewer_id"])
        if reviewer and review["phase"] in ("expert_first_pass", "expert_repeat"):
            require(reviewer["role"] == "accounting_expert", f"{review['review_id']}: student/curator cannot be counted as an expert review")
        if review["submission_sha256"]:
            require(review["submission_sha256"] == review_digest(review), f"{review['review_id']}: submission digest mismatch")
    if record["resolution"]["gold_sha256"]:
        require(record["resolution"]["gold_sha256"] == gold_digest(record), "resolution: decision-bearing state changed after gold hash")
    if record["release_status"] == "eligible":
        require(record["status"] == "expert_reviewed", "eligible records must be expert_reviewed")
    if not release and record["release_status"] != "eligible":
        return errors

    require(record["status"] == "expert_reviewed", "release: expert review is incomplete or case excluded")
    require(record["release_status"] == "eligible", "release: eligibility has not been attested")
    require(scope["framework"] != "experimental_only", "release: experimental contracts are not accounting authority")
    for key in ("assertion", "entity_type", "reporting_period_start", "reporting_period_end", "investigation_cutoff"):
        require(bool(scope[key]), f"release: scope.{key} missing")
    require(bool(scope["jurisdiction"]), "release: jurisdiction missing")
    require(bool(record["sources"]), "release: source bundle empty")
    for source in record["sources"]:
        for key in ("sha256", "retrieved_at", "document_date", "available_at", "provenance_note"):
            require(bool(source[key]), f"release: {source['document_id']}.{key} missing")
        if not source["is_synthetic"]:
            require(bool(source["source_url"]), f"release: {source['document_id']} source locator missing")
        if source["source_kind"] in ("original_filing", "restated_filing"):
            require(bool(source["accession"]), f"release: {source['document_id']} accession missing")
        require(source["rights_status"] != "unresolved", f"release: {source['document_id']} release rights unresolved")
    for cell in record["cells"]:
        require(cell["verified_against_selected_source"], f"release: {cell['cell_id']} source not verified")
        for key in ("raw_value", "normalized_value", "unit", "scale_factor", "sign_convention", "transformation"):
            require(cell[key] is not None and cell[key] != "", f"release: {cell['cell_id']}.{key} missing")
        require(cell["period_kind"] != "unresolved", f"release: {cell['cell_id']} period kind unresolved")
        if cell["period_kind"] in ("instant", "duration"):
            require(bool(cell["period_end"]), f"release: {cell['cell_id']} period end missing")
        if cell["period_kind"] == "duration":
            require(bool(cell["period_start"]), f"release: {cell['cell_id']} duration start missing")
    require(gold["conclusion"] not in ("unresolved", "excluded"), "release: final conclusion unresolved/excluded")
    require(gold["decision_sufficiency"] != "unresolved", "release: decision sufficiency unresolved")
    require(gold["authority_disposition"] not in ("unresolved", "out_of_scope"), "release: authority disposition unresolved/out of scope")
    require(bool(gold["rationale"].strip()), "release: accounting rationale missing")
    if gold["conclusion"] in ("supported_misstatement", "supported_compliance"):
        require(gold["decision_sufficiency"] == "sufficient" and bool(gold["accepted_proof_ids"]), "release: definitive conclusion needs sufficient accepted proof")
    if gold["conclusion"] in ("insufficient_evidence", "suspicious"):
        require(gold["decision_sufficiency"] == "insufficient", "release: unresolved conclusion cannot have sufficient decision evidence")
        require(not gold["accepted_proof_ids"], "release: unresolved conclusion cannot carry accepted definitive proof")
    if gold["conclusion"] == "insufficient_evidence" or gold["authority_disposition"] == "insufficient_evidence":
        require(bool(gold["missing_fact_requirements"]), "release: insufficient evidence needs named missing requirements")
    accepted_authority_ids = {item for group in gold["acceptable_citation_sets"] for item in group}
    for authority in record["authorities"]:
        require(authority["applicability"] in ("supported", "rejected") and authority["scope_decision"] != "unresolved",
                f"release: {authority['authority_id']} still has unresolved candidate applicability")
    for proof_id in gold["accepted_proof_ids"]:
        proof = indexes["proof_sets"].get(proof_id)
        if proof:
            accepted_authority_ids.update(proof["authority_ids"])
    for authority_id in accepted_authority_ids:
        authority = indexes["authorities"].get(authority_id)
        if not authority:
            continue
        require(authority["source_kind"] in ("canonical_standard", "regulator_rule"), f"release: {authority_id} is discovery/guidance rather than canonical authority")
        require(authority["scope_decision"] == "in_scope" and authority["applicability"] == "supported", f"release: {authority_id} applicability not established")
        for key in ("canonical_code", "source_url", "snapshot_sha256", "version_label", "checked_at", "effective_from", "adoption_basis", "governed_assertion", "rationale"):
            require(bool(authority[key]), f"release: {authority_id}.{key} missing")
        require(bool(authority["jurisdiction"]) and bool(authority["entity_scope"]), f"release: {authority_id} jurisdiction/entity scope missing")
        require(bool(set(authority["jurisdiction"]) & set(scope["jurisdiction"])), f"release: {authority_id} jurisdiction does not cover this case")
        require(scope["entity_type"] in authority["entity_scope"] or "all_entities" in authority["entity_scope"], f"release: {authority_id} entity scope does not cover this case")
        require(authority["assertion_family"] in (scope["assertion_family"], "cross_cutting"), f"release: {authority_id} assertion family does not cover this case")
        if authority["source_kind"] == "canonical_standard":
            require(authority["framework"] == scope["framework"], f"release: {authority_id} framework does not match case")
        if authority["source_kind"] == "regulator_rule":
            require(authority["framework"] == "regulatory", f"release: {authority_id} regulator source has inconsistent framework")
        require(bool(authority["required_fact_ids"]), f"release: {authority_id} has no applicability facts")
        if end and authority["effective_from"]:
            require(authority["effective_from"] <= end, f"release: {authority_id} not yet effective at reporting date")
        if end and authority["effective_to"]:
            require(end <= authority["effective_to"], f"release: {authority_id} expired before reporting date")
        code = authority["canonical_code"] or ""
        if authority["source_kind"] == "canonical_standard" and scope["framework"] == "us_gaap":
            require(bool(re.fullmatch(r"ASC \d{3}-\d{2}-\d{2}-\d+[A-Za-z]?(?:\([a-z0-9]+\))*", code)), f"release: {authority_id} requires full ASC paragraph identifier")

    expert_id = record["resolution"]["expert_reviewer_id"]
    expert = indexes["reviewers"].get(expert_id)
    require(bool(expert), "release: resolving expert not identified")
    if expert:
        require(expert["role"] == "accounting_expert" and expert["qualification_verified"], "release: expert qualification not verified")
        for key in ("qualification_basis", "qualification_verifier_id", "qualification_verified_at"):
            require(bool(expert[key]), f"release: reviewer.{key} missing")
        require(scope["framework"] in expert["framework_expertise"], "release: expert framework coverage not documented")
        require(scope["assertion_family"] in expert["assertion_expertise"], "release: expert assertion coverage not documented")
    first = [review for review in record["reviews"] if review["phase"] == "expert_first_pass" and review["reviewer_id"] == expert_id]
    repeats = [review for review in record["reviews"] if review["phase"] == "expert_repeat" and review["reviewer_id"] == expert_id]
    require(len(first) == 1, "release: exactly one preserved expert first pass required")
    if record["review_plan"]["repeat_required"]:
        require(len(repeats) == 1, "release: selected case requires one preserved delayed expert repeat")
    for review in first + repeats:
        for key in ("submitted_at", "bundle_sha256", "submission_sha256", "rationale"):
            require(bool(review[key]), f"release: {review['review_id']}.{key} missing")
        for flag in ("constructed_case", "saw_peer_annotation", "saw_own_prior_annotation", "saw_student_draft", "saw_reference_key", "saw_model_output"):
            require(not review[flag], f"release: {review['review_id']} blinding violated ({flag})")
        require(review["manual_version"] == record["review_plan"]["manual_version"], "release: review/manual version mismatch")
        require(bool(split["observable_bundle_sha256"]) and review["bundle_sha256"] == split["observable_bundle_sha256"], "release: expert reviewed a different/unhashed source bundle")
    if first and repeats and first[0]["submitted_at"] and repeats[0]["submitted_at"]:
        elapsed = (_time(repeats[0]["submitted_at"]) - _time(first[0]["submitted_at"])).total_seconds() / 86400
        require(elapsed >= record["review_plan"]["minimum_repeat_delay_days"], "release: repeat performed before minimum delay")
        selection_time = record["review_plan"]["repeat_selection_frozen_at"]
        require(bool(selection_time) and _time(selection_time) <= _time(repeats[0]["submitted_at"]), "release: repeat selected after repeat submission")
    resolution = record["resolution"]
    require(resolution["mode"] == "single_expert_resolution", "release: single-expert resolution incomplete")
    for key in ("recorder_id", "completed_at", "gold_sha256"):
        require(bool(resolution[key]), f"release: resolution.{key} missing")
    for review in first + repeats:
        if resolution["completed_at"] and review["submitted_at"]:
            require(_time(review["submitted_at"]) <= _time(resolution["completed_at"]), "release: final resolution precedes expert submission")
    if split["frozen_at"] and resolution["completed_at"]:
        require(_time(resolution["completed_at"]) <= _time(split["frozen_at"]), "release: split/gold freeze precedes final resolution")
    selection_time = record["review_plan"]["repeat_selection_frozen_at"]
    if selection_time and resolution["completed_at"]:
        require(_time(selection_time) <= _time(resolution["completed_at"]), "release: repeat allocation frozen after final resolution")
    if first:
        changed = any(first[0][field] != gold[field] for field in DECISION_FIELDS)
        changed |= any(any(first[0][field] != repeat[field] for field in DECISION_FIELDS) for repeat in repeats)
        require(not changed or bool(resolution["resolutions"]), "release: changed/disagreed decisions require recorded resolution")
    for proof in record["proof_sets"]:
        require(proof["minimality"]["status"] != "not_reviewed" and expert_id in proof["minimality"]["reviewer_ids"],
                f"release: {proof['proof_id']} remains an unreviewed candidate proof")
    for proof_id in gold["accepted_proof_ids"]:
        proof = indexes["proof_sets"].get(proof_id)
        if not proof:
            continue
        require(proof["conclusion"] == gold["conclusion"], f"release: {proof_id} supports a different conclusion")
        require(bool(proof["fact_ids"]), f"release: {proof_id} empty proof")
        for fact_id in proof["fact_ids"]:
            fact = indexes["facts"].get(fact_id)
            if not fact:
                continue
            require(fact["role"] != "missing_requirement", f"release: {proof_id} treats a missing fact as established")
            require(fact["origin"] != "derived" or bool(fact["derivation"].strip()), f"release: {fact_id} derivation missing")
            source = indexes["sources"].get(fact["document_id"])
            if source:
                require(source["initially_visible"] or source["obtainable"], f"release: {proof_id} depends on evidence outside the observation interface")
                require(bool(cutoff and source["available_at"]) and source["available_at"] <= cutoff, f"release: {proof_id} depends on evidence unavailable by cutoff")
        require(proof["minimality"]["status"] == "passed" and expert_id in proof["minimality"]["reviewer_ids"], f"release: {proof_id} minimality not reviewed by resolving expert")
        tests = proof["minimality"]["deletion_tests"]
        require({test["removed_fact_id"] for test in tests} == set(proof["fact_ids"]) and len(tests) == len(proof["fact_ids"]), f"release: {proof_id} needs exactly one deletion test per fact")
        require(all(test["still_sufficient"] is False and bool(test["rationale"].strip()) for test in tests), f"release: {proof_id} deletion does not establish relative minimality")
        require(bool(proof["refutation_resolution"].strip()), f"release: {proof_id} refutation assessment missing")
        if gold["authority_disposition"] == "governing_paragraph":
            require(any(set(group) <= set(proof["authority_ids"]) for group in gold["acceptable_citation_sets"]), f"release: {proof_id} lacks an accepted authority set")
        else:
            require(not proof["authority_ids"], f"release: {proof_id} uses authority despite a non-governing disposition")
        for authority_id in proof["authority_ids"]:
            authority = indexes["authorities"].get(authority_id)
            if authority:
                require(set(authority["required_fact_ids"]) <= set(proof["fact_ids"]), f"release: {proof_id} omits required applicability facts for {authority_id}")
                require(set(authority["refutation_fact_ids"]) <= set(proof["refutation_fact_ids"]), f"release: {proof_id} omits known authority refutations for {authority_id}")
    required_checks = set(schema["$defs"]["check"]["properties"]["check_id"]["enum"])
    require(set(indexes["leakage_checks"]) == required_checks, "release: leakage check inventory incomplete")
    for check in record["leakage_checks"]:
        require(check["status"] in ("passed", "not_applicable"), f"release: {check['check_id']} not cleared")
        require(bool(check["rationale"].strip()), f"release: {check['check_id']} rationale missing")
        require(check["reviewer_id"] in indexes["reviewers"], f"release: {check['check_id']} reviewer unknown")
        if check["status"] == "passed":
            require(bool(check["artifact_sha256"]), f"release: {check['check_id']} evidence hash missing")
        if check["check_id"] in ("payload_gold_leakage", "metadata_shortcuts", "cross_split_duplicates"):
            require(check["status"] == "passed", f"release: {check['check_id']} is mandatory")
    require(bool(split["company_group_ids"]) and bool(split["event_group_ids"]), "release: company/event dependency groups missing")
    if scope["source_case_kind"] != "synthetic":
        require(bool(split["filing_group_ids"]), "release: source filing dependency group missing")
    require(split["assignment"] != "unassigned", "release: split unassigned")
    for key in ("freeze_id", "frozen_at", "protocol_sha256", "initial_view_sha256", "observable_bundle_sha256"):
        require(bool(split[key]), f"release: split.{key} missing")
    require(bool(record["review_plan"]["repeat_selection_frozen_at"]), "release: repeat subset selection not frozen")
    return errors


def validate_batch(records: list[dict], *, release: bool = False, complete_dataset: bool = False) -> list[str]:
    errors = []
    seen_cases, seen_annotations, groups = set(), set(), {}
    for index, record in enumerate(records):
        local = validate_record(record, release=release)
        errors.extend(f"record[{index}]: {error}" for error in local)
        if structural_errors(record, json.loads(SCHEMA_PATH.read_text())):
            continue
        for value, seen, label in ((record["case_id"], seen_cases, "case"), (record["annotation_id"], seen_annotations, "annotation")):
            if value in seen:
                errors.append(f"batch: duplicate {label} identifier {value}")
            seen.add(value)
        split = record["split"]
        if split["assignment"] == "unassigned":
            continue
        for field in GROUP_FIELDS:
            for group in split[field]:
                key = (field, group)
                previous = groups.setdefault(key, split["assignment"])
                if previous != split["assignment"]:
                    errors.append(f"batch: dependency {field}:{group} crosses {previous}/{split['assignment']} splits")
    if complete_dataset:
        eligible = [record for record in records if record.get("release_status") == "eligible" and isinstance(record.get("review_plan"), dict)]
        repeated = sum(bool(record.get("review_plan", {}).get("repeat_required")) for record in eligible)
        if not eligible or not 0.10 <= repeated / len(eligible) <= 0.20:
            errors.append(f"batch: full-corpus blind-repeat fraction must be 10–20% (observed {repeated}/{len(eligible)}); tiny-pilot rounding is a reported development exception")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--release", action="store_true", help="require documented single-expert release gates")
    parser.add_argument("--complete-dataset", action="store_true", help="also check full-corpus 10–20% delayed repeat allocation")
    parser.add_argument("--print-gold-hash", action="store_true", help="print decision-state digest without modifying records")
    parser.add_argument("--print-review-hashes", action="store_true", help="print submission digests without inventing reviews")
    args = parser.parse_args()
    records = []
    for path in args.files:
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            print(f"ERROR {path}: {exc}")
            return 1
        records.append(record)
    if args.print_gold_hash or args.print_review_hashes:
        for path, record in zip(args.files, records):
            errors = structural_errors(record, json.loads(SCHEMA_PATH.read_text()))
            if errors:
                print(f"ERROR {path}: {errors}")
                return 1
            if args.print_gold_hash:
                print(f"{path}: {gold_digest(record)}")
            if args.print_review_hashes:
                for review in record["reviews"]:
                    print(f"{path}:{review['review_id']}: {review_digest(review)}")
        return 0
    errors = validate_batch(records, release=args.release, complete_dataset=args.complete_dataset)
    for error in errors:
        print(f"ERROR {error}")
    if errors:
        print(f"FAILED: {len(errors)} consistency/release errors; no records changed.")
        return 1
    print(f"PASS: {len(records)} structurally and semantically consistent record(s). "
          "This does not authenticate reviewers, sources, or accounting correctness.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
