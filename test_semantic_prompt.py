"""Semantik prompt, doğrulayıcının zorunlu kıldığı çıktı biçimini model'e açıkça söylemeli (API yok)."""
import llm_factory
import semantic_triage as st
from context_schema import ContextEvent


def test_prompt_names_evidence_keys_and_offset_rule(monkeypatch):
    seen = {}

    class Fake:
        def invoke(self, messages):
            seen['prompt'] = messages[0].content
            return st.SemanticTriageResult()

    monkeypatch.setattr(llm_factory, 'get_structured_model', lambda *a, **k: Fake())
    st.classify('Bugün biraz yorgunum.')
    prompt = seen['prompt']
    for field in ContextEvent.model_fields:
        if field != 'evidence':
            assert field in prompt
    assert 'subject and time' in prompt and 'omit start and end' in prompt
