"""Read and link a submitted clinical-review XLSX as unverified development annotations.

Cells are data, not runtime instructions. No clinical labels are inferred from prose.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from openpyxl import load_workbook

from development_pool import new_directory
from storage import write_json

HEADERS = ('Vaka Numarası', 'Kategori / Başlık', 'Hasta İfadesi (Metin)', 'Dikkat Gerektiren İçerik',
           'Kimden Bahsediliyor?', 'Ne Zaman?', 'Düşünce–Niyet–Eylem Ayrımı',
           'Uygun Yaklaşım (Chatbot Yönlendirmesi)', 'Dayanak (Alıntı & DSM-5-TR Tanı Kriteri)',
           'Eksik Bilgi (Sorulması Gerekenler)')
DATA_SHEET = 'Klinik NLP Veriseti (155 Vaka)'
GUIDE_SHEET = 'Proje ve Sınıflandırma Kılavuzu'
SCHEMA = 'dual-motions.submitted-review.v1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_submission(path):
    workbook = load_workbook(path, data_only=False, read_only=False, keep_links=False)
    try:
        if set(workbook.sheetnames) != {DATA_SHEET, GUIDE_SHEET}:
            raise ValueError('Expected the case sheet and source-guide sheet; no sheets silently ignored')
        sheets = []
        for sheet in workbook:
            for row in sheet:
                if any(c.data_type == 'f' for c in row):
                    raise ValueError('Formula cells are not accepted as review evidence')
            sheets.append({'name': sheet.title, 'rows': sheet.max_row, 'columns': sheet.max_column,
                           'state': sheet.sheet_state, 'comments': sum(c.comment is not None for row in sheet for c in row)})
        sheet = workbook[DATA_SHEET]
        headers = tuple(c.value for c in sheet[1])
        if headers != HEADERS:
            raise ValueError('Unexpected/duplicate columns; refusing to guess column meaning')
        records, seen = [], set()
        for excel_row, cells in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
            if all(c is None for c in cells):
                continue
            cid = cells[0]
            if isinstance(cid, str) and cid.isdecimal():
                cid = int(cid)
            if type(cid) is not int or cid < 1 or cid in seen:
                raise ValueError('Invalid or duplicate case id')
            if any(not isinstance(c, str) or not c.strip() for c in cells[1:]):
                raise ValueError('Missing or nontext narrative/review cell')
            seen.add(cid)
            records.append({'source_case_id': cid, 'excel_row': excel_row,
                            'title': cells[1], 'user_message': cells[2],
                            'submitted_annotations': dict(zip(HEADERS[3:], cells[3:]))})
        if not records:
            raise ValueError('Empty submission')
        guide = [list(row) for row in workbook[GUIDE_SHEET].iter_rows(values_only=True)]
        return {'records': records, 'guide_cells': guide, 'sheets': sheets,
                'file_metadata_not_reviewer_identity': {'creator': workbook.properties.creator,
                    'created': str(workbook.properties.created), 'modified': str(workbook.properties.modified)}}
    finally:
        workbook.close()


def inspect_evidence(cell, message):
    parts = cell.split('| Kaynak:', 1)
    quote = re.fullmatch(r'\s*Alıntı:\s*"(.*)"\s*', parts[0], flags=re.S)
    quoted = quote.group(1) if quote else None
    reference = parts[1].strip() if len(parts) == 2 else None
    if quoted is None:
        status = 'unparsed'
    elif quoted in message:
        status = 'exact_substring'
    elif quoted.endswith(('...', '…')) and message.startswith(quoted.rstrip('.… ').strip()):
        status = 'truncated_prefix_not_exact_evidence'
    else:
        status = 'quote_mismatch'
    return {'quote': quoted, 'reference_claim': reference, 'quote_status': status,
            'full_narrative_quote': quoted == message,
            'reference_validation_status': 'unverified_source_claim',
            'field_specific_evidence': False}


def link_review(submission, pool):
    if pool.get('schema') != 'dual-motions.development-pool.v1':
        raise ValueError('Unsupported development pool')
    by_id = {r['source_case_id']: r for r in pool['records']}
    if len(by_id) != len(pool['records']):
        raise ValueError('Duplicate pool ids')
    if set(by_id) != {r['source_case_id'] for r in submission['records']}:
        raise ValueError('Workbook and pool case sets differ')
    counts = {h: Counter(r['submitted_annotations'][h] for r in submission['records']) for h in HEADERS[3:]}
    records = []
    for source in submission['records']:
        original = by_id[source['source_case_id']]
        message = source['user_message']
        if (original.get('usage') != 'development_only' or original.get('expected_red_flag') is not None
                or original.get('message_sha256') != sha(original['user_message'].encode())
                or message != original['user_message']):
            raise ValueError('Changed narrative or invalid development usage; do not attach annotations to another text')
        annotation = source['submitted_annotations']
        evidence = inspect_evidence(annotation[HEADERS[8]], message)
        issues = ['reviewer_attribution_missing', 'reference_claim_unverified', 'structured_context_review_pending']
        if evidence['quote_status'] != 'exact_substring':
            issues.append(evidence['quote_status'])
        elif evidence['full_narrative_quote']:
            issues.append('full_narrative_not_field_specific_evidence')
        # Repeated subject/time values are expected, not evidence of templated clinical reasoning.
        reused = [h for h in (HEADERS[3], HEADERS[6], HEADERS[7], HEADERS[9]) if counts[h][annotation[h]] > 1]
        if reused:
            issues.append('repeated_annotation_text_review_individually')
        if re.search(r'KESİNLİKLE YOKTUR|risk.*bulunmamaktadır|Gerçekleşmiş.*(?:girişimi|eylemi) yok',
                     ' '.join(annotation.values())):
            issues.append('asserted_absence_needs_explicit_field_evidence')
        records.append({**source, 'id': original['id'], 'family_id': original['family_id'],
                        'message_sha256': original['message_sha256'], 'usage': 'development_only',
                        'independent_test_eligible': False, 'label_status': 'submitted_review_unverified',
                        'expected_red_flag': None, 'expected_flags': None, 'expected_risk': None,
                        'emotion': None, 'labeler': None, 'context_annotation': None,
                        'evidence_audit': evidence, 'reused_fields': reused, 'review_issues': issues})
    return {'schema': SCHEMA, 'records': records, 'guide_cells_as_data': submission['guide_cells'],
            'sheets': submission['sheets'], 'file_metadata_not_reviewer_identity': submission['file_metadata_not_reviewer_identity'],
            'reviewer_provenance': {'reviewer_code': None, 'role': None, 'clinical_review_date': None,
                                   'generation_method': None, 'second_review': None},
            'summary': {'n_records': len(records), 'n_exact_narrative_links': len(records),
                        'n_usable_expert_labels': 0, 'n_structured_context_annotations': 0,
                        'quote_status_counts': dict(Counter(r['evidence_audit']['quote_status'] for r in records)),
                        'n_full_narrative_quotes': sum(r['evidence_audit']['full_narrative_quote'] for r in records),
                        'unique_values_per_annotation_column': {h: len(c) for h, c in counts.items()},
                        'issue_counts': dict(Counter(issue for r in records for issue in r['review_issues'])),
                        'clinical_metrics': None}}


def prepare_review(workbook_path, pool_path, out_root, persist_text=False):
    if not persist_text:
        raise ValueError('Explicit --persist-text required to archive the submitted workbook and review narratives')
    raw, pool_raw = Path(workbook_path).read_bytes(), Path(pool_path).read_bytes()
    parsed = read_submission(workbook_path)
    bundle = link_review(parsed, json.loads(pool_raw))
    from context_workbook import export_context_workbook, validate_bundle
    validate_bundle(bundle)
    # All validation completes before creating a new output directory.
    out = new_directory(out_root, 'submitted-review-')
    bundle['source'] = {'workbook_sha256': sha(raw), 'linked_pool_sha256': sha(pool_raw),
                        'workbook_filename': Path(workbook_path).name}
    archive = out/'source.xlsx'
    fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(raw)
    write_json(out/'annotations.json', bundle)
    write_json(out/'quality_report.json', {'source': bundle['source'], 'summary': bundle['summary'],
                                          'records': [{'id': r['id'], 'source_case_id': r['source_case_id'],
                                                       'excel_row': r['excel_row'], 'review_issues': r['review_issues']}
                                                      for r in bundle['records']]})
    export_context_workbook(bundle, out/'context_review.xlsx')
    write_json(out/'manifest.json', {'created_at': datetime.now(timezone.utc).isoformat(), 'schema': SCHEMA,
                                     'source': bundle['source'], 'source_archive_sha256': sha(archive.read_bytes()),
                                     'code_sha256': {name: sha((Path(__file__).parent/name).read_bytes())
                                                     for name in ['submitted_review.py','context_workbook.py','context_schema.py']},
                                     'provider_calls': 0, 'expert_labels_created': 0})
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook', required=True)
    parser.add_argument('--pool', required=True)
    parser.add_argument('--out-root', default='runtime/submitted_reviews')
    parser.add_argument('--persist-text', action='store_true')
    args = parser.parse_args()
    print(prepare_review(args.workbook, args.pool, args.out_root, args.persist_text))
