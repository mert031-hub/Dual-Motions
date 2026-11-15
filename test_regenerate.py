import json

import pandas as pd

import regenerate


def _setup(tmp_path, monkeypatch):
    rows = [{'case_id': 'X001', 'system': 'study_baseline', 'repeat': 0, 'user_message': 'm', 'final_output': 'ok',
             'error': '', 'judged': False},
            {'case_id': 'X002', 'system': 'study_full', 'repeat': 0, 'user_message': 'm', 'final_output': '',
             'error': 'policy: OpenAIRateLimitError', 'judged': False},
            {'case_id': 'X003', 'system': 'study_full', 'repeat': 0, 'user_message': 'm', 'final_output': '',
             'error': 'critic: OpenAIRateLimitError', 'judged': False}]
    pd.DataFrame(rows).to_csv(tmp_path / 'responses.csv', index=False)
    (tmp_path / 'manifest.json').write_text(json.dumps({'n_response_errors': 2}), encoding='utf-8')
    monkeypatch.setattr(regenerate, 'load_cases', lambda **k: [
        {'id': i, 'user_message': f'msg {i}', 'emotion': 'Normal / Sakin'} for i in ('X001', 'X002', 'X003')])


def test_regenerates_only_failed_rows(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    calls = []

    def fake(msg, emo, mode, ctx, system, affect_mode='manual'):
        calls.append(msg)
        return {'final_output': 'yeni', 'critic_decision': 'Onaylandı', 'llm_calls': 2}
    monkeypatch.setattr(regenerate, 'run_pipeline', fake)
    df, left = regenerate.regenerate(tmp_path, sleep=0, out=lambda *a: None)
    assert calls == ['msg X002', 'msg X003'] and left == 0
    assert list(df['final_output']) == ['ok', 'yeni', 'yeni']
    assert json.loads((tmp_path / 'manifest.json').read_text())['n_response_errors'] == 0
    assert (tmp_path / 'responses_before_regenerate.csv').exists()


def test_stops_after_consecutive_errors(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(regenerate, 'run_pipeline',
                        lambda *a, **k: {'error': 'policy: OpenAIRateLimitError', 'final_output': ''})
    _, left = regenerate.regenerate(tmp_path, sleep=0, max_consecutive_errors=1, out=lambda *a: None)
    assert left == 2
