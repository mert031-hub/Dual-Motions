import json

import pandas as pd

import relabel
import review_compare as rc


def test_read_labels_cp1254_and_diff(tmp_path):
    p = tmp_path / 'l.csv'
    p.write_bytes('id;user_message;expected_red_flag;expected_risk\nX1;yaşım;EVET;high\nX2;m;HAYIR;low\n'.encode('cp1254'))
    labels = relabel.read_labels(p)
    assert labels['X1'] == {'expected_red_flag': True, 'expected_risk': 'high'}
    cases = [{'id': 'X1', 'expected_red_flag': False, 'expected_risk': 'high'},
             {'id': 'X2', 'expected_red_flag': False, 'expected_risk': 'low'}]
    assert relabel.diff_cases(cases, labels) == [('X1', 'expected_red_flag', False, True)]


def test_apply_keeps_messages_and_backs_up(tmp_path):
    p = tmp_path / 'c.json'
    p.write_text(json.dumps({'meta': {}, 'cases': [{'id': 'X1', 'user_message': 'yaşım', 'expected_red_flag': False,
                                                    'expected_risk': 'high'}]}), encoding='utf-8')
    relabel.apply_to_cases(p, {'X1': {'expected_red_flag': True, 'expected_risk': 'high'}})
    c = json.loads(p.read_text(encoding='utf-8'))['cases'][0]
    assert c['expected_red_flag'] is True and c['user_message'] == 'yaşım' and (tmp_path / 'c.json.bak').exists()


def test_mcnemar_exact():
    assert relabel.mcnemar_exact(4, 0) == 0.125 and relabel.mcnemar_exact(0, 0) == 1.0


def test_recompute_run_moves_case_between_groups(tmp_path):
    rows = []
    for cid, flag, miss in (('A1', True, False), ('A2', False, False), ('A3', False, True)):
        for s, m in (('sa', False), ('sb', miss)):
            rows.append({'case_id': cid, 'system': s, 'error': '', 'judged': True, 'expected_red_flag': flag,
                         'missed_crisis': m, 'over_escalation': False, 'safety': 5})
    pd.DataFrame(rows).to_csv(tmp_path / 'responses.csv', index=False)
    lines = []
    relabel.recompute_run(tmp_path, {'A3': {'expected_red_flag': True, 'expected_risk': None}}, out=lines.append)
    assert 'sb: n=3 | pozitif 2 negatif 1 | kriz kaçırma 1/2' in lines[1]


def test_review_compare_pairs_and_agreement(tmp_path):
    ratings = {'packet_id': 'p', 'ratings': []}
    mapping = {'packet_id': 'p', 'items': {}}
    for k in range(6):
        for s, safe in (('sa', 5), ('sb', 3)):
            iid = f'{s}{k}'
            ratings['ratings'].append({'item_id': iid, 'reviewer': 'Y', 'scores': {'safety': safe, 'empathy': 4, 'clinical_appropriateness': 4},
                                       'behavior_flags': {'excessive_advice': False, 'excessive_directiveness': False}})
            mapping['items'][iid] = {'case_id': f'C{k}', 'system': s, 'judge_scores': {'safety': 5, 'empathy': 4, 'clinical_appropriateness': 4}}
    (tmp_path / 'r.json').write_text(json.dumps(ratings), encoding='utf-8')
    (tmp_path / 'm.json').write_text(json.dumps(mapping), encoding='utf-8')
    out = []
    rc.summarize(rc.load(tmp_path / 'r.json', tmp_path / 'm.json'), out=out.append)
    text = '\n'.join(out)
    assert 'ortalama -2.00' in text and 'güvenlik ≤3: 6/6' in text
