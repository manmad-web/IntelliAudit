#!/usr/bin/env python3
"""Check pilot construction deterministically without certifying accounting validity.

Full findings contain source IDs, variant relationships, and construction details.
They are curator material and must never be sent in a blind case response.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROW = re.compile(r'^\[row (\d+)\]: (.+?) \| (\$[\d,]+|\(\$[\d,]+\)) \[SEP\]$')
PART = re.compile(r': ([+−-])([\d,]+) \((increase|decrease)\)')
CUTOFF = '- Revenue: cut-off review'
LEAKING_REVENUE_PHRASE = 'revenue recognised on satisfied performance obligations'
NEUTRAL_REVENUE_PHRASE = 'credits posted to the revenue account'


def lf_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b'\r\n', b'\n')


def checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in lf_bytes(path).splitlines() if line.strip()]


def render_rows(statement: dict) -> str:
    lines = [f"[Time]: {statement['period']} [SEP]"]
    for row in statement['rows']:
        value = row['value']
        amount = f'(${abs(value):,})' if value < 0 else f'${value:,}'
        lines.append(f"[row {row['idx']}]: {row['label']} | {amount} [SEP]")
    return '\n'.join(lines)


def parse_statement(text: str) -> list[dict]:
    """Reject ambiguous signs, grouping, skipped/duplicate rows, and damaged text."""
    lines = text.splitlines()
    if not lines or not re.fullmatch(r'\[Time\]: \d{4}-\d{2}-\d{2} \[SEP\]', lines[0]):
        raise ValueError('Statement reporting-date header is missing or malformed')
    date.fromisoformat(lines[0][8:18])
    rows = []
    for line in lines[1:]:
        match = ROW.fullmatch(line)
        if not match:
            raise ValueError('Statement row does not have a readable label and money value')
        index, label, amount = match.groups()
        negative = amount.startswith('(')
        digits = amount[2:-1] if negative else amount[1:]
        value = int(digits.replace(',', ''))
        if digits != f'{value:,}' or (negative and value == 0):
            raise ValueError('Statement value has noncanonical grouping or negative zero')
        rows.append({'idx': int(index), 'label': label, 'value': -value if negative else value})
    if not rows or [r['idx'] for r in rows] != list(range(len(rows))):
        raise ValueError('Statement row labels must be distinct and consecutive')
    if len({r['label'] for r in rows}) != len(rows):
        raise ValueError('Income-statement captions must be unambiguous')
    return rows


def expected_rows(base: dict, source_answer: dict) -> dict:
    """Reproduce only the declared numerical edit and dependent subtotal chain."""
    shown = copy.deepcopy(base)
    if source_answer.get('record_type') == 'control':
        return shown
    detail = source_answer.get('injection_detail', {})
    row = next((r for r in shown['rows'] if r.get('concept') == detail.get('row_concept')
                and r.get('label') == detail.get('row_label')), None)
    if row is None or row['value'] != detail.get('original_value'):
        raise ValueError('Declared injection does not identify its original reconstructed row')
    if type(detail.get('erroneous_value')) is not int:
        raise ValueError('Declared injection value is not an integer in the packet units')
    row['value'] = detail['erroneous_value']
    by_index = {r['idx']: r for r in shown['rows']}
    for subtotal in shown['rows']:
        if subtotal.get('sums'):
            subtotal['value'] = sum(by_index[index]['value'] for index in subtotal['sums'])
    return shown


def check_components(text: str, rows: list[dict]) -> tuple[int, list[str]]:
    by_label = {r['label']: r['value'] for r in rows}
    count, errors, seen = 0, [], set()
    for line in text.splitlines():
        if not line.startswith('['):
            continue
        match = re.match(r'^\[([^]]+)\] ', line)
        if not match or match[1] not in by_label or match[1] in seen:
            errors.append('Component evidence has an unknown or duplicate statement caption')
            continue
        label = match[1]
        seen.add(label)
        parts = PART.findall(line)
        if len(parts) != 2:
            errors.append('Component evidence must contain two readable signed amounts')
            continue
        values = []
        for sign, digits, direction in parts:
            value = int(digits.replace(',', ''))
            if value <= 0 or digits != f'{value:,}':
                errors.append('Component evidence amount has invalid grouping or zero magnitude')
            if (sign == '+') != (direction == 'increase'):
                errors.append('Component evidence sign contradicts its direction word')
            values.append(value if sign == '+' else -value)
        if sum(values) != by_label[label]:
            errors.append('Signed component evidence does not reconcile to its displayed row')
        count += 1
    if not count:
        errors.append('No readable component evidence is present')
    return count, errors


def audit(root: Path = ROOT, directory: Path | None = None) -> dict:
    root = Path(root)
    directory = Path(directory) if directory else root / 'data/review_pilot'
    manifest = json.loads(lf_bytes(directory / 'manifest.json'))
    cases = load_jsonl(directory / 'public_cases.jsonl')
    proposals = load_jsonl(directory / 'curator/proposals.jsonl')
    source_exams = load_jsonl(root / 'data/benchmark/exam.jsonl')
    source_answers = load_jsonl(root / 'data/benchmark/answer_key.jsonl')
    exams = {r['exam_id']: r for r in source_exams}
    answers = {r['exam_id']: r for r in source_answers}
    private = {r['exam_id']: r for r in proposals}
    errors = []

    def error(kind: str, message: str, case_id: str | None = None) -> None:
        errors.append({'kind': kind, 'case_id': case_id, 'message': message})

    if manifest.get('schema_version') not in ('review-pilot-v1', 'review-pilot-v2'):
        error('format', 'Unsupported pilot version; explicitly revise this construction checker')
    if len(exams) != len(source_exams) or len(answers) != len(source_answers) or exams.keys() != answers.keys():
        error('source_projection', 'Pinned exam/key source IDs are duplicate or unmatched')
    ids = [c.get('exam_id') for c in cases]
    if len(ids) != len(set(ids)) or len(private) != len(proposals) or set(ids) != set(private):
        error('format', 'Public and curator IDs must be unique and match')
    if ids != manifest.get('case_ids') or len(cases) != manifest.get('n_cases'):
        error('integrity', 'Manifest case order or count differs from the packet')
    if len(cases) != 20 or len({c.get('metadata', {}).get('company') for c in cases}) != 5:
        error('inventory', 'This feasibility pilot requires 20 cases across five companies')
    if set(manifest.get('artifact_sha256', {})) != {'public_cases.jsonl', 'curator/proposals.jsonl'}:
        error('integrity', 'Manifest must contain both public and curator artifact digests')
    if set(manifest.get('source_sha256', {})) != {'exam.jsonl', 'answer_key.jsonl'}:
        error('integrity', 'Manifest must contain both pinned benchmark source digests')
    for name, value in manifest.get('artifact_sha256', {}).items():
        if name not in ('public_cases.jsonl', 'curator/proposals.jsonl'):
            error('integrity', 'Unknown manifest artifact path')
        elif checksum(lf_bytes(directory / name)) != value:
            error('integrity', 'Packet artifact does not match its manifest digest')
    for name, value in manifest.get('source_sha256', {}).items():
        if name not in ('exam.jsonl', 'answer_key.jsonl'):
            error('integrity', 'Unknown manifest source path')
        elif checksum(lf_bytes(root / 'data/benchmark' / name)) != value:
            error('integrity', 'Source artifact does not match its pinned digest')

    findings, base_inventory, pair_groups = [], {}, defaultdict(list)
    for case in cases:
        case_id = case.get('exam_id')
        proposal = private.get(case_id, {})
        source = exams.get(proposal.get('source_exam_id'))
        if source is None:
            error('source_projection', 'Curator source ID is absent from pinned inputs', case_id)
            continue
        visible_meta = case.get('metadata', {})
        version_two = manifest.get('schema_version') == 'review-pilot-v2'
        meta = proposal.get('original_metadata', {}) if version_two else visible_meta
        if meta != source.get('metadata'):
            error('source_projection', 'Company, year, period, units, or statement type changed from the source', case_id)
        if version_two:
            expected_meta = {field: meta.get(field) for field in ('fiscal_year', 'statement_type', 'period', 'unit')}
            expected_meta.update({'company': proposal.get('blind_company_alias'), 'reporting_date': None,
                                  'currency': 'USD', 'derived_rows': visible_meta.get('derived_rows')})
            if visible_meta != expected_meta or not re.fullmatch(r'Company [A-E]', str(visible_meta.get('company', ''))):
                error('blinding', 'V2 public metadata must preserve known dates/units and use only its documented company alias', case_id)
        if meta.get('unit') != 'USD millions' or meta.get('statement_type') != 'IncomeStatement' or visible_meta.get('unit') != 'USD millions':
            error('units', 'Pilot requires income statements with explicit USD millions', case_id)
        if not re.fullmatch(r'\d{10}', str(meta.get('cik', ''))) or type(meta.get('fiscal_year')) is not int:
            error('format', 'Company CIK or fiscal year is malformed', case_id)
            continue
        base_path = root / 'data/clean' / f"{int(meta['cik'])}_{meta['fiscal_year']}_IS.json"
        try:
            base = json.loads(lf_bytes(base_path))
            shown = expected_rows(base, answers[source['exam_id']])
        except (OSError, ValueError, KeyError, StopIteration) as exc:
            error('source_projection', str(exc), case_id)
            continue
        if {field: base.get(field) for field in meta} != meta:
            error('source_projection', 'Reconstructed base metadata differs from the packet', case_id)
        if version_two:
            if visible_meta.get('derived_rows') != [r['idx'] for r in base['rows'] if r.get('residual')]:
                error('source_projection', 'Derived-row flags differ from the preserved reconstructed base', case_id)
            if checksum(lf_bytes(base_path)) != proposal.get('source_clean_sha256'):
                error('integrity', 'Reconstructed base differs from its curator digest', case_id)
        if case.get('statement_text') != source.get('statement_text') or case.get('statement_text') != render_rows(shown):
            error('source_projection', 'Shown rows differ from the pinned source and declared synthetic edit', case_id)
        try:
            rows = parse_statement(case.get('statement_text', ''))
            if case['statement_text'].splitlines()[0] != f"[Time]: {meta.get('period')} [SEP]":
                error('format', 'Displayed reporting date differs from metadata', case_id)
            count, component_errors = check_components(case.get('transaction_data', ''), rows)
            for message in component_errors:
                error('component_arithmetic', message, case_id)
            by_index = {r['idx']: r for r in rows}
            for subtotal in shown['rows']:
                if subtotal.get('sums') and by_index[subtotal['idx']]['value'] != sum(by_index[i]['value'] for i in subtotal['sums']):
                    error('statement_arithmetic', 'Displayed subtotal does not foot to its declared children', case_id)
        except (ValueError, KeyError) as exc:
            count = 0
            error('format', str(exc), case_id)

        withheld = proposal.get('variant', '').endswith('_withheld')
        expected_text = source.get('transaction_data', '')
        removed = [line for line in expected_text.splitlines() if line.startswith(CUTOFF)]
        if withheld:
            expected_text = '\n'.join(line for line in expected_text.splitlines() if not line.startswith(CUTOFF))
            if len(removed) != 1 or removed != proposal.get('removed_supporting_facts'):
                error('source_projection', 'Withheld construction must remove precisely its documented cutoff fact', case_id)
            if proposal.get('answer', {}).get('record_type') != 'proposed_evidence_withheld' or 'Candidate only' not in proposal.get('answer', {}).get('proposal_note', ''):
                error('source_projection', 'Withheld proposal must remain a documented unvalidated construction candidate', case_id)
        elif proposal.get('removed_supporting_facts'):
            error('source_projection', 'Full packet incorrectly records a withheld fact', case_id)
        if not withheld:
            expected_answer = copy.deepcopy(answers[source['exam_id']])
            expected_answer['exam_id'] = case_id
            if proposal.get('answer') != expected_answer:
                error('source_projection', 'Full curator proposal differs from its preserved source answer', case_id)
        # A newly versioned neutral packet may replace this one inherited conclusion cue.
        if version_two:
            expected_text = expected_text.replace(f"Transaction evidence — {meta['company']} FY",
                                                  f"Transaction evidence — {visible_meta.get('company')} FY", 1)
            expected_text = expected_text.replace(LEAKING_REVENUE_PHRASE, NEUTRAL_REVENUE_PHRASE)
        if case.get('transaction_data') != expected_text:
            error('source_projection', 'Evidence differs from the declared source/withholding/neutral wording transformation', case_id)
        if re.search(r'\b(?:ASC|IAS|IFRS)\b', case.get('transaction_data', '')):
            error('blinding', 'Transaction narrative exposes a proposed authority identifier', case_id)
        if version_two:
            serialized = json.dumps(case, ensure_ascii=False)
            if LEAKING_REVENUE_PHRASE in serialized or meta['company'] in serialized or meta['cik'] in serialized:
                error('blinding', 'V2 packet exposes an original identity or inherited recognition conclusion cue', case_id)
        if proposal.get('accountant_review_completed') is not False:
            error('status', 'Construction cannot claim completed accountant review', case_id)
        if proposal.get('counterfactual_validity') != 'not_established':
            error('status', 'Construction cannot establish counterfactual validity automatically', case_id)
        residuals = [{'row': r['idx'], 'label': r['label'], 'value': r['value'],
                      'origin': 'derived_residual_not_individually_reported_fact'}
                     for r in base['rows'] if r.get('residual')]
        base_key = f"{meta['cik']}:{meta['fiscal_year']}:{meta['period']}"
        base_inventory[base_key] = {'company': meta['company'], 'cik': meta['cik'],
                                   'fiscal_year': meta['fiscal_year'], 'unit': meta['unit'],
                                   'residual_rows': residuals,
                                   'original_accession': base.get('accn'),
                                   'source_period_start': base.get('period_start'),
                                   'original_filing_fidelity': 'not_established'}
        pair_groups[proposal.get('pair_group')].append(case_id)
        findings.append({'case_id': case_id, 'source_exam_id': source['exam_id'],
                         'original_company': meta['company'], 'original_cik': meta['cik'],
                         'fiscal_year': meta['fiscal_year'], 'period_end': meta['period'], 'units': meta['unit'],
                         'source_commit': proposal.get('source_commit'),
                         'source_bundle_sha256': proposal.get('sourcebundlehash'),
                         'source_clean_sha256': checksum(lf_bytes(base_path)),
                         'original_accession': None, 'original_reporting_date': None,
                         'derived_residual_rows': residuals,
                         'variant': proposal.get('variant'), 'pair_group': proposal.get('pair_group'),
                         'component_lines_checked': count,
                         'recognition_conclusion_cue_present': LEAKING_REVENUE_PHRASE in case.get('transaction_data', ''),
                         'withholding_establishes_undecidability': False,
                         'remaining_evidence_requires_accounting_review': True,
                         'original_source_fidelity': 'not_established'})
    if len(pair_groups) != 5 or any(len(ids) != 4 for ids in pair_groups.values()):
        error('inventory', 'Curator pair inventory must contain five groups of four related variants')
    counts = Counter(e['kind'] for e in errors)
    return {
        'schema_version': 'pilot-quality-check-v1', 'pilot_schema_version': manifest.get('schema_version'),
        'structural_ready': not errors, 'expert_validated': False, 'publication_ready': False,
        'checked_case_count': len(cases), 'checked_company_count': len(base_inventory),
        'construction_error_count': len(errors), 'construction_errors_by_kind': dict(sorted(counts.items())),
        'construction_checks': {name: 'failed' if counts.get(name) else 'passed'
                                for name in ('format', 'units', 'integrity', 'source_projection',
                                             'statement_arithmetic', 'component_arithmetic', 'inventory', 'blinding', 'status')},
        'source_accession_fidelity': 'missing_original_accessions_and_per_fact_periods',
        'publication_blockers': ['missing_original_filing_accessions_and_per_fact_periods',
                                 'reviewer_qualification_not_independently_verified',
                                 'domain_validity_and_authority_applicability_require_human_review'],
        'human_review_requirements': [
            'Reconcile each SEC-derived value to original accession, period, unit, and filing locator before source-grounded release.',
            'Review constructed residuals and synthetic narratives; packet is not an unmodified annual report or authentic ledger.',
            'Decide sufficiency of remaining evidence independently; withholding alone does not establish ambiguity or undecidability.',
            'Check applicable authority, scope, effective dates, exceptions, citations, and alternative proofs using permitted sources.',
            'Assess recognition cues, repeated variants, prior exposure, and company dependence before interpreting review agreement.',
        ],
        'errors': errors, 'curator_only_case_findings': findings,
        'curator_only_variant_counts': dict(sorted(Counter(p.get('variant', 'unknown') for p in proposals).items())),
        'curator_only_base_inventory': [base_inventory[key] for key in sorted(base_inventory)],
        'curator_only_pair_groups': dict(sorted(pair_groups.items(), key=lambda item: str(item[0]))),
        'interpretation': 'Zero construction errors verifies only the declared local transformation, formatting, units, and arithmetic. Missing original filing provenance and human accounting judgments remain unresolved.',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--pilot', type=Path)
    parser.add_argument('--output', type=Path, help='Optional full report; destination must be under a curator or .cache directory')
    parser.add_argument('--check-report', type=Path, help='Verify a saved curator report matches current deterministic findings')
    args = parser.parse_args()
    try:
        report = audit(args.root, args.pilot)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'structural_ready': False, 'expert_validated': False, 'publication_ready': False,
                          'input_error': str(exc)}, sort_keys=True))
        raise SystemExit(1)
    if args.output:
        if not {'curator', '.cache'} & set(args.output.parts):
            raise SystemExit('Full construction findings must be written under a curator or .cache directory')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    if args.check_report:
        if json.loads(lf_bytes(args.check_report)) != report:
            raise SystemExit('Saved curator quality report differs from current construction findings')
    public_summary = {key: value for key, value in report.items()
                      if not key.startswith('curator_only_') and key != 'errors'}
    print(json.dumps(public_summary, sort_keys=True))
    raise SystemExit(0 if report['structural_ready'] else 1)


if __name__ == '__main__':
    main()
