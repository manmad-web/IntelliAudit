"""Detect damaged financial packets and keep construction checks below human claims."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import build_expert_review_pilot as v2
from scripts import build_review_pilot as v1
from scripts import check_pilot_quality as quality


class PilotVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = v2.build()
        cls.cases = quality.load_jsonl(v2.ROOT / 'data/review_pilot_v2/public_cases.jsonl')
        cls.private = {p['exam_id']: p for p in quality.load_jsonl(v2.ROOT / 'data/review_pilot_v2/curator/proposals.jsonl')}
        cls.original = {p['exam_id']: p for p in quality.load_jsonl(v2.ROOT / 'data/review_pilot/public_cases.jsonl')}

    def test_new_version_does_not_modify_frozen_legacy(self):
        for name, value in v1.build().items():
            self.assertEqual(v1.canonical_lf_bytes((v2.ROOT / 'data/review_pilot' / name).read_bytes()), value)
        for name, value in self.artifacts.items():
            self.assertEqual(v1.canonical_lf_bytes((v2.ROOT / 'data/review_pilot_v2' / name).read_bytes()), value)

    def test_v2_preserves_all_financial_values_and_substantive_facts(self):
        for case in self.cases:
            private = self.private[case['exam_id']]
            original = self.original[private['source_pilot_case_id']]
            self.assertEqual(case['statement_text'], original['statement_text'])
            self.assertEqual(case['transaction_data'], v2.neutral_transactions(
                original['transaction_data'], original['metadata']['company'], case['metadata']['company']))
            old_facts = [line for line in original['transaction_data'].splitlines() if line.startswith('- ')]
            new_facts = [line for line in case['transaction_data'].splitlines() if line.startswith('- ')]
            self.assertEqual(new_facts, old_facts)
            self.assertEqual(private['answer']['exam_id'], case['exam_id'])

    def test_new_opaque_ids_and_public_metadata_do_not_disclose_source_identity(self):
        self.assertEqual(len(self.cases), 20)
        self.assertEqual({c['metadata']['company'] for c in self.cases}, {f'Company {letter}' for letter in 'ABCDE'})
        for case in self.cases:
            self.assertRegex(case['exam_id'], r'^RP2-[a-f0-9]{24}$')
            self.assertNotIn(case['exam_id'], self.original)
            meta = case['metadata']
            self.assertEqual(set(meta), {'company', 'fiscal_year', 'statement_type', 'period', 'unit',
                                         'currency', 'reporting_date', 'derived_rows'})
            self.assertIsNone(meta['reporting_date'])
            self.assertEqual(meta['currency'], 'USD')
            private = self.private[case['exam_id']]
            payload = json.dumps(case, ensure_ascii=False)
            self.assertNotIn(private['original_metadata']['company'], payload)
            self.assertNotIn(private['original_metadata']['cik'], payload)
            self.assertNotIn(v2.OLD_REVENUE, payload)
            for forbidden in ('source_exam_id', 'pair_group', 'ground_truth_citations', 'source_pilot_case_id', 'original_metadata'):
                self.assertNotIn(forbidden, payload)
            self.assertEqual(meta['fiscal_year'], private['original_metadata']['fiscal_year'])
            self.assertEqual(meta['period'], private['original_metadata']['period'])

    def test_corrupt_legacy_source_is_not_silently_reversioned(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            for name, value in v1.build().items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
            with (source / 'public_cases.jsonl').open('ab') as stream:
                stream.write(b'\n')
            with self.assertRaisesRegex(ValueError, 'Frozen v1'):
                v2.build(source)

    def test_nonempty_output_preserves_existing_review_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'saved.json'
            target.write_text('preserved', encoding='utf-8')
            run = subprocess.run([sys.executable, str(v2.ROOT / 'scripts/build_expert_review_pilot.py'), '--output', directory],
                                 capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('Refusing to replace', run.stderr)
            self.assertEqual(target.read_text(encoding='utf-8'), 'preserved')


class PilotQualityTests(unittest.TestCase):
    def audit_mutation(self, change):
        """Rehash a deliberate mutation so semantic checks must catch it themselves."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for name, value in v2.build().items():
                path = target / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
            cases = quality.load_jsonl(target / 'public_cases.jsonl')
            private = quality.load_jsonl(target / 'curator/proposals.jsonl')
            manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
            change(cases, private, manifest)
            (target / 'public_cases.jsonl').write_bytes(v1.jsonl_bytes(cases))
            (target / 'curator/proposals.jsonl').write_bytes(v1.jsonl_bytes(private))
            for name in manifest['artifact_sha256']:
                manifest['artifact_sha256'][name] = quality.checksum(quality.lf_bytes(target / name))
            (target / 'manifest.json').write_bytes(v1.json_bytes(manifest))
            return quality.audit(directory=target)

    def test_checked_packets_pass_construction_but_cannot_claim_expert_or_source_fidelity(self):
        for directory in ('review_pilot', 'review_pilot_v2'):
            report = quality.audit(directory=v2.ROOT / 'data' / directory)
            self.assertTrue(report['structural_ready'], report['errors'])
            self.assertEqual(report['construction_error_count'], 0)
            self.assertEqual(report['checked_case_count'], 20)
            self.assertEqual(report['checked_company_count'], 5)
            self.assertFalse(report['expert_validated'])
            self.assertFalse(report['publication_ready'])
            self.assertEqual(report['source_accession_fidelity'], 'missing_original_accessions_and_per_fact_periods')
            self.assertIn('domain_validity_and_authority_applicability_require_human_review', report['publication_blockers'])

    def test_v1_cue_is_reported_and_v2_cue_is_removed(self):
        old = quality.audit(directory=v2.ROOT / 'data/review_pilot')
        current = quality.audit(directory=v2.ROOT / 'data/review_pilot_v2')
        self.assertTrue(all(c['recognition_conclusion_cue_present'] for c in old['curator_only_case_findings']))
        self.assertTrue(all(not c['recognition_conclusion_cue_present'] for c in current['curator_only_case_findings']))
        self.assertTrue(all(not c['withholding_establishes_undecidability'] for c in current['curator_only_case_findings']))

    def test_malformed_money_and_duplicate_row_labels_are_rejected(self):
        text = '[Time]: 2024-12-31 [SEP]\n[row 0]: Revenue | $1,000 [SEP]'
        self.assertEqual(quality.parse_statement(text)[0]['value'], 1000)
        for bad in (text.replace('$1,000', '$10,00'), text.replace('$1,000', '($0)'),
                    text.replace('row 0', 'row 1'), text + '\n[row 0]: Expense | ($100) [SEP]'):
            with self.assertRaises(ValueError):
                quality.parse_statement(bad)

    def test_component_sum_and_direction_mismatch_detected_despite_updated_hash(self):
        def change(cases, private, manifest):
            text = cases[0]['transaction_data']
            match = quality.PART.search(text)
            amount = int(match[2].replace(',', ''))
            cases[0]['transaction_data'] = text[:match.start()] + f': {match[1]}{amount + 1:,} ({match[3]})' + text[match.end():]
        report = self.audit_mutation(change)
        self.assertFalse(report['structural_ready'])
        self.assertGreater(report['construction_errors_by_kind'].get('component_arithmetic', 0), 0)

    def test_wrong_units_wrong_source_and_false_reporting_dates_detected(self):
        def change(cases, private, manifest):
            cases[0]['metadata']['unit'] = 'USD dollars'
            cases[1]['metadata']['reporting_date'] = '2025-01-01'
            private[2]['source_exam_id'] = 'unknown-source'
        report = self.audit_mutation(change)
        self.assertFalse(report['structural_ready'])
        self.assertGreater(report['construction_errors_by_kind'].get('source_projection', 0), 0)
        self.assertGreater(report['construction_errors_by_kind'].get('blinding', 0), 0)
        self.assertGreater(report['construction_errors_by_kind'].get('units', 0), 0)

    def test_derived_flags_do_not_invent_individually_reported_rows(self):
        report = self.audit_mutation(lambda cases, private, manifest: cases[0]['metadata'].update(derived_rows=[0]))
        self.assertFalse(report['structural_ready'])
        self.assertTrue(any('Derived-row' in error['message'] for error in report['errors']))

    def test_original_identity_or_recognition_claim_cannot_reenter_v2_packet(self):
        def change(cases, private, manifest):
            cases[0]['transaction_data'] = cases[0]['transaction_data'].replace(v2.NEW_REVENUE, v2.OLD_REVENUE)
        report = self.audit_mutation(change)
        self.assertFalse(report['structural_ready'])
        self.assertGreater(report['construction_errors_by_kind'].get('blinding', 0), 0)

    def test_cli_default_summary_excludes_private_pairings_and_original_identity(self):
        run = subprocess.run([sys.executable, str(v2.ROOT / 'scripts/check_pilot_quality.py'),
                              '--pilot', str(v2.ROOT / 'data/review_pilot_v2')], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        report = json.loads(run.stdout)
        self.assertFalse(any(key.startswith('curator_only_') for key in report))
        self.assertNotIn('source_exam_id', run.stdout)
        self.assertNotIn('source_revenue_fault', run.stdout)
        self.assertNotIn('UnitedHealth', run.stdout)


if __name__ == '__main__':
    unittest.main()
