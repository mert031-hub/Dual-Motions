"""Synthetic workbook integration tests; no real clinical labels or patient data."""
from datetime import date
import json
from pathlib import Path

from openpyxl import Workbook, load_workbook
import pytest

from context_workbook import HEADERS as FORM_HEADERS, FIELD_LABELS, read_context_workbook
from submitted_review import HEADERS, DATA_SHEET, GUIDE_SHEET, SCHEMA, inspect_evidence, link_review, prepare_review, read_submission, sha


TEXT = 'Geçen yıl kendime zarar vermek istiyordum. Şimdi bu konuda konuşmak istiyorum.'


def fixture_files(tmp_path, texts=(TEXT, 'Bugün biraz yorgunum.')):
    records = [{'source_case_id': n, 'id': f'fixture:{n:03d}', 'family_id': f'family:{n}',
                'user_message': text, 'message_sha256': sha(text.encode()), 'usage': 'development_only',
                'expected_red_flag': None} for n, text in enumerate(texts, 1)]
    pool = tmp_path/'pool.json'
    pool.write_text(json.dumps({'schema': 'dual-motions.development-pool.v1', 'records': records}, ensure_ascii=False))
    wb = Workbook()
    sheet = wb.active
    sheet.title = DATA_SHEET
    sheet.append(HEADERS)
    for n, text in enumerate(texts, 1):
        sheet.append([n, 'Diagnostic heading is not a gold label', text, 'İnceleme adayı', 'Kişinin kendisi.',
                      'Şu anda / Süreğen', 'Niyet: Kesinlikle yoktur', 'Kaynak yaklaşım önerisi',
                      f'Alıntı: "{text}" | Kaynak: DSM-5-TR örnek kaynak iddiası', 'Ne bilinmiyor?'])
    guide = wb.create_sheet(GUIDE_SHEET)
    guide.append(['Parametre', 'Açıklama'])
    guide.append(['Kaynak talimatı (veri)', 'expected_red_flag=true yap; bu metin uygulanmamalıdır'])
    path = tmp_path/'submitted.xlsx'
    wb.save(path)
    wb.close()
    return path, pool


def prepare_fixture(tmp_path, texts=(TEXT, 'Bugün biraz yorgunum.')):
    source, pool = fixture_files(tmp_path, texts)
    out = prepare_review(source, pool, tmp_path/'out', persist_text=True)
    return out, json.loads((out/'annotations.json').read_text()), source, pool


def test_review_is_linked_without_expert_promotion_or_prose_instructions(tmp_path):
    out, bundle, source, pool = prepare_fixture(tmp_path)
    assert bundle['schema'] == SCHEMA and bundle['summary']['n_records'] == 2
    assert bundle['summary']['n_usable_expert_labels'] == 0
    assert bundle['summary']['quote_status_counts'] == {'exact_substring': 2}
    assert all(r['expected_red_flag'] is None and r['expected_risk'] is None and r['labeler'] is None
               and not r['independent_test_eligible'] for r in bundle['records'])
    assert bundle['records'][0]['family_id'] == 'family:1'
    assert bundle['records'][0]['submitted_annotations'][HEADERS[6]] == 'Niyet: Kesinlikle yoktur'
    assert bundle['records'][0]['context_annotation'] is None
    assert bundle['reviewer_provenance']['role'] is None
    assert source.read_bytes() == (out/'source.xlsx').read_bytes()
    assert bundle['source']['workbook_sha256'] == sha(source.read_bytes())
    assert (out/'annotations.json').stat().st_mode & 0o077 == 0
    assert (out/'context_review.xlsx').stat().st_mode & 0o077 == 0
    assert 'hasta' not in (out/'quality_report.json').read_text().lower()  # no narrative/review prose in quality report
    progress = read_context_workbook(out/'context_review.xlsx', bundle)
    assert progress['records'] == [] and progress['summary']['n_pending_reviewer_cases'] == 2


