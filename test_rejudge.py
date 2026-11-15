import pandas as pd
import judge
import rejudge


def _value():
    v = {d: 5 for d in judge.DIMENSIONS}
    v.update(unsafe=False, missed_crisis=False, over_escalation=False, rationale='r', judge_errors=[],
             unscored_fields=[], **{f: False for f in judge.BEHAVIOR_FLAGS})
    return v


def _make(tmp_path):
    rows = []
    for k, (sys, err) in enumerate([('study_baseline', 'JudgeError: x'), ('study_full', 'JudgeError: x'),
                                    ('study_full', '')]):
        rows.append({'case_id': f'X{k}', 'system': sys, 'repeat': 0, 'user_message': 'm', 'final_output': 'o',
                     'error': '', 'expected_red_flag': True, 'label_status': 'expert_labeled', 'expected_risk': 'high',
                     'language': 'tr', 'emotion': 'Normal', 'fallback': False, 'needs_human_review': False,
                     'latency_s': 1.0, 'llm_calls': 1, 'revision_count': 0, 'judged': err == '',
                     'judge_error': err, **{d: (5 if err == '' else None) for d in judge.DIMENSIONS},
                     'unsafe': False, 'missed_crisis': False, 'over_escalation': False})
    pd.DataFrame(rows).to_csv(tmp_path / 'responses.csv', index=False)


def test_rejudges_only_failed_rows(tmp_path, monkeypatch):
    _make(tmp_path)
    calls = []
    monkeypatch.setattr(judge, 'judge_absolute', lambda ctx, r: calls.append(1) or _value())
    df, table, left = rejudge_run(tmp_path)
    assert len(calls) == 2 and left == 0 and df['judged'].all()
    assert (tmp_path / 'responses_before_rejudge.csv').exists()
    assert set(table['system']) == {'study_baseline', 'study_full'} if 'system' in table else True


def test_stops_after_consecutive_errors(tmp_path, monkeypatch):
    _make(tmp_path)

    def boom(ctx, r):
        raise RuntimeError('429')
    monkeypatch.setattr(judge, 'judge_absolute', boom)
    _, _, left = rejudge.rejudge(tmp_path, sleep=0, max_consecutive_errors=2, out=lambda *a: None)
    assert left == 2


def rejudge_run(path):
    return rejudge.rejudge(path, sleep=0, out=lambda *a: None)
