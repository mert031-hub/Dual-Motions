import json
from pathlib import Path

import pytest

from development_pool import build_pool, literal_assignment, prepare, snapshot


def case(cid=26, title='Original family', text='Kendimi öldüreceğim.'):
    return dict(case_id=cid, category_id=2, category_name='Source category',
                title=title, narrative=text, Risk_Seviyesi='Sarı')


def test_static_reader_does_not_execute_submitted_code(tmp_path):
    marker = tmp_path/'executed'
    source = tmp_path/'source.py'
    source.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\nCASES = [1]\n")
    assert literal_assignment(source, 'CASES') == [1]
    assert not marker.exists()
    source.write_text('CASES = list(range(3))')
    with pytest.raises(ValueError):
        literal_assignment(source, 'CASES')


def test_colors_report_and_family_do_not_become_expert_labels():
    legacy = [dict(id=1, title='Original family')]
    report = [dict(case_id=26, red_flag_type='Source claim')]
    pool = build_pool([case()], report, legacy, 'upload')
    row = pool['records'][0]
    assert row['id'] == 'upload:026' and row['family_id'] == 'legacy:001'
    assert row['source_report_entry'] == report[0]
    assert row['expected_red_flag'] is None and row['expected_flags'] is None
    assert row['emotion'] is None and row['source_color'] == 'Sarı'
    assert row['independent_test_eligible'] is False
    assert row['source_record']['narrative'] == row['user_message']
    unrelated = build_pool([case(title='Different')], [], legacy, 'upload')['records'][0]
    assert unrelated['legacy_candidate_id'] is None
    assert 'independence_not_established' in unrelated['family_evidence']


@pytest.mark.parametrize('records,report', [([case(), case()], []),
                                          ([case()], [dict(case_id=99)]),
                                          ([case()], [dict(case_id=26), dict(case_id=26)])])
def test_ambiguous_ids_are_rejected(records, report):
    with pytest.raises(ValueError):
        build_pool(records, report, [], 'upload')


def test_prepare_and_snapshot_preserve_sources_and_repeated_runs(tmp_path, monkeypatch):
    import llm_factory
    monkeypatch.setattr(llm_factory, 'get_chat_model', lambda *a, **k: pytest.fail('API attempted'))
    source, report = tmp_path/'input.py', tmp_path/'report.py'
    source.write_text('CASES = ' + repr([case(), case(27, text='Bugün sakinim.')]))
    report.write_text('RED_FLAG_CASES = []')
    with pytest.raises(ValueError, match='persist-text'):
        prepare(source, report, tmp_path/'pool')
    pool_path = prepare(source, report, tmp_path/'pool', persist_text=True)
    assert (pool_path.parent/'sources/input.py').read_bytes() == source.read_bytes()
    assert pool_path.stat().st_mode & 0o077 == 0
    before = pool_path.read_bytes()
    first = snapshot(pool_path, tmp_path/'runs')
    second = snapshot(pool_path, tmp_path/'runs')
    assert first != second
    assert (first/'observations.json').read_bytes() == (second/'observations.json').read_bytes()
    result = json.loads((first/'observations.json').read_text())
    assert result['summary']['n_with_rule_match'] == 1
    assert result['records'][0]['tier'] == 1
    assert result['records'][0]['flags'][0]['name'] == 'active_self_harm'
    assert result['records'][1]['tier'] == 0
    assert result['summary']['clinical_metrics'] is None
    assert 'user_message' not in result['records'][0]
    assert pool_path.read_bytes() == before
    manifest = json.loads((first/'manifest.json').read_text())
    assert manifest['model_calls'] == 0 and manifest['code_sha256']['red_flags.py']
    pool = json.loads(before)
    pool['records'][0]['user_message'] = 'Altered after preparation'
    pool_path.write_text(json.dumps(pool))
    with pytest.raises(ValueError, match='Changed message'):
        snapshot(pool_path, tmp_path/'runs')
