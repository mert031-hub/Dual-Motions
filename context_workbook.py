"""Plain Turkish Excel event reviews -> evidence-validated context annotations.

An attributed review is not automatically an expert label or independent test.
"""
import argparse
from collections import defaultdict
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from context_schema import ContextAnnotation, validate_annotation
from storage import write_json

FIELD_LABELS = {
    'subject': 'Kimden bahsediliyor?', 'time': 'Zaman', 'unwanted_thought': 'İstenmeyen düşünce',
    'intent': 'Zarar verme niyeti', 'desire_to_die': 'Ölme isteği',
    'plan_or_preparation': 'Plan / hazırlık', 'action': 'Gerçekleşmiş zarar verici eylem',
    'injury_or_poisoning': 'Yaralanma / zehirlenme', 'physical_need': 'Fiziksel ihtiyaç',
}
YES_NO = {'Bilinmiyor': 'unknown', 'Evet': 'yes', 'Hayır': 'no'}
VALUES = {name: YES_NO for name in FIELD_LABELS}
VALUES['subject'] = {'Bilinmiyor': 'unknown', 'Kendisi': 'self', 'Başkası': 'other', 'Alıntı': 'quoted'}
VALUES['time'] = {'Bilinmiyor': 'unknown', 'Güncel': 'current', 'Geçmiş': 'past', 'Varsayımsal': 'hypothetical'}
BASE = ['Vaka No', 'Kayıt Kimliği', 'Metin SHA256', 'Olay Kodu', 'Hasta Metni', 'Değerlendirici Kodu',
        'Rol / Yetkinlik (beyan)', 'Değerlendirme Tarihi (YYYY-AA-GG)', 'Durum', 'Not']
HEADERS = BASE + [label + suffix for label in FIELD_LABELS.values() for suffix in ('', ' — Birebir kanıt')]
SHEET = 'Alanlar'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _text(cell, value):
    cell.value = str(value) if value is not None else ''
    cell.data_type = 's'  # User-submitted prose beginning '=' remains text, never an Excel formula.
    cell.alignment = Alignment(wrap_text=True, vertical='top')


def validate_bundle(bundle):
    if bundle.get('schema') != 'dual-motions.submitted-review.v1':
        raise ValueError('Unsupported submitted-review bundle')
    records = bundle['records']
    if not records or len({r['id'] for r in records}) != len(records):
        raise ValueError('Empty/duplicate review bundle')
    if any(r.get('usage') != 'development_only' or r.get('expected_red_flag') is not None
           or sha(r['user_message'].encode()) != r['message_sha256'] for r in records):
        raise ValueError('Changed narrative or invalid review usage')
    return {r['id']: r for r in records}


