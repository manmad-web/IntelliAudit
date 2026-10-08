"""Software-gate tests. Mock attestations here are never human review records."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.validate_annotations import gold_digest, review_digest, validate_batch, validate_record
from scripts.build_annotation_packet import build_packet, render_html
from scripts.check_release_readiness import assess_release


HERE = Path(__file__).resolve().parents[1] / "review"


def fixture():
    """In-memory mock of completed paperwork; no accounting-validity claim."""
    item = json.loads((HERE / "annotation_template.json").read_text())
    item.update(annotation_id="annotation_test", case_id="case_test", status="expert_reviewed", release_status="eligible")
    item["scope"].update(jurisdiction=["US"], assertion="Test-only arithmetic reconciliation.", entity_type="fictional_test_issuer",
                         reporting_period_start="2024-01-01", reporting_period_end="2024-12-31", investigation_cutoff="2025-02-15",
                         source_case_kind="synthetic", synthetic_assumptions=["Unit-test mock; not accounting gold."])
    item["sources"] = [{"document_id": "doc_test", "source_kind": "synthetic", "accession": None, "source_url": None,
                        "sha256": "a" * 64, "retrieved_at": "2026-10-01T00:00:00Z", "document_date": "2024-12-31",
                        "available_at": "2025-01-01", "initially_visible": True, "obtainable": True, "is_synthetic": True,
                        "rights_status": "redistribution_permitted", "provenance_note": "Mock source for software test only."}]
    item["facts"] = [{"fact_id": "fact_test", "document_id": "doc_test", "locator": "test row", "proposition": "Mock arithmetic mismatch.",
                      "origin": "synthetic", "source_cell_ids": [], "event_date": "2024-12-31", "entity_refs": ["test_entity"],
                      "role": "support", "derivation": "", "reliability_assessment": "Mock assessment."}]
    item["reviewers"] = [{"reviewer_id": "mock_expert", "role": "accounting_expert", "is_human": True,
                          "qualification_basis": "TEST STUB: no real human review.", "framework_expertise": ["us_gaap"],
                          "assertion_expertise": ["revenue_cutoff"], "qualification_verified": True,
                          "qualification_verifier_id": "mock_curator", "qualification_verified_at": "2026-10-01"}]
    item["proof_sets"] = [{"proof_id": "proof_test", "conclusion": "supported_misstatement", "fact_ids": ["fact_test"], "edges": [],
                           "authority_ids": [], "refutation_fact_ids": [], "assumptions": [], "refutation_resolution": "Test-only no-refutation assessment.",
                           "minimality": {"status": "passed", "reviewer_ids": ["mock_expert"],
                                          "deletion_tests": [{"removed_fact_id": "fact_test", "still_sufficient": False, "rationale": "Mock only fact removed."}],
                                          "scope_note": "Relative to this unit-test universe."}}]
    item["gold"].update(conclusion="supported_misstatement", decision_sufficiency="sufficient", authority_disposition="no_governing_paragraph",
                        accepted_proof_ids=["proof_test"], rationale="Mock arithmetic-only task does not prescribe authority.")
    review = {"review_id": "review_test", "reviewer_id": "mock_expert", "phase": "expert_first_pass", "submitted_at": "2026-10-03T12:00:00Z",
              "manual_version": "0.1.0", "bundle_sha256": "b" * 64, "submission_sha256": None,
              "constructed_case": False, "saw_peer_annotation": False, "saw_own_prior_annotation": False, "saw_student_draft": False,
              "saw_reference_key": False, "saw_model_output": False, "conclusion": "supported_misstatement",
              "authority_disposition": "no_governing_paragraph", "acceptable_citation_sets": [], "accepted_proof_ids": ["proof_test"],
              "support_fact_ids": ["fact_test"], "refutation_fact_ids": [], "missing_fact_requirements": [], "rationale": "Mock review, not a real attestation."}
    review["submission_sha256"] = review_digest(review)
    item["reviews"] = [review]
    item["resolution"].update(mode="single_expert_resolution", recorder_id="mock_curator", expert_reviewer_id="mock_expert", completed_at="2026-10-12T12:00:00Z")
    item["review_plan"].update(repeat_selection_frozen_at="2026-10-03T18:00:00Z", repeat_strata=["test_stratum"])
    for check in item["leakage_checks"]:
        check.update(status="passed", artifact_sha256="c" * 64, reviewer_id="mock_expert", rationale="Mock software-gate evidence only.")
    item["split"].update(company_group_ids=["company_test"], event_group_ids=["event_test"], assignment="development", freeze_id="freeze_test",
                         frozen_at="2026-10-13T00:00:00Z", protocol_sha256="d" * 64, initial_view_sha256="e" * 64, observable_bundle_sha256="b" * 64)
    item["notes"] = ["UNIT TEST ONLY. These synthetic attestations never represent a reviewed benchmark case."]
    item["resolution"]["gold_sha256"] = gold_digest(item)
    return item


def add_repeat(item, when="2026-10-11T12:00:00Z"):
    repeat = deepcopy(item["reviews"][0])
    repeat.update(review_id="review_repeat", phase="expert_repeat", submitted_at=when)
    repeat["submission_sha256"] = review_digest(repeat)
    item["reviews"].append(repeat)
    item["review_plan"]["repeat_required"] = True


def immediate_fixture():
    item = fixture()
    item["review_plan"].update(protocol_id="immediate_reconciliation_v2", reliability_status="reliability_not_measured",
                               repeat_required=False, minimum_repeat_delay_days=0,
                               repeat_selection_frozen_at=None, repeat_strata=[])
    return item


def add_mock_authority(item):
    item["authorities"] = [{"authority_id": "authority_test", "canonical_code": "ASC 606-10-25-23", "source_kind": "canonical_standard",
                            "framework": "us_gaap", "assertion_family": "revenue_cutoff", "source_url": "urn:unit-test:authority", "snapshot_sha256": "f" * 64,
                            "version_label": "MOCK ONLY", "checked_at": "2026-10-03", "effective_from": "2018-01-01", "effective_to": None,
                            "adoption_basis": "Mock applicability metadata, never actual authority review.", "jurisdiction": ["US"], "entity_scope": ["fictional_test_issuer"],
                            "governed_assertion": "Mock assertion.", "scope_decision": "in_scope", "applicability": "supported", "required_fact_ids": ["fact_test"],
                            "refutation_fact_ids": [], "exceptions_considered": [], "rationale": "Test-only rationale."}]
    item["gold"].update(authority_disposition="governing_paragraph", acceptable_citation_sets=[["authority_test"]])
    item["proof_sets"][0]["authority_ids"] = ["authority_test"]
    item["resolution"]["resolutions"] = [{"issue": "Mock changed label.", "resolution": "Mock accepted authority.", "rationale": "Software test only."}]
    item["resolution"]["gold_sha256"] = gold_digest(item)


class AnnotationValidationTests(unittest.TestCase):
    def test_drafts_validate_without_becoming_reviewed(self):
        for name in ("annotation_template.json", "annotation_example_unreviewed.json"):
            record = json.loads((HERE / name).read_text())
            self.assertEqual(validate_record(record), [])
            self.assertTrue(validate_record(record, release=True))
            self.assertEqual(record["reviews"], [])

    def test_documented_single_expert_gate_can_pass(self):
        self.assertEqual(validate_record(fixture(), release=True), [])

    def test_student_draft_cannot_substitute_for_expert(self):
        record = fixture()
        record["reviewers"][0]["role"] = "student"
        self.assertTrue(any("expert" in x for x in validate_record(record, release=True)))

    def test_changed_fact_invalidates_gold_signature(self):
        record = fixture()
        record["facts"][0]["proposition"] = "Changed after review."
        self.assertTrue(any("state changed" in x for x in validate_record(record)))

    def test_changed_review_invalidates_submission_signature(self):
        record = fixture()
        record["reviews"][0]["rationale"] = "Rewritten after submission."
        self.assertTrue(any("submission digest" in x for x in validate_record(record)))

    def test_future_evidence_is_not_observable(self):
        record = json.loads((HERE / "annotation_example_unreviewed.json").read_text())
        record["sources"][0]["available_at"] = "2026-01-01"
        self.assertTrue(any("after investigation cutoff" in x for x in validate_record(record)))

    def test_proof_requires_known_endpoints(self):
        record = json.loads((HERE / "annotation_example_unreviewed.json").read_text())
        record["proof_sets"][0]["edges"][0]["to_fact_id"] = "fact_invented"
        self.assertTrue(any("outside proof" in x for x in validate_record(record)))

    def test_failed_minimality_is_not_release_ready(self):
        record = fixture()
        record["proof_sets"][0]["minimality"]["deletion_tests"][0]["still_sufficient"] = True
        record["resolution"]["gold_sha256"] = gold_digest(record)
        self.assertTrue(any("minimality" in x for x in validate_record(record, release=True)))

    def test_repeat_is_delayed_and_blind(self):
        record = fixture()
        add_repeat(record)
        self.assertEqual(validate_record(record, release=True), [])
        record["reviews"][1]["submitted_at"] = "2026-10-04T12:00:00Z"
        record["reviews"][1]["submission_sha256"] = review_digest(record["reviews"][1])
        self.assertTrue(any("minimum delay" in x for x in validate_record(record, release=True)))
        record["reviews"][1]["submitted_at"] = "2026-10-11T12:00:00Z"
        record["reviews"][1]["saw_own_prior_annotation"] = True
        record["reviews"][1]["submission_sha256"] = review_digest(record["reviews"][1])
        self.assertTrue(any("blinding violated" in x for x in validate_record(record, release=True)))

    def test_unresolved_authority_cannot_be_called_governing(self):
        record = fixture()
        record["gold"]["authority_disposition"] = "governing_paragraph"
        record["resolution"]["gold_sha256"] = gold_digest(record)
        self.assertTrue(any("accepted authority set" in x for x in validate_record(record)))

    def test_grouped_split_leakage_is_detected(self):
        first = fixture()
        second = deepcopy(first)
        second.update(case_id="case_other", annotation_id="annotation_other")
        second["split"]["assignment"] = "test"
        self.assertTrue(any("crosses" in x for x in validate_batch([first, second])))

    def test_typo_fields_and_invalid_dates_rejected(self):
        record = fixture()
        record["scope"]["reporting_period_end"] = "2024-02-30"
        record["scope"]["recommended_answer"] = "leak"
        errors = validate_record(record)
        self.assertTrue(any("invalid date" in x for x in errors))
        self.assertTrue(any("unknown field" in x for x in errors))

    def test_full_corpus_repeat_allocation(self):
        records = []
        for index in range(10):
            record = fixture()
            record.update(case_id=f"case_{index}", annotation_id=f"annotation_{index}")
            records.append(record)
        self.assertTrue(any("repeat fraction" in x for x in validate_batch(records, complete_dataset=True)))
        add_repeat(records[0])
        self.assertEqual(validate_batch(records, release=True, complete_dataset=True), [])

    def test_immediate_protocol_passes_without_claiming_repeat_reliability(self):
        records = []
        for index in range(20):
            record = immediate_fixture()
            record.update(case_id=f"case_{index}", annotation_id=f"annotation_{index}")
            records.append(record)
        self.assertEqual(validate_batch(records, release=True, complete_dataset=True), [])
        self.assertTrue(all(record["review_plan"]["reliability_status"] == "reliability_not_measured" for record in records))

    def test_immediate_protocol_requires_explicit_disclosure_and_no_delayed_subset(self):
        changes = [{"reliability_status": "repeat_assessments_collected"}, {"minimum_repeat_delay_days": 7},
                   {"repeat_required": True}, {"repeat_selection_frozen_at": "2026-10-03T18:00:00Z"},
                   {"repeat_strata": ["test_stratum"]}]
        for change in changes:
            record = immediate_fixture()
            record["review_plan"].update(change)
            with self.subTest(change=change):
                self.assertTrue(validate_record(record, release=True))
        record = immediate_fixture()
        del record["review_plan"]["reliability_status"]
        self.assertTrue(any("reliability_status" in error for error in validate_record(record)))

    def test_legacy_implicit_and_explicit_protocols_keep_seven_day_and_selection_gates(self):
        for explicit in (False, True):
            record = fixture()
            if explicit:
                record["review_plan"]["protocol_id"] = "delayed_repeat_v1"
            self.assertEqual(validate_record(record, release=True), [])
            record["review_plan"]["minimum_repeat_delay_days"] = 0
            self.assertTrue(any("below minimum 7" in error for error in validate_record(record, release=True)))
            record["review_plan"]["minimum_repeat_delay_days"] = 7
            record["review_plan"]["repeat_selection_frozen_at"] = None
            self.assertTrue(any("selection not frozen" in error for error in validate_record(record, release=True)))

    def test_immediate_post_proposal_review_is_reconciliation_never_blind_repeat(self):
        record = immediate_fixture()
        later = deepcopy(record["reviews"][0])
        later.update(review_id="review_reconciliation", phase="expert_reconciliation", submitted_at="2026-10-03T14:00:00Z",
                     saw_own_prior_annotation=True, saw_reference_key=True)
        later["submission_sha256"] = review_digest(later)
        record["reviews"].append(later)
        self.assertEqual(validate_record(record, release=True), [])
        later["phase"] = "expert_repeat"
        later["submission_sha256"] = review_digest(later)
        self.assertTrue(any("no independent delayed expert_repeat" in error for error in validate_record(record, release=True)))

    def test_reconciliation_preserves_chronology_and_reasons_for_changed_decisions(self):
        record = immediate_fixture()
        later = deepcopy(record["reviews"][0])
        later.update(review_id="review_reconciliation", phase="expert_reconciliation", submitted_at="2026-10-03T11:00:00Z",
                     saw_own_prior_annotation=True, saw_reference_key=True)
        later["submission_sha256"] = review_digest(later)
        record["reviews"].append(later)
        self.assertTrue(any("reconciliation precedes" in error for error in validate_record(record, release=True)))
        later.update(submitted_at="2026-10-03T14:00:00Z", conclusion="insufficient_evidence",
                     accepted_proof_ids=[], missing_fact_requirements=["Mock missing evidence."])
        later["submission_sha256"] = review_digest(later)
        self.assertTrue(any("recorded resolution" in error for error in validate_record(record, release=True)))
        record["resolution"]["resolutions"] = [{"issue": "Mock changed decision.", "resolution": "Retain original after review.", "rationale": "Software test only."}]
        self.assertEqual(validate_record(record, release=True), [])

    def test_complete_dataset_rejects_mixed_protocols_and_bad_protocol_values(self):
        first, second = immediate_fixture(), fixture()
        first.update(case_id="case_first", annotation_id="annotation_first")
        second.update(case_id="case_second", annotation_id="annotation_second")
        self.assertTrue(any("cannot mix" in error for error in validate_batch([first, second], release=True, complete_dataset=True)))
        for value in ("unknown_protocol", {"protocol": "immediate_reconciliation_v2"}):
            record = immediate_fixture()
            record["review_plan"]["protocol_id"] = value
            with self.subTest(value=value):
                self.assertTrue(validate_batch([record], release=True, complete_dataset=True))

    def test_immediate_protocol_still_requires_qualification_proof_and_source_gates(self):
        record = immediate_fixture()
        record["reviewers"][0]["qualification_verified"] = False
        record["proof_sets"][0]["minimality"]["deletion_tests"][0]["still_sufficient"] = True
        record["sources"][0]["rights_status"] = "unresolved"
        record["resolution"]["gold_sha256"] = gold_digest(record)
        errors = validate_record(record, release=True)
        for expected in ("qualification not verified", "minimality", "rights unresolved"):
            self.assertTrue(any(expected in error for error in errors), errors)

    def test_accepted_proof_cannot_use_inaccessible_late_evidence(self):
        record = fixture()
        record["sources"][0].update(initially_visible=False, obtainable=False, available_at="2026-01-01")
        record["resolution"]["gold_sha256"] = gold_digest(record)
        errors = validate_record(record, release=True)
        self.assertTrue(any("outside the observation interface" in x for x in errors))
        self.assertTrue(any("unavailable by cutoff" in x for x in errors))

    def test_all_proof_authorities_checked_even_if_gold_abstains(self):
        record = fixture()
        add_mock_authority(record)
        record["gold"].update(authority_disposition="no_governing_paragraph", acceptable_citation_sets=[])
        record["authorities"][0]["effective_from"] = "2030-01-01"
        record["resolution"]["gold_sha256"] = gold_digest(record)
        errors = validate_record(record, release=True)
        self.assertTrue(any("non-governing disposition" in x for x in errors))
        self.assertTrue(any("not yet effective" in x for x in errors))

    def test_authority_requires_observed_prerequisites_and_matching_scope(self):
        record = fixture()
        add_mock_authority(record)
        self.assertEqual(validate_record(record, release=True), [])
        extra = deepcopy(record["facts"][0])
        extra["fact_id"] = "fact_extra"
        record["facts"].append(extra)
        record["authorities"][0].update(required_fact_ids=["fact_extra"], jurisdiction=["UK"], entity_scope=["bank"], framework="ifrs")
        record["resolution"]["gold_sha256"] = gold_digest(record)
        errors = validate_record(record, release=True)
        for expected in ("omits required applicability", "jurisdiction does not cover", "entity scope does not cover", "framework does not match"):
            self.assertTrue(any(expected in x for x in errors), errors)

    def test_missing_or_underived_fact_cannot_support_proof(self):
        record = fixture()
        record["facts"][0].update(role="missing_requirement", origin="derived", derivation="")
        record["resolution"]["gold_sha256"] = gold_digest(record)
        errors = validate_record(record, release=True)
        self.assertTrue(any("missing fact as established" in x for x in errors))
        self.assertTrue(any("derivation missing" in x for x in errors))

    def test_insufficiency_and_future_repeat_freeze_are_rejected(self):
        record = fixture()
        record["gold"].update(conclusion="insufficient_evidence", decision_sufficiency="sufficient", missing_fact_requirements=["Missing contract."])
        record["review_plan"]["repeat_selection_frozen_at"] = "2030-01-01T00:00:00Z"
        record["resolution"]["gold_sha256"] = gold_digest(record)
        errors = validate_record(record, release=True)
        self.assertTrue(any("cannot have sufficient" in x for x in errors))
        self.assertTrue(any("frozen after final resolution" in x for x in errors))

    def test_boolean_attestation_cannot_be_integer(self):
        record = fixture()
        record["reviewers"][0]["is_human"] = 1
        self.assertTrue(any("expected type" in x for x in validate_record(record)))

    def test_unresolved_extra_candidates_block_release(self):
        record = fixture()
        add_mock_authority(record)
        record["authorities"][0]["applicability"] = "unresolved"
        extra = deepcopy(record["proof_sets"][0])
        extra["proof_id"] = "proof_unreviewed"
        extra["minimality"]["status"] = "not_reviewed"
        record["proof_sets"].append(extra)
        record["resolution"]["gold_sha256"] = gold_digest(record)
        errors = validate_record(record, release=True)
        self.assertTrue(any("unresolved candidate applicability" in x for x in errors))
        self.assertTrue(any("unreviewed candidate proof" in x for x in errors))

    def test_known_refutations_cannot_be_silently_omitted(self):
        record = fixture()
        add_mock_authority(record)
        contradiction = deepcopy(record["facts"][0])
        contradiction.update(fact_id="fact_refutation", role="refutation")
        record["facts"].append(contradiction)
        record["authorities"][0]["refutation_fact_ids"] = ["fact_refutation"]
        record["resolution"]["gold_sha256"] = gold_digest(record)
        self.assertTrue(any("omits known authority refutations" in x for x in validate_record(record, release=True)))

    def test_packet_uses_only_public_whitelist_and_blank_annotations(self):
        rows = [{"case_id": f"original_{i}", "gold_answer": "SECRET", "metadata": {"company": f"company_{i % 2}", "cik": str(i % 2), "gold_label": "SECRET"},
                 "statement_text": "<script>bad()</script>", "transaction_data": "Synthetic unreviewed evidence."} for i in range(6)]
        packet, private, annotations = build_packet(rows, 4, seed="a" * 64)
        self.assertEqual(len(packet["cases"]), 4)
        self.assertEqual(sorted(case["metadata"]["company"] for case in packet["cases"]), ["company_0", "company_0", "company_1", "company_1"])
        public_text = json.dumps(packet)
        self.assertNotIn("SECRET", public_text)
        self.assertNotIn("original_", public_text)
        self.assertIn("original_", json.dumps(private))
        self.assertTrue(all(not record["reviews"] and record["gold"]["conclusion"] == "unresolved" for record in annotations.values()))
        html = render_html(packet)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_release_gate_blocks_empty_and_missing_case_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            annotations = root / "annotations"
            annotations.mkdir()
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"case_ids": ["case_test"]}))
            report = assess_release(annotations, manifest, complete_dataset=False)
            self.assertFalse(report["release_ready"])
            self.assertTrue(any(item["code"] == "no_annotations" for item in report["blockers"]))
            (annotations / "case.json").write_text(json.dumps(fixture()))
            self.assertTrue(assess_release(annotations, manifest, complete_dataset=False)["release_ready"])
            manifest.write_text(json.dumps({"case_ids": ["case_test", "case_missing"]}))
            self.assertFalse(assess_release(annotations, manifest, complete_dataset=False)["release_ready"])

    def test_release_gate_reports_new_protocol_and_blocks_manifest_relabeling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            annotations = root / "annotations"
            annotations.mkdir()
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"case_ids": ["case_test"], "review_protocol": "immediate_reconciliation_v2"}))
            (annotations / "case.json").write_text(json.dumps(immediate_fixture()))
            report = assess_release(annotations, manifest)
            self.assertTrue(report["release_ready"], report["blockers"])
            self.assertEqual(report["reliability_status"], "reliability_not_measured")
            self.assertFalse(report["repeat_fraction_checked"])
            self.assertTrue(report["complete_dataset_protocol_checked"])
            (annotations / "case.json").write_text(json.dumps(fixture()))
            report = assess_release(annotations, manifest, complete_dataset=False)
            self.assertFalse(report["release_ready"])
            self.assertTrue(any(blocker["code"] == "manifest_review_protocol_mismatch" for blocker in report["blockers"]))
            (annotations / "case.json").write_text(json.dumps(immediate_fixture()))
            manifest.write_text(json.dumps({"case_ids": ["case_test"], "schema_version": "review-pilot-v1"}))
            report = assess_release(annotations, manifest, complete_dataset=False)
            self.assertFalse(report["release_ready"])
            self.assertEqual(report["manifest_review_protocol"], "delayed_repeat_v1")
            self.assertTrue(any(blocker["code"] == "manifest_review_protocol_mismatch" for blocker in report["blockers"]))

    def test_operational_workflow_is_not_publication_gold(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "case.json").write_text(json.dumps({"case_id": "case_test", "status": "reviewed", "reviewers": None}))
            manifest = root / "manifest.data"
            manifest.write_text(json.dumps({"case_ids": ["case_test"]}))
            report = assess_release(root, manifest)
            self.assertFalse(report["release_ready"])
            self.assertEqual(report["records_passing_release_checks"], 0)


if __name__ == "__main__":
    unittest.main()