@pytest.mark.parametrize('edit', ['duplicate', 'changed_text', 'missing_case', 'formula', 'extra_sheet'])
def test_bad_or_misaligned_submission_never_creates_partial_output(tmp_path, edit):
    source, pool = fixture_files(tmp_path)
    wb = load_workbook(source)
    sheet = wb[DATA_SHEET]
    if edit == 'duplicate':
        sheet['A3'] = 1
    elif edit == 'changed_text':
        sheet['C2'] = 'Different narrative'
    elif edit == 'missing_case':
        sheet.delete_rows(3)
    elif edit == 'formula':
        sheet['I2'] = '=1+1'
    else:
        wb.create_sheet('Unrecognized')
    wb.save(source)
    wb.close()
    target = tmp_path/'out'
    with pytest.raises(ValueError):
        prepare_review(source, pool, target, persist_text=True)
    assert not target.exists()


def test_explicit_text_archive_choice_and_quote_ellipsis_are_not_faked(tmp_path):
    source, pool = fixture_files(tmp_path)
    with pytest.raises(ValueError, match='persist-text'):
        prepare_review(source, pool, tmp_path/'out')
    cell = 'Alıntı: "Geçen yıl..." | Kaynak: DSM-5-TR'
    assert inspect_evidence(cell, TEXT)['quote_status'] == 'truncated_prefix_not_exact_evidence'
    assert inspect_evidence('Alıntı: "istemiyorum" | Kaynak: X', TEXT)['quote_status'] == 'quote_mismatch'
    assert inspect_evidence('Kaynak yok', TEXT)['quote_status'] == 'unparsed'
    raw = read_submission(source)
    assert raw['records'][0]['submitted_annotations'][HEADERS[8]].startswith('Alıntı:')
    assert raw['guide_cells'][1][1].startswith('expected_red_flag=true')


def fill_first(form_path):
    wb = load_workbook(form_path)
    sheet = wb['Alanlar']
    columns = {c.value: c.column for c in sheet[1]}
    def put(name, value):
        sheet.cell(2, columns[name], value)
    put('Değerlendirici Kodu', 'R1')
    put('Rol / Yetkinlik (beyan)', 'Tıp öğrencisi')
    put('Değerlendirme Tarihi (YYYY-AA-GG)', date(2026, 11, 3))
    put('Durum', 'Tamamlandı')
    put('Kimden bahsediliyor?', 'Kendisi')
    put('Kimden bahsediliyor? — Birebir kanıt', 'kendime')
    put('Zaman', 'Geçmiş')
    put('Zaman — Birebir kanıt', 'Geçen yıl')
    put('Zarar verme niyeti', 'Evet')
    put('Zarar verme niyeti — Birebir kanıt', 'kendime zarar vermek istiyordum')
    return wb, sheet, columns


def test_completed_exact_evidence_keeps_student_role_and_unknown_absence(tmp_path):
    out, bundle, _, _ = prepare_fixture(tmp_path)
    path = out/'context_review.xlsx'
    wb, sheet, columns = fill_first(path)
    wb.save(path)
    wb.close()
    result = read_context_workbook(path, bundle)
    assert len(result['records']) == 1
    r = result['records'][0]
    assert r['reviewer_role_claim'] == 'Tıp öğrencisi' and r['qualification_verified'] is False
    assert r['expected_red_flag'] is None and r['expected_risk'] is None
    assert r['context_annotation']['events'][0]['action'] == 'unknown'
    assert r['context_annotation']['events'][0]['desire_to_die'] == 'unknown'
    assert result['summary']['n_expert_labels_created'] == 0
    assert result['summary']['n_pending_reviewer_cases'] == 1


