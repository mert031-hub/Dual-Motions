"""Synthetic pilot infrastructure tests. No real API access or human judgments."""
import json
from pathlib import Path

import pytest

import llm_factory
from llm_factory import bounded_invocations, InvocationBudgetExceeded
from slide_pilot import make_plan, prepare, run


def test_budget_stops_before_extra_invocation_and_disables_retries():
    calls = []
    def failed():
        calls.append(1)
        raise RuntimeError('private provider body')
    with bounded_invocations(2) as budget:
        with pytest.raises(RuntimeError):
            llm_factory.call_with_retry(failed, retries=10)
        assert len(calls) == 1
        assert llm_factory.call_with_retry(lambda: 'ok') == 'ok'
        with pytest.raises(InvocationBudgetExceeded):
            llm_factory.call_with_retry(lambda: calls.append(2))
        assert budget.exhausted and len(budget.attempts) == 2
        assert 'private provider body' not in json.dumps(budget.attempts)
    # Context is restored after exit, including exception paths.
    assert llm_factory.call_with_retry(lambda: 3) == 3


def test_actual_client_settings_cache_includes_scoped_limits(monkeypatch):
    import langchain_groq
    created = []
    class Client:
        def __init__(self, **kw):
            created.append(kw)
    monkeypatch.setattr(langchain_groq, 'ChatGroq', Client)
    llm_factory._cached_chat_model.cache_clear()
    first = llm_factory.get_chat_model('fixture-model', 0)
    with bounded_invocations(2, max_output_tokens=123, timeout_s=7):
        limited = llm_factory.get_chat_model('fixture-model', 0)
        assert limited is llm_factory.get_chat_model('fixture-model', 0)
    assert llm_factory.get_chat_model('fixture-model', 0) is first
    assert limited is not first
    assert created[1]['max_retries'] == 0 and created[1]['max_tokens'] == 123 and created[1]['timeout'] == 7
    assert 'max_tokens' not in created[0]
    llm_factory._cached_chat_model.cache_clear()


def test_plan_balance_is_authored_not_ground_truth_and_no_request_is_made(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_factory, 'get_chat_model', lambda *a, **k: pytest.fail('API called'))
    out, plan = prepare(tmp_path)
    assert plan['n_response_tasks'] == 20 and plan['n_primary_families'] == 1
    assert set(plan['author_condition_counts_not_gold'].values()) == {1}
    assert plan['clinical_metrics'] is None and not plan['independent_test']
    assert all(c['expected_red_flag'] is None for c in plan['scenarios'])
    public = json.loads((out/'reviewer/affect_packet.json').read_text(encoding='utf-8'))
    assert all(set(i) == {'item_id', 'user_message', 'message_sha256'} for i in public['items'])
    form = json.loads((out/'reviewer/affect_form_R1.json').read_text(encoding='utf-8'))
    assert all(r['emotion'] is None and r['status'] == 'pending' for r in form['ratings'])
    assert json.loads((out/'readiness.json').read_text(encoding='utf-8'))['provider_calls'] == 0
    for kwargs in ({'families': 3}, {'max_attempts': 0}, {'max_attempts': True}):
        with pytest.raises(ValueError):
            make_plan(**kwargs)


def test_offline_actual_four_arm_graph_is_not_exported_as_live_quality(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_factory, 'get_chat_model', lambda *a, **k: pytest.fail('API called'))
    out, checks = run(tmp_path)
    assert checks['infrastructure_checks_passed'] and checks['n_observed'] == 20
    assert checks['n_primary_records'] == 16 and checks['runnable_invocations'] == 32
    assert checks['gate_calls_zero'] and checks['gate_outputs_identical']
    assert checks['provider_calls'] == 0 and not checks['blinded_response_packet_exported']
    assert not (out/'reviewer/responses.json').exists()
    report = json.loads((Path(checks['run_dir'])/'research_report.json').read_text(encoding='utf-8'))
    assert report['H4_descriptive_emotion_groups'] == []
    assert report['status'] == 'offline_infrastructure_only'
    assert all(c['n'] == 0 for c in report['contrasts'].values())


def test_missing_key_or_denied_snapshot_blocks_live_without_partial_run(tmp_path, monkeypatch):
    import slide_pilot
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    with pytest.raises(ValueError, match='GROQ_API_KEY'):
        run(tmp_path, mode='live')
    monkeypatch.setenv('GROQ_API_KEY', 'fixture-not-a-real-key')
    monkeypatch.setattr(slide_pilot, 'network_snapshot', lambda: {'status': 'not_permitted_in_snapshot'})
    with pytest.raises(ValueError, match='network snapshot'):
        run(tmp_path, mode='live')
    assert not list(tmp_path.iterdir())


def test_blinded_live_packet_hides_predictions_and_author_conditions(backend, tmp_path, monkeypatch):
    import slide_pilot
    monkeypatch.setenv('GROQ_API_KEY', 'fixture-not-a-real-key')
    monkeypatch.setattr(slide_pilot, 'network_snapshot', lambda: {'status': 'permitted_in_snapshot'})
    out, checks = run(tmp_path, mode='live')  # scripted backend, not real model-quality evidence
    assert checks['infrastructure_checks_passed'] and checks['blinded_response_packet_exported']
    packet = json.loads((out/'reviewer/responses.json').read_text(encoding='utf-8'))
    mapping = json.loads((out/'private/response_mapping.json').read_text(encoding='utf-8'))
    assert len(packet['items']) == 16
    for item in packet['items']:
        assert set(item) == {'item_id', 'user_message', 'response', 'content_sha256'}
        meta = mapping['items'][item['item_id']]
        assert meta['family_id'] == 'pilot-family:presentation' and meta['triage_tier'] != 1
    assert not list((out/'reviewer').glob('*.mapping.json'))
    assert all(r['scores']['safety'] is None for r in json.loads((out/'reviewer/response_ratings_R1.json').read_text(encoding='utf-8'))['ratings'])


def test_exhausted_pilot_is_explicitly_incomplete_and_no_review_packet_is_exported(backend, tmp_path, monkeypatch):
    import slide_pilot
    monkeypatch.setenv('GROQ_API_KEY', 'fixture-not-a-real-key')
    monkeypatch.setattr(slide_pilot, 'network_snapshot', lambda: {'status': 'permitted_in_snapshot'})
    out, checks = run(tmp_path, mode='live', max_attempts=1)
    assert checks['budget_exhausted'] and not checks['infrastructure_checks_passed']
    assert checks['runnable_invocations'] == 1 and checks['n_response_errors'] > 0
    assert checks['gate_calls_zero']
    assert not (out/'reviewer/responses.json').exists()


def test_optional_judge_never_receives_model_emotion_as_reference(backend):
    import judge
    judge.judge_absolute({'user_message': 'Bugün gerginim.', 'emotion': 'UNVERIFIED_LABEL_DO_NOT_LEAK',
                          'emotion_source': 'model'}, 'Sizi duyuyorum.')
    prompt = backend.prompts('AbsoluteJudgment')[0]
    assert 'UNVERIFIED_LABEL_DO_NOT_LEAK' not in prompt
    assert 'circular evaluation' in prompt
