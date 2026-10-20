from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app_auth import hash_password, verify_password

ROOT = Path(__file__).resolve().parent


def test_password_gate_rejects_missing_hash_before_rendering_app(monkeypatch):
    monkeypatch.setenv('APP_REQUIRE_AUTH', '1')
    monkeypatch.delenv('APP_PASSWORD_HASH', raising=False)
    app = AppTest.from_file(str(ROOT/'app.py')).run()
    assert not app.exception
    assert any('APP_PASSWORD_HASH' in e.value for e in app.error)
    assert not app.chat_input


def test_local_app_renders_rule_metrics_and_crisis_without_api(backend, monkeypatch, tmp_path):
    import research_privacy
    monkeypatch.setenv('APP_REQUIRE_AUTH', '0')
    monkeypatch.delenv('APP_PASSWORD_HASH', raising=False)
    monkeypatch.setattr(research_privacy, 'DATA_DIR', tmp_path)
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=15).run()
    assert not app.exception
    app = next(b for b in app.button if b.label == 'Trijaj metriklerini hesapla').click().run()
    assert not app.exception and app.dataframe
    # Disable the additional vanilla/judge comparison: this test is for emergency routing.
    for checkbox in app.checkbox:
        if checkbox.label.startswith('Canlı kör karşılaştırma'):
            checkbox.set_value(False)
    app = app.chat_input[0].set_value('Kendimi öldüreceğim.').run()
    assert not app.exception
    assert app.session_state['turn']['result']['triage_tier'] == 1
    assert backend.calls == []
    app = next(b for b in app.button if b.label == 'Tüm Sohbeti ve Analizi Temizle').click().run()
    assert not app.exception and app.session_state['messages'] == []


def test_review_app_does_not_expose_system_mapping(monkeypatch):
    monkeypatch.setenv('APP_REQUIRE_AUTH', '0')
    monkeypatch.delenv('APP_PASSWORD_HASH', raising=False)
    app = AppTest.from_file(str(ROOT/'review_app.py')).run()
    assert not app.exception
    assert not app.chat_input and not app.selectbox


def test_password_hash_verifies_correct_password_and_fails_on_bad_configuration():
    encoded = hash_password('test-fixture-only')
    assert verify_password('test-fixture-only', encoded)
    assert not verify_password('wrong', encoded)
    assert not verify_password('anything', 'pbkdf2_sha256$1$ab$cd')
    assert not verify_password('anything', 'malformed')