def export_context_workbook(bundle, target):
    validate_bundle(bundle)
    target = Path(target)
    if target.exists():
        raise FileExistsError('Refuse to overwrite a review form')
    wb = Workbook()
    sheet = wb.active
    sheet.title = SHEET
    sheet.append(HEADERS)
    for rownum, record in enumerate(bundle['records'], 2):
        values = [record['source_case_id'], record['id'], record['message_sha256'], 'E1', record['user_message'],
                  '', '', '', 'Bekliyor', ''] + [v for _ in FIELD_LABELS for v in ('Bilinmiyor', '')]
        for col, value in enumerate(values, 1):
            _text(sheet.cell(rownum, col), value)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='244C66')
        cell.alignment = Alignment(wrap_text=True)
    sheet.freeze_panes = 'F2'
    sheet.auto_filter.ref = sheet.dimensions
    sheet.column_dimensions['B'].hidden = True
    sheet.column_dimensions['C'].hidden = True
    sheet.column_dimensions['A'].width = 10
    sheet.column_dimensions['D'].width = 10
    sheet.column_dimensions['E'].width = 70
    from openpyxl.utils import get_column_letter
    for col in range(6, len(HEADERS) + 1):
        sheet.column_dimensions[get_column_letter(col)].width = 25 if col % 2 else 35
    for row in range(2, len(bundle['records']) + 2):
        sheet.row_dimensions[row].height = 120
    status = DataValidation(type='list', formula1='"Bekliyor,Tamamlandı"')
    sheet.add_data_validation(status)
    status.add(f'I2:I{len(bundle["records"])+1}')
    for index, name in enumerate(FIELD_LABELS):
        col = get_column_letter(len(BASE) + 1 + 2 * index)
        validation = DataValidation(type='list', formula1='"' + ','.join(VALUES[name]) + '"')
        sheet.add_data_validation(validation)
        validation.add(f'{col}2:{col}{len(bundle["records"])+1}')
    instructions = wb.create_sheet('Nasıl Doldurulur')
    help_rows = [
        ('Amaç', 'Tanı veya düşük/orta/yüksek risk puanı vermeyin. Metinde ne ifade edildiğini ayrı alanlarda kaydedin.'),
        ('Bilinmiyor', 'Bir bilgi metinde geçmiyorsa Bilinmiyor bırakın. Söylenmemiş bilgi Hayır değildir.'),
        ('Kanıt', 'Bilinmiyor dışındaki HER alan için hasta metninden birebir, ilgili kısa cümleyi kopyalayın. Üç noktalı özet kullanmayın.'),
        ('Niyet', 'Zarar verme niyeti ve ölme isteği ayrıdır. İstenmeyen düşünce tek başına niyet değildir. Günlük işi sürdürme/kaçınma isteği bu alana yazılmaz.'),
        ('Eylem', 'Gerçekleşmiş zarar verici eylem ve yaralanma ayrı alanlardır. Söylenmemiş bir girişimi yok saymayın veya var saymayın.'),
        ('Birden fazla olay', 'Geçmiş ve güncel ya da farklı kişiye ait olaylar için satırı çoğaltın; aynı vaka/metinle Olay Kodu E2, E3 yazın. Tek satırda çelişkili zamanları birleştirmeyin.'),
        ('Atıf', 'Tamamlandı işaretlemeden önce değerlendirici kodu, rol/yetkinlik beyanı ve tarihi yazın. Kişisel ad/kimlik gerekli değildir.'),
        ('Bağımsız inceleme', 'Bu dosyada ilk yazarın klinik açıklamaları ve tanı başlıkları gösterilmez. İkinci değerlendirici ayrı kopyayla çalışmalı; ilk puanları görmemeli.'),
        ('Sınır', 'Rol yazmak uzmanlık doğrulaması değildir. Teknik doğrulama alıntı/şema bütünlüğünü denetler; yorumun klinik doğruluğunu kanıtlamaz.'),
    ]
    for rownum, pair in enumerate(help_rows, 1):
        for col, value in enumerate(pair, 1):
            _text(instructions.cell(rownum, col), value)
    instructions.column_dimensions['A'].width = 24
    instructions.column_dimensions['B'].width = 115
    for row in range(1, len(help_rows) + 1):
        instructions.row_dimensions[row].height = 55
    target.parent.mkdir(parents=True, exist_ok=True)
    wb.save(target)
    wb.close()
    os.chmod(target, 0o600)
    return target


