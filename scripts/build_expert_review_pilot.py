#!/usr/bin/env python3
"""Version a neutral, pseudonymized review packet without changing frozen v1 work.

No new financial amounts, documentary evidence, authority, or reviewed labels
are created. Every construction mapping remains in the curator projection.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

try:
    from scripts import build_review_pilot as legacy
except ImportError:
    import build_review_pilot as legacy

ROOT = Path(__file__).resolve().parents[1]
SEED = 'accountant-review-pilot-v2-neutral-pseudonyms'
OLD_REVENUE = 'revenue recognised on satisfied performance obligations'
NEW_REVENUE = 'credits posted to the revenue account'
PROTOCOL = 'immediate_reconciliation_v2'


def rank(namespace: str, value: str) -> str:
    return hashlib.sha256(f'{SEED}|{namespace}|{value}'.encode()).hexdigest()


def neutral_transactions(text: str, original_company: str, alias: str) -> str:
    lines = text.splitlines()
    if not lines or not lines[0].startswith(f'Transaction evidence — {original_company} FY'):
        raise ValueError('Source transaction header does not identify its documented company')
    lines[0] = lines[0].replace(f'Transaction evidence — {original_company} FY',
                              f'Transaction evidence — {alias} FY', 1)
    return '\n'.join(lines).replace(OLD_REVENUE, NEW_REVENUE)


def clean_statement_metadata(metadata: dict) -> tuple[dict, str]:
    """Derived-row flags come from the preserved reconstructed base, never a guess."""
    path = ROOT / 'data/clean' / f"{int(metadata['cik'])}_{metadata['fiscal_year']}_IS.json"
    raw = legacy.canonical_lf_bytes(path.read_bytes())
    statement = json.loads(raw)
    if {field: statement.get(field) for field in metadata} != metadata:
        raise ValueError('Reconstructed statement metadata differs from its frozen pilot source')
    return statement, legacy.digest(raw)


def build(source: Path = ROOT / 'data/review_pilot', benchmark: Path = ROOT / 'data/benchmark') -> dict[str, bytes]:
    """Reject changed v1 inputs before making an explicitly separate new version."""
    expected = legacy.build(benchmark)
    source_raw = {}
    for name, value in expected.items():
        source_raw[name] = legacy.canonical_lf_bytes((source / name).read_bytes())
        if source_raw[name] != value:
            raise ValueError('Frozen v1 pilot differs from its deterministic source; preserve and resolve that version first')
    old_manifest = json.loads(source_raw['manifest.json'])
    old_cases = [json.loads(line) for line in source_raw['public_cases.jsonl'].splitlines()]
    old_proposals = {row['exam_id']: row for row in map(json.loads, source_raw['curator/proposals.jsonl'].splitlines())}
    companies = sorted({row['metadata']['cik'] for row in old_cases}, key=lambda cik: rank('company', cik))
    aliases = {cik: f'Company {chr(65 + index)}' for index, cik in enumerate(companies)}
    public, proposals = [], []
    for source_case in old_cases:
        original_metadata = source_case['metadata']
        clean, clean_sha256 = clean_statement_metadata(original_metadata)
        company_alias = aliases[original_metadata['cik']]
        case_id = 'RP2-' + rank('case-id', source_case['exam_id'])[:24]
        metadata = {field: original_metadata[field]
                    for field in ('fiscal_year', 'statement_type', 'period', 'unit')}
        metadata.update({'company': company_alias, 'reporting_date': None, 'currency': 'USD',
                         'derived_rows': [row['idx'] for row in clean['rows'] if row.get('residual')]})
        public.append({'exam_id': case_id, 'metadata': metadata,
                       'statement_text': source_case['statement_text'],
                       'transaction_data': neutral_transactions(source_case['transaction_data'], original_metadata['company'], company_alias)})
        proposal = copy.deepcopy(old_proposals[source_case['exam_id']])
        proposal.update({'exam_id': case_id, 'source_pilot_case_id': source_case['exam_id'],
                         'original_metadata': original_metadata, 'blind_company_alias': company_alias,
                         'pilot_version': 'review-pilot-v2', 'review_protocol': PROTOCOL,
                         'source_clean_sha256': clean_sha256,
                         'wording_change': {'from': OLD_REVENUE, 'to': NEW_REVENUE,
                                            'purpose': 'Remove an inherited recognition conclusion from synthetic component descriptions; preserve all amounts and substantive period-end facts.'},
                         'source_filing_accession': None,
                         'source_filing_fidelity': 'not_established',
                         'provenance_note': 'Reconstructed SEC-derived illustration, with computed residual rows and synthetic component movements, period-end facts, and simulated edits. Not a verbatim filing or authentic ledger. Original per-fact accession/period reconciliation is missing; no allegation about the named source company.'})
        proposal['answer']['exam_id'] = case_id
        # The old opaque case ID must not accidentally remain a visible answer ID.
        proposals.append(proposal)
    public.sort(key=lambda row: rank('order', row['exam_id']))
    proposals.sort(key=lambda row: row['exam_id'])
    public_bytes, private_bytes = legacy.jsonl_bytes(public), legacy.jsonl_bytes(proposals)
    manifest = {
        'schema_version': 'review-pilot-v2', 'seed': SEED,
        'status': 'EXPERT_REVIEW_PENDING', 'review_protocol': PROTOCOL,
        'purpose': 'Blind annotation and usability development pilot; automated checks do not establish accounting validity or a scientific reliability result.',
        'n_cases': len(public), 'n_companies': len(companies),
        'case_ids': [row['exam_id'] for row in public], 'accountant_reviews_completed': 0,
        'company_labels': sorted(aliases.values()),
        'source_commit': old_manifest['source_commit'],
        'source_repository': old_manifest['source_repository'],
        'source_paths': old_manifest['source_paths'],
        'source_sha256': old_manifest['source_sha256'],
        'source_bundle_sha256': old_manifest['source_bundle_sha256'],
        'source_pilot_version': old_manifest['schema_version'],
        'source_pilot_sha256': {name: legacy.digest(value) for name, value in sorted(source_raw.items())},
        'artifact_sha256': {'public_cases.jsonl': legacy.digest(public_bytes),
                            'curator/proposals.jsonl': legacy.digest(private_bytes)},
        'selection': 'Preserve the frozen v1 inventory of 20 related cases across five source companies, assign new opaque IDs and consistent Company A–E labels, and shuffle with the v2 seed.',
        'evidence': 'Reconstructed SEC-derived illustrations with computed residual rows and synthetic component movements, period-end facts, and simulated edits. Statements are not verbatim filings; supporting narratives are not authentic invoices, contracts, or ledgers. No allegation concerns a named company.',
        'date_policy': 'Fiscal year and statement period end retain the source values. Original reporting/publication date is unknown and represented as null; no date is invented.',
        'unit_policy': 'All statement values and supplied synthetic component/fact amounts are in USD millions; parentheses denote negative values.',
        'neutral_wording_policy': 'Replace the inherited revenue-component phrase asserting satisfied performance obligations with a neutral revenue-account credit description. Preserve every number, sign, statement row, and substantive period-end fact.',
        'withheld_variant_policy': old_manifest['withheld_variant_policy'],
        'pairing_limitations': 'Related full/withheld and reconstructed/simulated variants may cue judgments through repeated amounts and wording. Pseudonyms reduce name lookup cues but cannot establish blinding, minimal counterfactual validity, or genuinely undecidable evidence.',
        'review_policy': 'Record the complete initial pass before any proposed-answer reveal. Reconciliation follows immediately; this version does not request a delayed repeat or claim intra-rater reliability. Preserve initial and reconciliation records separately.',
        'qualification_policy': 'Reviewer qualification is self-declared and must be independently checked for the intended claim. An accounting student, exam-level candidate, or teammate is not automatically a licensed CPA or a qualified US-GAAP expert.',
        'publication_gate': 'Original filing accession/period/unit reconciliation, qualified human accounting and authority review, ambiguity disposition, leakage assessment, and research release gates remain pending.',
        'curator_access': 'Original company/CIK, old/new case mapping, source IDs, proposed answers, removed facts, pair groups, and construction notes are curator material. Keep them out of blind API responses. Repository access can expose construction keys and must be controlled in any future blinded study.',
        'licensing': old_manifest['licensing'],
        'version_policy': 'Frozen v1 artifacts and any historical review scope remain unchanged. v2 requires a separate dataset fingerprint and review scope; no automatic migration or relabeling of submitted work.',
    }
    return {'public_cases.jsonl': public_bytes, 'curator/proposals.jsonl': private_bytes,
            'manifest.json': legacy.json_bytes(manifest)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/review_pilot')
    parser.add_argument('--benchmark', type=Path, default=ROOT / 'data/benchmark')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/review_pilot_v2')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    artifacts = build(args.source, args.benchmark)
    if args.check:
        mismatches = [name for name, value in artifacts.items()
                      if not (args.output / name).is_file() or legacy.canonical_lf_bytes((args.output / name).read_bytes()) != value]
        if mismatches:
            raise SystemExit('Rebuild differs: ' + ', '.join(mismatches))
        print('Verified separate v2 packet: 20 cases, five company aliases, unchanged financial amounts; expert review remains pending.')
        return
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit('Refusing to replace a nonempty review directory. Use --check or a new --output.')
    for name, value in artifacts.items():
        target = args.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    print(f'Created separate unreviewed v2 pilot at {args.output}')


if __name__ == '__main__':
    main()
