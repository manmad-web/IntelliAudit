#!/usr/bin/env python3
"""Build a blind, unreviewed revenue/cutoff annotation pilot without model calls.

The checked-in artifacts are a review queue, never approved benchmark labels.
This builder keeps proposed answers and paired-case provenance curator-only.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = '72da89a9e6400bfd1da9041a742f9cdeb00470bc'
PINNED_SOURCE_SHA256 = {
    'answer_key.jsonl': 'a00a4057184bda6a5c80d6091453b5ff586a956dec9b52871c3a91eafe9a3c23',
    'exam.jsonl': '83f44363450ffa4b53ca7744e6728cd0d75bacb25a7032869b27f4011f2658ce',
}
SEED = 'revenue-cutoff-accountant-pilot-v1'
CANDIDATE_CIKS = (731766, 1334036, 1655210, 100885, 1800, 949870, 51434, 831259)
METADATA_FIELDS = ('company', 'cik', 'fiscal_year', 'statement_type', 'period', 'unit')
CUTOFF_PREFIX = '- Revenue: cut-off review'
REVIEW_STATUS = 'EXPERT_REVIEW_PENDING'


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def rank(namespace: str, value: str) -> str:
    return digest(f'{SEED}|{namespace}|{value}'.encode())


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def jsonl_bytes(rows: list[dict]) -> bytes:
    return ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows).encode()


def remove_cutoff(text: str) -> tuple[str, list[str]]:
    """Remove only revenue cutoff facts, preserving every movement and other fact."""
    lines = text.splitlines()
    removed = [line for line in lines if line.startswith(CUTOFF_PREFIX)]
    if len(removed) != 1:
        raise ValueError('Each selected source must have exactly one revenue cutoff fact')
    # Preserve the section heading too: no extra edit or disclosure of variant kind.
    return '\n'.join(line for line in lines if not line.startswith(CUTOFF_PREFIX)), removed


def build(source: Path = ROOT / 'data/benchmark') -> dict[str, bytes]:
    paths = {name: source / name for name in ('exam.jsonl', 'answer_key.jsonl')}
    raw = {name: path.read_bytes() for name, path in paths.items()}
    hashes = {name: digest(value) for name, value in raw.items()}
    if hashes != PINNED_SOURCE_SHA256:
        raise ValueError('Source bytes differ from the pinned commit inputs; revise and document a new pilot version')
    bundle_hash = digest(json.dumps(hashes, sort_keys=True).encode())
    exams_list = [json.loads(line) for line in raw['exam.jsonl'].splitlines() if line]
    answers_list = [json.loads(line) for line in raw['answer_key.jsonl'].splitlines() if line]
    exams = {row['exam_id']: row for row in exams_list}
    answers = {row['exam_id']: row for row in answers_list}
    if len(exams) != len(exams_list) or len(answers) != len(answers_list) or exams.keys() != answers.keys():
        raise ValueError('Source IDs must be unique and exam/key sets must match')
    eligible: dict[tuple[int, int, str], dict[str, list[str]]] = {}
    for exam_id, exam in exams.items():
        meta, answer = exam['metadata'], answers[exam_id]
        cik, year = int(meta['cik']), int(meta['fiscal_year'])
        if cik not in CANDIDATE_CIKS or not 2020 <= year <= 2024 or meta['statement_type'] != 'IncomeStatement':
            continue
        if sum(line.startswith(CUTOFF_PREFIX) for line in exam['transaction_data'].splitlines()) != 1:
            continue
        category = None
        if answer.get('record_type') == 'control' and answer.get('general_judgement') == 'Correct':
            category = 'source_control'
        elif answer.get('rule_id') == 'R09_revenue_recognition_timing' and answer.get('ground_truth_citations', {}).get('citable') is True:
            category = 'source_revenue_fault'
        if category:
            eligible.setdefault((cik, year, meta['period']), {}).setdefault(category, []).append(exam_id)
    pairs_by_company: dict[int, list[tuple]] = {}
    for base, groups in eligible.items():
        for control_id in groups.get('source_control', []):
            for fault_id in groups.get('source_revenue_fault', []):
                # Match the actual clean base; company/year alone is insufficient.
                if exams[control_id]['statement_text'] == answers[fault_id].get('corrected_statement_text'):
                    pairs_by_company.setdefault(base[0], []).append((*base, control_id, fault_id))
    companies = sorted(pairs_by_company, key=lambda cik: rank('company', str(cik)))[:5]
    if len(companies) != 5:
        raise ValueError(f'Need five eligible companies, found {len(companies)}; do not manufacture cases')
    public, proposals = [], []
    for cik in companies:
        pair = min(pairs_by_company[cik], key=lambda item: rank('base', '|'.join(map(str, item))))
        _, year, period, control_id, fault_id = pair
        pair_group = rank('pair', '|'.join(map(str, pair)))[:24]
        for source_id, category in ((control_id, 'source_control'), (fault_id, 'source_revenue_fault')):
            exam = exams[source_id]
            for withheld in (False, True):
                variant = category + ('_cutoff_withheld' if withheld else '_full')
                exam_id = 'RP-' + rank('public-id', source_id + '|' + variant)[:24]
                transactions, removed = (remove_cutoff(exam['transaction_data']) if withheld else (exam['transaction_data'], []))
                public.append({
                    'exam_id': exam_id,
                    'metadata': {field: exam['metadata'][field] for field in METADATA_FIELDS},
                    'statement_text': exam['statement_text'],
                    'transaction_data': transactions,
                })
                answer = copy.deepcopy(answers[source_id])
                if withheld:
                    answer = {
                        'record_type': 'proposed_evidence_withheld',
                        'general_judgement': 'Insufficient evidence',
                        'error_type': None,
                        'error_identification': None,
                        'ground_truth_citations': {'citable': False, 'asc_full': None, 'asc_topic': None, 'asc_subtopic': None},
                        'proposal_note': 'Candidate only. An accountant must decide whether remaining evidence supports a different judgment; removal does not establish undecidability.',
                    }
                answer['exam_id'] = exam_id
                proposals.append({
                    'exam_id': exam_id, 'answer': answer,
                    'review_status': REVIEW_STATUS, 'accountant_review_completed': False,
                    'source_exam_id': source_id, 'pair_group': pair_group,
                    'company_cluster': str(cik).zfill(10), 'family_cluster': 'revenue_recognition_cutoff',
                    'variant': variant, 'sourcebundlehash': bundle_hash,
                    'source_commit': SOURCE_COMMIT, 'removed_supporting_facts': removed,
                    'counterfactual_validity': 'not_established',
                    'provenance_note': 'Public-company statement figures with synthetic transactions and synthetic error injection; no allegation about the named company.',
                })
    public.sort(key=lambda row: rank('order', row['exam_id']))
    proposals.sort(key=lambda row: row['exam_id'])
    public_bytes, proposal_bytes = jsonl_bytes(public), jsonl_bytes(proposals)
    manifest = {
        'schema_version': 'review-pilot-v1', 'status': REVIEW_STATUS,
        'purpose': 'Blind single-accountant annotation feasibility pilot; not a scored or gold-standard benchmark.',
        'seed': SEED, 'n_cases': len(public), 'n_companies': len(companies),
        'case_ids': [row['exam_id'] for row in public],
        'accountant_reviews_completed': 0, 'source_commit': SOURCE_COMMIT,
        'source_repository': 'https://github.com/manmad-web/IntelliAudit',
        'source_paths': ['data/benchmark/exam.jsonl', 'data/benchmark/answer_key.jsonl'],
        'source_sha256': hashes, 'source_bundle_sha256': bundle_hash,
        'artifact_sha256': {'public_cases.jsonl': digest(public_bytes), 'curator/proposals.jsonl': digest(proposal_bytes)},
        'selection': 'Hash-rank five eligible companies from the fixed eight-company pool, then one FY2020–2024 same-base income-statement control/R09 pair per company; require a revenue-cutoff supporting fact in both.',
        'evidence': 'Synthetic component movements and supporting facts. Company names refer to source financial figures, not real incidents. Unmodified source text may contain residual clues.',
        'withheld_variant_policy': 'Remove only the single revenue cutoff supporting-fact line. Keep all other text, including component movements. Insufficient-evidence proposals require independent review.',
        'pairing_limitations': 'Clean/fault source evidence may differ in multiple lines. These are matched-source review cases, not validated minimal counterfactual pairs. Repeated company/year cases may cue later judgments.',
        'review_policy': 'One accountant; lock initial judgments before exposing any curator proposal or paired mapping. Preserve blind and reconciliation records. Delayed re-review measures intra-reviewer consistency only.',
        'publication_gate': 'Expert review, provenance reconciliation, authority/applicability checks, ambiguity disposition, and immutable split freeze remain pending. Never count proposed labels as reviewed results.',
        'curator_access': 'Source IDs, proposed answers, removed facts, pair groups, and company/family clusters live only in curator/proposals.jsonl; exclude that file from reviewer/model payloads.',
        'licensing': 'No new redistribution license is asserted for inherited source content.',
    }
    return {'public_cases.jsonl': public_bytes, 'curator/proposals.jsonl': proposal_bytes, 'manifest.json': json_bytes(manifest)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/benchmark')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/review_pilot')
    parser.add_argument('--check', action='store_true', help='Rebuild in memory and verify saved bytes; never modify artifacts')
    args = parser.parse_args()
    artifacts = build(args.source)
    if args.check:
        mismatches = [name for name, value in artifacts.items() if not (args.output / name).is_file() or (args.output / name).read_bytes() != value]
        if mismatches:
            raise SystemExit('Rebuild differs: ' + ', '.join(mismatches))
        print('Verified deterministic 20-case, 5-company review pilot; all labels remain unreviewed.')
        return
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit('Refusing to replace a nonempty review directory. Use --check, or select a new --output.')
    for name, value in artifacts.items():
        target = args.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    print(f'Created 20 unreviewed cases for five companies at {args.output}')


if __name__ == '__main__':
    main()