def read_context_workbook(path, bundle):
    by_id = validate_bundle(bundle)
    wb = load_workbook(path, data_only=False, keep_links=False)
    groups = defaultdict(list)
    try:
        if set(wb.sheetnames) != {SHEET, 'Nasıl Doldurulur'}:
            raise ValueError('Unexpected review-form sheets')
        for sheet in wb:
            if any(c.data_type == 'f' for row in sheet for c in row):
                raise ValueError('Formula cells are not accepted')
        sheet = wb[SHEET]
        if [c.value for c in sheet[1]] != HEADERS:
            raise ValueError('Unexpected form headers')
        seen = set()
        for values in sheet.iter_rows(min_row=2, values_only=True):
            if not any(v is not None for v in values):
                continue
            row = dict(zip(HEADERS, values))
            record = by_id.get(row['Kayıt Kimliği'])
            if (record is None or str(row['Vaka No']) != str(record['source_case_id'])
                    or row['Metin SHA256'] != record['message_sha256']
                    or row['Hasta Metni'] != record['user_message']):
                raise ValueError('Unknown case or changed narrative/hash')
            status = row['Durum']
            if status not in ('Bekliyor', 'Tamamlandı'):
                raise ValueError('Explicit review status required')
            reviewer = str(row['Değerlendirici Kodu'] or '').strip()
            event_id = str(row['Olay Kodu'] or '').strip()
            key = (record['id'], reviewer, event_id)
            if not event_id or key in seen:
                raise ValueError('Missing/duplicate event code for reviewer/case')
            seen.add(key)
            groups[(record['id'], reviewer)].append((row, record))
    finally:
        wb.close()
    completed, pending, draft_rows = [], 0, 0
    for (ident, reviewer), rows in groups.items():
        statuses = {r['Durum'] for r, _ in rows}
        if len(statuses) != 1:
            raise ValueError('All events for a reviewer/case need the same completion status')
        if statuses == {'Bekliyor'}:
            pending += 1
            draft_rows += sum(any(r[FIELD_LABELS[k]] not in (None, 'Bilinmiyor') or r[FIELD_LABELS[k]+' — Birebir kanıt']
                                  for k in FIELD_LABELS) for r, _ in rows)
            continue  # Incomplete edits are drafts, never converted into reference labels.
        roles = {str(r['Rol / Yetkinlik (beyan)'] or '').strip() for r, _ in rows}
        dates = set()
        for row, _ in rows:
            value = row['Değerlendirme Tarihi (YYYY-AA-GG)']
            if isinstance(value, datetime):
                value = value.date()
            if isinstance(value, date):
                value = value.isoformat()
            dates.add(date.fromisoformat(str(value)).isoformat())
        if not reviewer or len(roles) != 1 or not next(iter(roles)) or len(dates) != 1:
            raise ValueError('Completed review needs consistent reviewer, role and date')
        events = []
        record = rows[0][1]
        for row, _ in rows:
            event = {'evidence': {}}
            for field, label in FIELD_LABELS.items():
                if row[label] not in VALUES[field]:
                    raise ValueError('Choose an explicit allowed value for every context field')
                value, quote = VALUES[field][row[label]], row[label+' — Birebir kanıt']
                event[field] = value
                if quote is not None and str(quote).strip():
                    if not isinstance(quote, str):
                        raise ValueError('Evidence must be text')
                    event['evidence'][field] = [{'quote': quote}]
            events.append(event)
        annotation = validate_annotation({'events': events}, record['user_message'])
        completed.append({'id': ident, 'source_case_id': record['source_case_id'], 'family_id': record['family_id'],
                          'message_sha256': record['message_sha256'], 'reviewer': reviewer,
                          'reviewer_role_claim': next(iter(roles)), 'qualification_verified': False,
                          'review_date': next(iter(dates)), 'context_annotation': annotation.model_dump(),
                          'usage': 'development_only', 'independent_test_eligible': False,
                          'expected_red_flag': None, 'expected_risk': None,
                          'status': 'attributed_context_review_not_adjudicated'})
    return {'schema': 'dual-motions.context-workbook-review.v1', 'records': completed,
            'summary': {'n_source_cases': len(by_id), 'n_source_cases_without_rows': len(set(by_id) - {ident for ident, _ in groups}),
                        'n_completed_reviewer_case_records': len(completed), 'n_pending_reviewer_cases': pending,
                        'n_pending_rows_with_edits_not_imported': draft_rows,
                        'n_completed_without_known_observations': sum(
                            all(getattr(e, field) == 'unknown' for e in ContextAnnotation.model_validate(r['context_annotation']).events
                                for field in FIELD_LABELS) for r in completed),
                        'n_expert_labels_created': 0, 'clinical_metrics': None}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--form', required=True)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    target = Path(args.out)
    if target.exists():
        raise FileExistsError('Refuse to overwrite an existing context review')
    raw = Path(args.bundle).read_bytes()
    result = read_context_workbook(args.form, json.loads(raw))
    result['source'] = {'bundle_sha256': sha(raw), 'form_sha256': sha(Path(args.form).read_bytes())}
    write_json(target, result)
    print(target)
