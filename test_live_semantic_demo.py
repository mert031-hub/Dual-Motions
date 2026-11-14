import json

import pytest

from live_semantic_demo import run_demo, setup_check


def test_setup_check_and_missing_key_do_not_call_provider(monkeypatch, tmp_path):
    import llm_factory
    monkeypatch.setattr(llm_factory, 'get_chat_model', lambda *a, **k: pytest.fail('Unexpected provider access'))
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    check = setup_check()
    assert check['provider_calls'] == 0 and check['key_variable_present'] is False
    assert check['authentication_verified'] is False
    with pytest.raises(ValueError, match='GROQ_API_KEY'):
        run_demo(tmp_path)
    assert not list(tmp_path.iterdir())


def test_opt_in_demo_records_errors_and_canned_bypasses_without_text_or_secrets(backend, monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, 'STRUCTURED_RETRIES', 0)
    monkeypatch.setenv('GROQ_API_KEY', 'private-test-fixture-key')
    backend.semantic = [RuntimeError('private-provider-response')]
    out, report = run_demo(tmp_path)
    assert len(report['rows']) == 4 and report['n_attempted_examples'] == 2
    assert report['n_errors'] == 2 and report['clinical_metrics'] is None
    assert report['execution_mode'] == 'live'
    assert backend.kinds().count('SemanticTriageResult') == 2
    disk = (out/'report.json').read_text(encoding='utf-8')
    assert 'private-test-fixture-key' not in disk and 'private-provider-response' not in disk
    assert 'Geçen yıl' not in disk
    assert all(r['triage_tier'] == 1 for r in report['rows'] if not r['semantic_attempted'])
    assert json.loads(disk)['status'] == 'live_synthetic_demo_not_clinical_validation'
