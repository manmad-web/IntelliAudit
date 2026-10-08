"""Readable projections of supplied evidence, without inventing accounting facts.

The original unit IDs and text remain available for historical annotations.
Stable content IDs supplement those IDs; display labels are local to a case.
"""
import hashlib
import re
from collections import Counter

ROW = re.compile(r'^\s*\[row\s+(\d+)\]\s*:\s*(.*?)\s*\|\s*(.*?)\s*(?:\[SEP\])?\s*$', re.I)


def clean_text(text):
    return re.sub(r'\s*\[SEP\]\s*$', '', text).strip()


def build_presentation(exam, units, dataset_id='pilot-v2'):
    meta = exam.get('metadata', {})
    rows, evidence, warnings = [], [], []
    occurrences = Counter()
    facts_section = False
    derived = set(meta.get('derived_rows', []))
    for index, unit in enumerate(units, 1):
        identity_text = clean_text(unit['text'])
        text = identity_text
        source = unit['source']
        match = ROW.match(unit['text']) if source == 'statement' else None
        heading = ''
        category = 'context'
        if match:
            row, label, amount = int(match[1]), match[2].strip(), clean_text(match[3])
            rows.append({'row': row, 'label': label, 'amount': amount,
                         'unit_id': unit['id'], 'derived': row in derived,
                         'note': 'Reconstructed residual; not an individually reported filing fact.' if row in derived else ''})
            category, heading = 'statement', label
            text = f'{label}: {amount}'
        elif source == 'statement' and not text.startswith('[Time]'):
            warnings.append('A statement line could not be presented as a labeled financial row.')
        elif source == 'transactions':
            if text.startswith('Supporting facts'):
                facts_section = True
                heading = 'Period-end context'
            elif re.match(r'^\[[^\]]+\]', text):
                category = 'movement'
                movement = re.match(r'^\[([^\]]+)\]\s*(.*)', text)
                heading, text = movement[1], movement[2]
            elif facts_section or re.match(r'^\s*-\s+', text):
                category = 'period_end_fact'
                text = re.sub(r'^\s*-\s+', '', text)
                heading = 'Supplied period-end fact'
            else:
                heading = 'Synthetic summary context'
        occurrence_key = (source, identity_text)
        occurrences[occurrence_key] += 1
        stable = hashlib.sha256((source + '\0' + identity_text + '\0' + str(occurrences[occurrence_key])).encode()).hexdigest()[:10].upper()
        evidence.append({'id': unit['id'], 'stable_id': 'EV-' + stable,
                         'label': f'EV-{index:03d}', 'source': source,
                         'category': category, 'heading': heading, 'text': text})
    statement_type = meta.get('statement_type', 'IncomeStatement')
    titles = {'IncomeStatement': 'Income Statement (Statement of Operations)',
              'BalanceSheet': 'Balance Sheet', 'CashFlow': 'Statement of Cash Flows',
              'CashFlowStatement': 'Statement of Cash Flows'}
    return {
        'version': 2, 'company_display': meta.get('company', 'Review case'),
        'framework': 'IFRS' if dataset_id == 'ifrs' else 'US GAAP',
        'statement_title': titles.get(statement_type, statement_type),
        'reporting_period': f"FY {meta.get('fiscal_year', 'unknown')} · period end {meta.get('period', 'not supplied')}",
        'reporting_date': meta.get('reporting_date'),
        'reporting_date_note': 'The period end is supplied; the original filing/publication date has not been verified.',
        'currency': meta.get('currency', 'USD' if str(meta.get('unit', '')).startswith('USD') else 'Not supplied'),
        'unit': meta.get('unit', 'Not supplied'), 'statement_rows': rows,
        'evidence': evidence, 'presentation_warnings': warnings,
        'source_notes': 'This packet is a reconstructed illustration derived from SEC financial figures, with synthetic account movements, period-end facts and simulated amounts. It is not a verbatim filed statement, an actual invoice or contract, or independent evidence about a real company. Marked residual rows were derived during reconstruction.',
        'limitations': 'Assess only the supplied information. Matching component totals does not prove recognition is appropriate. Missing facts must not be assumed true or false. Original filing accession and statement fidelity remain unverified. Related scenarios may appear in the pilot; assess each packet independently.',
        'task': {'title': 'Assess the reported revenue for this period',
                 'instruction': 'Decide whether the supplied information supports appropriate revenue recognition, supports a potential misstatement, is insufficient, or makes the case unclear. Do not assume every case contains an error.'},
    }
