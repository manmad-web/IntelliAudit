"""Descriptive comparisons of preserved first assessments, for curators only.

These counts neither authenticate qualifications nor establish accounting gold.
The server must authorize the curator and scope input records to one dataset and
fingerprint before calling this helper.
"""
from copy import deepcopy
from itertools import combinations
import json


FIELDS = (
    'judgement', 'error_type', 'rows', 'evidence_sufficiency',
    'authority_disposition', 'citations', 'authority_currency', 'proof_sets',
)


def _comparison_value(field, value):
    """Ignore selection order, but never infer citation or proof equivalence."""
    if field in {'rows', 'citations'} and isinstance(value, list):
        value = sorted(value, key=lambda item: json.dumps(item, sort_keys=True))
    elif field == 'proof_sets' and isinstance(value, list):
        proofs = [sorted(proof, key=lambda item: json.dumps(item, sort_keys=True))
                  if isinstance(proof, list) else proof for proof in value]
        value = sorted(proofs, key=lambda item: json.dumps(item, sort_keys=True))
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def build_comparison(cases, events, adjudications):
    """Compare one first blind event per reviewer/case in append order.

    Repeats and post-reveal verification never replace initial assessments.
    Each case contributes every reviewer pair; correlated pairs and repeated
    company cases must not be treated as independent statistical observations.
    """
    output, by_case = [], {}
    for source in cases:
        case_id = source.get('id', source.get('exam_id'))
        if not isinstance(case_id, str) or not case_id or case_id in by_case:
            raise ValueError('Comparison requires distinct case IDs')
        row = {key: deepcopy(source[key]) for key in
               ('company', 'fiscal_year', 'statement_type', 'period') if key in source}
        row.update(id=case_id, reviews=[], adjudications=[])
        by_case[case_id] = row
        output.append(row)

    seen, reviewers, declared = set(), set(), set()
    for event in events:
        case_id, reviewer_id = event.get('case_id'), event.get('reviewer_id')
        if (event.get('stage') != 'blind' or case_id not in by_case or
                not isinstance(reviewer_id, str) or not reviewer_id or
                not isinstance(event.get('annotation'), dict)):
            continue
        key = (case_id, reviewer_id)
        if key in seen:
            continue
        seen.add(key)
        reviewers.add(reviewer_id)
        if isinstance(event.get('qualification'), str) and event['qualification'].strip():
            declared.add(reviewer_id)
        by_case[case_id]['reviews'].append(deepcopy(event))
    for record in adjudications:
        if record.get('case_id') in by_case:
            by_case[record['case_id']]['adjudications'].append(deepcopy(record))

    agreement = {field: {'compared_pairs': 0, 'agreeing_pairs': 0, 'ratio': None}
                 for field in FIELDS}
    counts = {status: 0 for status in ('pending', 'incomplete', 'disputed', 'agreed', 'resolved')}
    for row in output:
        annotations = [event['annotation'] for event in row['reviews']]
        row['review_count'] = len(annotations)
        row['differing_fields'] = []
        row['missing_fields'] = sorted({field for annotation in annotations
                                        for field in FIELDS if field not in annotation})
        for field in FIELDS:
            values = [_comparison_value(field, annotation[field])
                      for annotation in annotations if field in annotation]
            if len(set(values)) > 1:
                row['differing_fields'].append(field)
            for left, right in combinations(values, 2):
                agreement[field]['compared_pairs'] += 1
                agreement[field]['agreeing_pairs'] += left == right
        row['latest_adjudication'] = row['adjudications'][-1] if row['adjudications'] else None
        row['status'] = ('resolved' if row['latest_adjudication'] else
                         'pending' if len(annotations) < 2 else
                         'incomplete' if row['missing_fields'] else
                         'disputed' if row['differing_fields'] else 'agreed')
        counts[row['status']] += 1
    for metric in agreement.values():
        if metric['compared_pairs']:
            metric['ratio'] = metric['agreeing_pairs'] / metric['compared_pairs']
    return {
        'cases': output,
        'dispute_queue': [row['id'] for row in output if row['status'] in {'disputed', 'incomplete'}],
        'case_count': len(output), 'reviewer_count': len(reviewers),
        'declared_qualification_count': len(declared), 'status_counts': counts,
        'agreement': agreement,
        'caveats': [
            'Counts compare preserved first blind assessments only; repeats and reconciliation are separate.',
            'Qualifications are self-declared. These counts do not verify credentials, independence or accounting correctness.',
            'Rows, citation selections and proof-family selections ignore ordering. Distinct paragraph labels and alternative proofs are not inferred to be equivalent.',
            'Ratios are descriptive raw pair agreement, not chance-corrected agreement or independent statistical evidence.',
            'A curator resolution preserves disagreement; it does not establish expert-validated publication gold.',
        ],
    }
