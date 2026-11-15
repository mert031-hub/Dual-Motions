import json

import pandas as pd
from openpyxl import load_workbook

import clinician_review as cr
import judge
import review_excel as rx


def _run(tmp_path, n_pos=6, n_neg=4):
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'manifest.json').write_text(json.dumps({'run_id': 'r', 'persist_text': True, 'finished_at': 'x',
                                                    'execution_mode': 'live'}), encoding='utf-8')
    rows = []
    for k in range(n_pos + n_neg):
        for s in ('study_baseline', 'study_full'):
            rows.append({'case_id': f'X{k:03d}', 'system': s, 'repeat': 0, 'user_message': f'mesaj {k}',
                         'final_output': f'yanit {s} {k}', 'error': '', 'triage_tier': 0,
                         'expected_red_flag': k < n_pos, 'family_id': f'X{k:03d}',
                         **{d: 5 for d in judge.DIMENSIONS}, 'excessive_advice': False,
                         'excessive_directiveness': False})
    pd.DataFrame(rows).to_csv(run / 'responses.csv', index=False)
    packet = tmp_path / 'p.json'
    cr.export_packet(run, packet)
    return run, packet


def test_export_hides_system_and_pairs_cases(tmp_path):
    run, packet = _run(tmp_path)
    out = tmp_path / 'f.xlsx'
    info = rx.export_xlsx(packet, run, out, n_pos=3, n_neg=2, seed=1)
    assert info['n_items'] == 10 and info['n_pos_cases'] == 3 and info['n_neg_cases'] == 2
    ws = load_workbook(out)['Puanlama']
    sheets = ' '.join(str(c.value) for w in load_workbook(out) for r in w.iter_rows() for c in r if c.value)
    assert 'study_baseline' not in sheets.replace('yanit study_baseline', '') and 'mapping' not in sheets.lower()
    assert all('X0' not in str(r[0].value) for r in ws.iter_rows(min_row=2))
    assert [c.value for c in ws[1]][:3] == ['Kod', 'Hasta mesajı', 'Sistem yanıtı']


def test_export_is_outcome_independent_and_refuses_overwrite(tmp_path):
    run, packet = _run(tmp_path)
    a = rx.export_xlsx(packet, run, tmp_path / 'a.xlsx', 3, 2, 5)
    b = rx.export_xlsx(packet, run, tmp_path / 'b.xlsx', 3, 2, 5)
    assert a['n_items'] == b['n_items']
    try:
        rx.export_xlsx(packet, run, tmp_path / 'a.xlsx')
        raise AssertionError
    except FileExistsError:
        pass


def test_import_roundtrip_with_blanks_and_flags(tmp_path):
    run, packet = _run(tmp_path)
    out = tmp_path / 'f.xlsx'
    rx.export_xlsx(packet, run, out, 2, 1, 3)
    wb = load_workbook(out)
    ws = wb['Puanlama']
    ws['D2'], ws['E2'], ws['G2'], ws['H2'] = 4, 3, 'E', 'H'
    ws['D3'] = 5
    wb.save(out)
    res = rx.import_xlsx(out, packet, 'Yavuz', tmp_path / 'r.json')
    data = json.loads((tmp_path / 'r.json').read_text(encoding='utf-8'))
    first = data['ratings'][0]
    assert res['n_ratings'] == 6 and first['scores']['safety'] == 4 and first['scores']['clinical_appropriateness'] is None
    assert first['behavior_flags'] == {'excessive_advice': True, 'excessive_directiveness': False}
    assert first['scores']['validation'] is None


def test_import_rejects_bad_flag_and_unknown_code(tmp_path):
    run, packet = _run(tmp_path)
    out = tmp_path / 'f.xlsx'
    rx.export_xlsx(packet, run, out, 2, 1, 3)
    wb = load_workbook(out)
    wb['Puanlama']['G2'] = 'X'
    wb.save(out)
    try:
        rx.import_xlsx(out, packet, 'Y', tmp_path / 'r.json')
        raise AssertionError
    except ValueError:
        pass


def test_export_strips_control_characters(tmp_path):
    run, packet = _run(tmp_path)
    data = json.loads(packet.read_text(encoding='utf-8'))
    for it in data['items']:
        it['response'] = 'ba\x0bd\x00 yanit'
    packet.write_text(json.dumps(data), encoding='utf-8')
    rx.export_xlsx(packet, run, tmp_path / 'c.xlsx', 2, 1, 1)
    ws = load_workbook(tmp_path / 'c.xlsx')['Puanlama']
    assert ws['C2'].value == 'bad yanit'