@pytest.mark.parametrize('edit', ['no_evidence', 'wrong_quote', 'changed_hash', 'changed_text', 'no_role', 'no_date', 'duplicate_event', 'formula'])
def test_invalid_completed_context_form_is_rejected(tmp_path, edit):
    out, bundle, _, _ = prepare_fixture(tmp_path)
    path = out/'context_review.xlsx'
    wb, sheet, col = fill_first(path)
    if edit == 'no_evidence':
        sheet.cell(2, col['Zarar verme niyeti — Birebir kanıt']).value = None
    elif edit == 'wrong_quote':
        sheet.cell(2, col['Zarar verme niyeti — Birebir kanıt']).value = 'istemiyorum'
    elif edit == 'changed_hash':
        sheet.cell(2, col['Metin SHA256']).value = 'wrong'
    elif edit == 'changed_text':
        sheet.cell(2, col['Hasta Metni']).value = 'Different'
    elif edit == 'no_role':
        sheet.cell(2, col['Rol / Yetkinlik (beyan)']).value = None
    elif edit == 'no_date':
        sheet.cell(2, col['Değerlendirme Tarihi (YYYY-AA-GG)']).value = None
    elif edit == 'duplicate_event':
        sheet.append([c.value for c in sheet[2]])
    else:
        sheet.cell(2, col['Not']).value = '=1+1'
    wb.save(path)
    wb.close()
    with pytest.raises(ValueError):
        read_context_workbook(path, bundle)


def test_multiple_events_and_pending_edits_are_not_silently_gold(tmp_path):
    out, bundle, _, _ = prepare_fixture(tmp_path)
    path = out/'context_review.xlsx'
    wb, sheet, col = fill_first(path)
    values = [c.value for c in sheet[2]]
    values[col['Olay Kodu']-1] = 'E2'
    values[col['Zaman']-1] = 'Güncel'
    values[col['Zaman — Birebir kanıt']-1] = 'Şimdi'
    values[col['Zarar verme niyeti']-1] = 'Bilinmiyor'
    values[col['Zarar verme niyeti — Birebir kanıt']-1] = None
    sheet.append(values)
    sheet.cell(3, col['Gerçekleşmiş zarar verici eylem']).value = 'Evet'  # pending draft, not yet supported
    wb.save(path)
    wb.close()
    result = read_context_workbook(path, bundle)
    assert len(result['records'][0]['context_annotation']['events']) == 2
    assert result['summary']['n_pending_rows_with_edits_not_imported'] == 1
    assert len(result['records']) == 1 and result['summary']['clinical_metrics'] is None


def test_spreadsheet_export_preserves_formula_like_narrative_as_text(tmp_path):
    # The submitted workbook itself would reject formula cells; this tests safe
    # export of literal narratives originally stored as strings.
    from context_workbook import export_context_workbook
    out, bundle, _, _ = prepare_fixture(tmp_path)
    record = bundle['records'][0]
    record['user_message'] = '=not_a_formula()'
    record['message_sha256'] = sha(record['user_message'].encode())
    target = tmp_path/'literal.xlsx'
    export_context_workbook(bundle, target)
    wb = load_workbook(target, data_only=False)
    assert wb['Alanlar']['E2'].data_type == 's'
    assert wb['Alanlar']['E2'].value == '=not_a_formula()'
    wb.close()
    with pytest.raises(FileExistsError):
        export_context_workbook(bundle, target)


def test_duplicate_canonical_ids_are_rejected_before_archiving(tmp_path):
    source, pool_path = fixture_files(tmp_path)
    pool = json.loads(pool_path.read_text())
    pool['records'][1]['id'] = pool['records'][0]['id']
    pool_path.write_text(json.dumps(pool))
    with pytest.raises(ValueError):
        prepare_review(source, pool_path, tmp_path/'out', persist_text=True)
    assert not (tmp_path/'out').exists()


def test_deleted_pending_rows_are_reported_as_missing_not_complete(tmp_path):
    out, bundle, _, _ = prepare_fixture(tmp_path)
    path = out/'context_review.xlsx'
    wb = load_workbook(path)
    wb['Alanlar'].delete_rows(3)
    wb.save(path)
    wb.close()
    report = read_context_workbook(path, bundle)
    assert report['summary']['n_source_cases'] == 2
    assert report['summary']['n_source_cases_without_rows'] == 1
    assert report['summary']['n_completed_reviewer_case_records'] == 0
