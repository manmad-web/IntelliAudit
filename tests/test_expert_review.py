"""Expert-facing projection and optional first-assessment fields.

These are mechanical software checks, not expert accounting approval.
"""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

from dashboard.presentation import build_presentation
from dashboard.review_store import ReviewStore, validate_annotation
from dashboard.server import BlindDataset, Store

ROOT = Path(__file__).resolve().parents[1]


def initial_annotation():
    return {'judgement': 'ambiguous', 'error_type': None, 'rows': [],
            'evidence_sufficiency': 'uncertain', 'authority_disposition': 'unresolved',
            'citations': [], 'authority_currency': 'unresolved', 'authority_source': '',
            'proof_sets': [], 'reasoning': 'The source statement and synthetic summaries need clarification.',
            'confidence': 'low', 'supporting_evidence': [],
            'missing_information': 'Original contract and evidence of control transfer.',
            'case_quality_flags': ['source_unclear', 'evidence_unclear'],
            'case_quality_notes': 'Cannot verify the original filing accession.',
            'alternative_treatments': '', 'contradictions': ''}


class ExpertProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = BlindDataset(Store(ROOT), 'pilot-v2')

    def test_all_twenty_packets_have_exact_rows_and_evidence_traceability(self):
        self.assertEqual(len(self.dataset.entries), 20)
        self.assertEqual(set(self.dataset.facets['company']), {f'Company {letter}' for letter in 'ABCDE'})
        for entry in self.dataset.entries:
            detail = self.dataset.detail(entry['id'])
            view = detail['presentation']
            raw_units = {unit['id']: unit['text'] for unit in detail['evidence_units']}
            raw_labels = {int(row) for row in re.findall(r'\[row (\d+)\]', detail['exam']['statement_text'])}
            self.assertEqual({row['row'] for row in view['statement_rows']}, raw_labels)
            self.assertEqual(len(view['statement_rows']), len(raw_labels))
            self.assertFalse(view['presentation_warnings'])
            self.assertEqual(view['framework'], 'US GAAP')
            self.assertEqual(view['unit'], 'USD millions')
            self.assertEqual(view['currency'], 'USD')
            self.assertIsNone(view['reporting_date'])
            for row in view['statement_rows']:
                self.assertIn(row['unit_id'], raw_units)
                self.assertIn(row['amount'], raw_units[row['unit_id']])
            self.assertEqual({unit['id'] for unit in view['evidence']}, set(raw_units))
            self.assertEqual(len({unit['stable_id'] for unit in view['evidence']}), len(raw_units))
            self.assertTrue(any(unit['category'] == 'movement' for unit in view['evidence']))
            self.assertTrue(any(row['derived'] for row in view['statement_rows']))
            self.assertEqual(self.dataset.detail(entry['id'])['presentation'], view)

    def test_public_packet_contains_no_private_construction_or_original_identity(self):
        original = json.loads((ROOT / 'data/review_pilot_v2/curator/quality_report.json').read_text())
        names = [row['company'] for row in original['curator_only_base_inventory']]
        for entry in self.dataset.entries:
            detail = self.dataset.detail(entry['id'])
            payload = json.dumps(detail)
            self.assertNotIn('cik', detail['exam']['metadata'])
            for key in ('source_exam_id', 'source_pilot_case_id', 'pair_group', 'variant', 'ground_truth_citations', 'answer'):
                self.assertNotIn('"' + key + '"', payload)
            for name in names:
                self.assertNotIn(name, payload)
            self.assertNotIn('revenue recognised on satisfied performance obligations', payload)

    def test_statement_parser_does_not_silently_discard_unrecognized_information(self):
        exam = {'metadata': {'unit': 'USD millions'}, 'statement_text': 'Unlabeled special adjustment'}
        units = [{'id': 'statement:L0001', 'source': 'statement', 'text': exam['statement_text']}]
        view = build_presentation(exam, units)
        self.assertTrue(view['presentation_warnings'])
        self.assertEqual(view['evidence'][0]['text'], exam['statement_text'])

    def test_case_curation_context_is_distinct_from_public_packet(self):
        private = self.dataset.curator_detail(self.dataset.entries[0]['id'])
        self.assertIn('original_metadata', private['source_context'])
        self.assertIn('original_company', private['quality'])
        self.assertFalse(self.dataset.quality()['publication_ready'])

    def test_simplified_first_assessment_accepts_unresolved_authority_and_missing_information(self):
        detail = self.dataset.detail(self.dataset.entries[0]['id'])
        annotation = initial_annotation()
        annotation['supporting_evidence'] = [detail['evidence_units'][0]['id']]
        self.assertEqual(validate_annotation(annotation, detail, 'blind'), annotation)
        self.assertEqual(annotation['proof_sets'], [])

    def test_optional_assessment_fields_reject_unknown_units_flags_and_unbounded_text(self):
        detail = self.dataset.detail(self.dataset.entries[0]['id'])
        for field, value in [('supporting_evidence', ['fabricated:invoice']),
                             ('supporting_evidence', [detail['evidence_units'][0]['id']] * 2),
                             ('case_quality_flags', ['expert_approved']),
                             ('case_quality_flags', ['other', 'other']),
                             ('missing_information', 'x' * 10001),
                             ('contradictions', 123)]:
            annotation = copy.deepcopy(initial_annotation())
            annotation[field] = value
            with self.subTest(field=field, value_type=type(value).__name__), self.assertRaises(ValueError):
                validate_annotation(annotation, detail, 'blind')

    def test_reopening_an_available_proposal_preserves_its_first_exposure_record(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReviewStore(Path(directory) / 'qa.sqlite3')
            store.register_protocol('pilot-v2', self.dataset.fingerprint, self.dataset.entries)
            scope = {'dataset': 'pilot-v2', 'fingerprint': self.dataset.fingerprint, 'reviewer_id': 'synthetic_qa'}
            for entry in self.dataset.entries:
                store.append({**scope, 'case_id': entry['id']}, 'blind', 'QA only', 'Software test only', initial_annotation())
            case_scope = {**scope, 'case_id': self.dataset.entries[0]['id']}
            first = store.append(case_scope, 'reveal')
            second = store.append(case_scope, 'reveal')
            self.assertEqual(first, second)
            reveals = [event for event in store.history(case_scope)['events'] if event['stage'] == 'reveal']
            self.assertEqual(len(reveals), 1)


if __name__ == '__main__':
    unittest.main()
