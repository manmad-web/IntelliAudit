"""Curator comparison retains independent first-pass disagreements."""
from copy import deepcopy
import unittest

from dashboard.agreement import build_comparison


def annotation(**changes):
    return {'judgement': 'incorrect', 'error_type': 'cutoff', 'rows': [2, 1],
            'evidence_sufficiency': 'sufficient', 'authority_disposition': 'governing_paragraph',
            'citations': ['ASC 606-10-25-1', 'ASC 606-10-25-3'],
            'authority_currency': 'verified', 'proof_sets': [['fact:2', 'fact:1'], ['fact:3']],
            'reasoning': 'Independent rationale.', 'confidence': 'high', **changes}


def event(reviewer, case='a', stage='blind', **changes):
    return {'case_id': case, 'reviewer_id': reviewer, 'stage': stage,
            'event_id': reviewer + ':' + case + ':' + stage,
            'reviewer_name': reviewer, 'qualification': 'CPA (self-declared)',
            'annotation': annotation(**changes)}


class AgreementTests(unittest.TestCase):
    def setUp(self):
        self.cases = [{'id': 'a', 'company': 'Example'}, {'id': 'b', 'company': 'Other'}]

    def test_verification_and_repeat_do_not_replace_first_blind_judgment(self):
        records = [event('one'), event('two', judgement='correct'),
                   event('two', stage='verification'), event('two', stage='repeat')]
        report = build_comparison(self.cases, records, [])
        self.assertEqual(report['dispute_queue'], ['a'])
        self.assertEqual(report['cases'][0]['reviews'][1]['annotation']['judgement'], 'correct')
        self.assertEqual(report['agreement']['judgement'],
                         {'compared_pairs': 1, 'agreeing_pairs': 0, 'ratio': 0.0})

    def test_order_only_changes_are_not_disagreements(self):
        records = [event('one'), event('two', rows=[1, 2],
                   citations=['ASC 606-10-25-3', 'ASC 606-10-25-1'],
                   proof_sets=[['fact:3'], ['fact:1', 'fact:2']])]
        report = build_comparison(self.cases, records, [])
        self.assertEqual(report['cases'][0]['status'], 'agreed')
        self.assertTrue(all(metric['ratio'] == 1 for metric in report['agreement'].values()))

    def test_alternative_proof_and_paragraph_labels_remain_visible(self):
        report = build_comparison(self.cases, [event('one'), event('two',
                                  citations=['ASC 606-10-25-7'], proof_sets=[['fact:4']])], [])
        self.assertEqual(report['cases'][0]['differing_fields'], ['citations', 'proof_sets'])

    def test_missing_reviews_do_not_count_as_disagreement_or_agreement(self):
        report = build_comparison(self.cases, [event('one')], [])
        self.assertEqual(report['status_counts']['pending'], 2)
        self.assertEqual(report['agreement']['judgement']['compared_pairs'], 0)
        self.assertIsNone(report['agreement']['judgement']['ratio'])

    def test_three_reviewers_contribute_three_pairs_and_only_first_events(self):
        records = [event('one'), event('two'), event('three', judgement='correct'),
                   event('three')]
        report = build_comparison(self.cases, records, [])
        self.assertEqual(report['reviewer_count'], 3)
        self.assertEqual(report['agreement']['judgement']['compared_pairs'], 3)
        self.assertEqual(report['agreement']['judgement']['agreeing_pairs'], 1)
        self.assertAlmostEqual(report['agreement']['judgement']['ratio'], 1 / 3)

    def test_curator_resolution_preserves_original_disagreement_and_history(self):
        records = [event('one'), event('two', judgement='correct')]
        resolutions = [{'case_id': 'a', 'reason': 'Earlier reasoning.'},
                       {'case_id': 'a', 'reason': 'Additional evidence considered.'}]
        originals = deepcopy((self.cases, records, resolutions))
        report = build_comparison(self.cases, records, resolutions)
        self.assertEqual(report['cases'][0]['status'], 'resolved')
        self.assertEqual(len(report['cases'][0]['adjudications']), 2)
        self.assertEqual(report['cases'][0]['latest_adjudication'], resolutions[-1])
        self.assertEqual(report['agreement']['judgement']['agreeing_pairs'], 0)
        report['cases'][0]['reviews'][0]['annotation']['judgement'] = 'changed'
        self.assertEqual((self.cases, records, resolutions), originals)

    def test_outside_cases_and_nonblind_records_are_ignored(self):
        report = build_comparison(self.cases, [event('one', case='unknown'),
                                  event('two', stage='verification')],
                                  [{'case_id': 'unknown'}])
        self.assertEqual(report['reviewer_count'], 0)
        self.assertEqual(report['declared_qualification_count'], 0)

    def test_partial_old_annotation_is_flagged_and_missing_field_excluded(self):
        partial = event('two')
        partial['annotation'].pop('citations')
        report = build_comparison(self.cases, [event('one'), partial], [])
        self.assertEqual(report['cases'][0]['status'], 'incomplete')
        self.assertEqual(report['cases'][0]['missing_fields'], ['citations'])
        self.assertEqual(report['agreement']['citations']['compared_pairs'], 0)

    def test_duplicate_case_inventory_rejected(self):
        with self.assertRaises(ValueError):
            build_comparison([{'id': 'a'}, {'id': 'a'}], [], [])


if __name__ == '__main__':
    unittest.main()
