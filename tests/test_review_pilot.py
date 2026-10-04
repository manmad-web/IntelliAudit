"""Review-boundary, withholding, pairing, and reproducibility safeguards."""
import collections
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from scripts import build_review_pilot as pilot


class ReviewPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = pilot.build()
        cls.public = [json.loads(line) for line in cls.artifacts['public_cases.jsonl'].splitlines()]
        cls.proposals = [json.loads(line) for line in cls.artifacts['curator/proposals.jsonl'].splitlines()]
        cls.manifest = json.loads(cls.artifacts['manifest.json'])
        cls.exams = {r['exam_id']: r for r in map(json.loads, (pilot.ROOT / 'data/benchmark/exam.jsonl').read_text().splitlines())}

    def test_public_payload_has_only_observable_fields(self):
        source_ids = set(self.exams)
        for case in self.public:
            self.assertEqual(set(case), {'exam_id', 'metadata', 'statement_text', 'transaction_data'})
            self.assertEqual(set(case['metadata']), set(pilot.METADATA_FIELDS))
            self.assertRegex(case['exam_id'], r'^RP-[0-9a-f]{24}$')
            self.assertNotIn(case['exam_id'], source_ids)
            serialized = json.dumps(case)
            for forbidden in ('source_exam_id', 'rule_id', 'corrected_statement_text', 'ground_truth_citations', 'pair_group', 'EXPERT_REVIEW_PENDING'):
                self.assertNotIn(forbidden, serialized)

    def test_twenty_cases_five_companies_unreviewed(self):
        self.assertEqual(len(self.public), 20)
        self.assertEqual(len({r['exam_id'] for r in self.public}), 20)
        self.assertEqual(set(collections.Counter(r['metadata']['cik'] for r in self.public).values()), {4})
        self.assertEqual(len({r['metadata']['cik'] for r in self.public}), 5)
        self.assertEqual(self.manifest['case_ids'], [r['exam_id'] for r in self.public])
        self.assertEqual(self.manifest['accountant_reviews_completed'], 0)
        for proposal in self.proposals:
            self.assertEqual(proposal['review_status'], 'EXPERT_REVIEW_PENDING')
            self.assertFalse(proposal['accountant_review_completed'])
            self.assertEqual(proposal['counterfactual_validity'], 'not_established')

    def test_withholding_removes_exactly_cutoff_fact_and_nothing_else(self):
        public = {r['exam_id']: r for r in self.public}
        for proposal in self.proposals:
            case, source = public[proposal['exam_id']], self.exams[proposal['source_exam_id']]
            self.assertEqual(case['statement_text'], source['statement_text'])
            if proposal['variant'].endswith('_withheld'):
                expected = '\n'.join(line for line in source['transaction_data'].splitlines() if not line.startswith(pilot.CUTOFF_PREFIX))
                self.assertEqual(case['transaction_data'], expected)
                self.assertEqual(len(proposal['removed_supporting_facts']), 1)
                self.assertEqual(proposal['answer']['general_judgement'], 'Insufficient evidence')
                self.assertIn('Candidate only', proposal['answer']['proposal_note'])
            else:
                self.assertEqual(case['transaction_data'], source['transaction_data'])
            self.assertTrue(any(line.startswith('[') for line in case['transaction_data'].splitlines()))

    def test_pair_groups_share_clean_base_and_metadata(self):
        groups = collections.defaultdict(list)
        for row in self.proposals:
            groups[row['pair_group']].append(row)
        self.assertEqual(len(groups), 5)
        for rows in groups.values():
            self.assertEqual(len(rows), 4)
            originals = [r for r in rows if r['variant'].endswith('_full')]
            control = next(r for r in originals if r['variant'].startswith('source_control'))
            fault = next(r for r in originals if r['variant'].startswith('source_revenue_fault'))
            self.assertEqual(self.exams[control['source_exam_id']]['statement_text'], fault['answer']['corrected_statement_text'])
            self.assertEqual(self.exams[control['source_exam_id']]['metadata'], self.exams[fault['source_exam_id']]['metadata'])

    def test_rebuild_matches_checked_in_bytes_and_manifest_hashes(self):
        for name, value in self.artifacts.items():
            self.assertEqual((pilot.ROOT / 'data/review_pilot' / name).read_bytes(), value)
        for name, checksum in self.manifest['artifact_sha256'].items():
            self.assertEqual(pilot.digest(self.artifacts[name]), checksum)

    def test_unpinned_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('exam.jsonl', 'answer_key.jsonl'):
                (Path(directory) / name).write_text('{}\n')
            with self.assertRaisesRegex(ValueError, 'pinned commit'):
                pilot.build(Path(directory))

    def test_nonempty_destination_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / 'saved-review.json'
            sentinel.write_text('preserve accountant work')
            result = subprocess.run([sys.executable, str(pilot.ROOT / 'scripts/build_review_pilot.py'), '--output', directory], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Refusing to replace', result.stderr)
            self.assertEqual(sentinel.read_text(), 'preserve accountant work')

    def test_ambiguous_or_missing_cutoff_fact_rejected(self):
        with self.assertRaises(ValueError):
            pilot.remove_cutoff('[Revenue] +10')
        with self.assertRaises(ValueError):
            pilot.remove_cutoff(pilot.CUTOFF_PREFIX + ' one\n' + pilot.CUTOFF_PREFIX + ' two')


if __name__ == '__main__':
    unittest.main()
