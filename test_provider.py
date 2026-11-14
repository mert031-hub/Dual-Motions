"""Sağlayıcı seçimi (ağ çağrısı yok)."""
import pytest

import llm_factory


def test_varsayilan_groq(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert llm_factory._provider() == "groq"


def test_bilinmeyen_saglayici_hata_verir(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "baska")
    with pytest.raises(ValueError):
        llm_factory._provider()


def test_cerebras_istemcisi_olusur_ve_arac_cagirma_kullanir(monkeypatch):
    pytest.importorskip("langchain_openai")
    monkeypatch.setenv("LLM_PROVIDER", "cerebras")
    monkeypatch.setenv("CEREBRAS_API_KEY", "test-anahtari")
    llm_factory._cached_chat_model.cache_clear()
    from semantic_triage import SemanticTriageResult
    model = llm_factory.get_chat_model("gpt-oss-120b", 0.0)
    assert type(model).__name__ == "ChatOpenAI" and "cerebras" in str(model.openai_api_base)
    assert llm_factory.get_structured_model("gpt-oss-120b", 0.0, SemanticTriageResult) is not None
    llm_factory._cached_chat_model.cache_clear()


def test_anahtar_sonundaki_bosluk_temizlenir(monkeypatch):
    pytest.importorskip("langchain_openai")
    monkeypatch.setenv("LLM_PROVIDER", "cerebras")
    monkeypatch.setenv("CEREBRAS_API_KEY", "  test-anahtari \n")
    llm_factory._cached_chat_model.cache_clear()
    model = llm_factory.get_chat_model("gpt-oss-120b", 0.0)
    assert model.openai_api_key.get_secret_value() == "test-anahtari"
    llm_factory._cached_chat_model.cache_clear()


class _FakeChat:
    def __init__(self, reply):
        self.reply, self.seen, self.bound = reply, None, None

    def bind(self, **kw):
        self.bound = kw
        return self

    def invoke(self, messages):
        self.seen = messages
        from types import SimpleNamespace
        return SimpleNamespace(content=self.reply)


def test_json_mode_sarmalayici_semayi_prompta_ekler_ve_dogrular():
    from langchain_core.messages import HumanMessage, SystemMessage
    from semantic_triage import SemanticTriageResult
    chat = _FakeChat('```json\n{"risk_categories": [], "abstain": false, "confidence": "high"}\n```')
    out = llm_factory._JsonModeStructured(chat, SemanticTriageResult).invoke(
        [SystemMessage(content="SİSTEM"), HumanMessage(content="mesaj")])
    assert out.abstain is False and chat.bound == {"response_format": {"type": "json_object"}}
    assert "JSON Schema" in chat.seen[0].content and chat.seen[0].content.startswith("SİSTEM")
    assert chat.seen[1].content == "mesaj"


def test_json_mode_uymayan_cikti_sessizce_duzeltilmez():
    from langchain_core.messages import HumanMessage, SystemMessage
    from pydantic import ValidationError
    from semantic_triage import SemanticTriageResult
    chat = _FakeChat('{"context": {"events": [{"evidence": [{"quote": "x"}]}]}}')
    with pytest.raises(ValidationError):
        llm_factory._JsonModeStructured(chat, SemanticTriageResult).invoke(
            [SystemMessage(content="s"), HumanMessage(content="m")])
