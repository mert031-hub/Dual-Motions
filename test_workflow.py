import config
import messages
import workflow
from conftest import approve, reject
from workflow import run_pipeline

CLEAN = "Bugün işte çok yoruldum ve canım sıkkın."
CRISIS = "Kendimi öldüreceğim, karar verdim."
PASSIVE = "Keşke sabah uyanmasam."


def test_full_pipeline_approves(backend):
    backend.policy = ["Yorgun hissetmeniz çok anlaşılır."]
    r = run_pipeline(CLEAN, mode="full")
    assert r["final_output"] == "Yorgun hissetmeniz çok anlaşılır."
    assert r["critic_decision"] == "Onaylandı"
    assert r["revision_count"] == 0 and r["llm_calls"] == 2 and not r["error"]
    assert backend.kinds() == ["policy", "CriticEvaluation"]


def test_canned_triage_short_circuits_without_any_llm_call(backend):
    r = run_pipeline(CRISIS, mode="full")
    assert backend.calls == []                       # LLM hiç çağrılmadı
    assert r["triage_decision"] == "Acil Trijaj" and r["triage_tier"] == 1
    assert "112" in r["final_output"] and r["needs_human_review"]


def test_english_crisis_not_detected_by_turkish_rules_but_critic_flags_miss(backend):
    """Kural motoru Türkçe: İngilizce kriz kaçar. Critic yüksek risk görürse 'olası trijaj kaçağı' işaretlenir."""
    backend.policy = ["I'm here with you. Are you thinking about ending your life?"]
    backend.critic = [approve(risk_level="Kritik (Kırmızı Bayrak)", detected_language="English")]
    r = run_pipeline("I'm going to kill myself tonight.", mode="full")
    assert r["triage_flags"] == [] and r["triage_miss_suspected"] is True


def test_revise_then_approve_uses_revision_notes(backend):
    backend.policy = ["- madde 1\n- madde 2", "Sizi dinliyorum."]
    backend.critic = [reject(), approve()]
    r = run_pipeline(CLEAN, mode="full")
    assert r["final_output"] == "Sizi dinliyorum."
    assert r["revision_count"] == 1 and len(r["revision_log"]) == 2
    second_policy_prompt = backend.prompts("policy")[1]
    assert "Madde işaretlerini kaldır." in second_policy_prompt and "unsolicited_advice" in second_policy_prompt


def test_three_rejections_do_not_auto_approve(backend):
    """Eski hata: 3 ret sonrası denetlenmemiş taslak 'Onaylandı' oluyordu."""
    backend.policy = ["taslak A", "taslak B", "taslak C", "taslak D"]
    backend.critic = [reject()]                      # her seferinde reddeder
    r = run_pipeline(CLEAN, mode="full")
    drafts = {"taslak A", "taslak B", "taslak C", "taslak D"}
    assert r["final_output"] not in drafts
    assert r["final_output"] == messages.get_message("safe_fallback", "tr")
    assert r["critic_decision"] == "Güvenli Yedek" and r["needs_human_review"]
    assert r["revision_count"] == config.MAX_REVISIONS
    # MAX_REVISIONS = izin verilen ret sayısı: her taslak denetlendi, 3. retten sonra güvenli yedeğe düşüldü
    assert backend.kinds().count("CriticEvaluation") == config.MAX_REVISIONS
    assert backend.kinds().count("policy") == config.MAX_REVISIONS
    assert "taslak D" not in {p for p in backend.prompts("CriticEvaluation") if "taslak D" in p}


def test_policy_failure_returns_safe_message_not_exception(backend):
    backend.policy = [RuntimeError("groq down")]
    r = run_pipeline(CLEAN, mode="full")
    assert r["error"].startswith("policy:") and r["needs_human_review"]
    assert r["final_output"] == messages.get_message("technical_error", "tr")
    assert "CriticEvaluation" not in backend.kinds()


def test_critic_failure_is_fail_closed(backend):
    backend.policy = ["Taslak"]
    backend.critic = [ValueError("şema doğrulanamadı")]
    r = run_pipeline(CLEAN, mode="full")
    assert r["critic_decision"] == "Güvenli Yedek" and r["error"].startswith("critic:")
    assert r["final_output"] != "Taslak"
    assert r["final_output"] == messages.get_message("technical_error", "tr")


def test_critic_prompt_contains_patient_message_history_and_directives(backend):
    backend.policy = ["Nasıl hissettiğinizi duyuyorum. Kendinizi öldürmeyi düşünüyor musunuz?"]
    run_pipeline(PASSIVE, chat_history="Patient: Merhaba\nAssistant: Buradayım.", mode="full")
    prompt = backend.prompts("CriticEvaluation")[0]
    assert PASSIVE in prompt                            # hasta mesajı
    assert "Patient: Merhaba" in prompt                 # geçmiş
    assert "passive_death_wish" in prompt               # trijaj bayrağı
    assert "exactly ONE direct" in prompt               # zorunlu yönerge
    assert "Nasıl hissettiğinizi duyuyorum" in prompt   # taslak


def test_guided_directive_reaches_policy_prompt(backend):
    run_pipeline(PASSIVE, mode="full")
    assert "exactly ONE direct" in backend.prompts("policy")[0]


def test_contradictory_critic_output_is_rejected(backend):
    """decision='Onaylandı' ama ihlal listesi dolu => reddedilmeli."""
    backend.policy = ["Bırakmanızı öneririm.", "Doktorunuzla konuşun."]
    backend.critic = [approve(violated_criteria=["medication_advice"]), approve()]
    r = run_pipeline(CLEAN, mode="full")
    assert r["revision_count"] == 1 and r["final_output"] == "Doktorunuzla konuşun."


def test_mode_triage_only_skips_critic(backend):
    backend.policy = ["Sizi dinliyorum."]
    r = run_pipeline(CLEAN, mode="triage_only")
    assert "CriticEvaluation" not in backend.kinds()
    assert r["final_output"] == "Sizi dinliyorum." and r["critic_decision"].startswith("Atlandı")


def test_mode_triage_only_still_triages(backend):
    r = run_pipeline(CRISIS, mode="triage_only")
    assert backend.calls == [] and "112" in r["final_output"]


def test_mode_critic_only_skips_triage(backend):
    backend.policy = ["Buradayım."]
    r = run_pipeline(CRISIS, mode="critic_only")
    assert r["triage_decision"] == "Atlandı" and r["triage_flags"] == []
    assert backend.kinds() == ["policy", "CriticEvaluation"]


def test_mode_vanilla_uses_plain_llm_only(backend):
    r = run_pipeline(CRISIS, mode="vanilla")
    assert backend.kinds() == ["vanilla"] and r["final_output"] == "Yalın yanıt."


def test_mode_policy_only(backend):
    r = run_pipeline(CRISIS, mode="policy_only")
    assert backend.kinds() == ["policy"] and r["triage_decision"] == "Atlandı"


def test_vanilla_error_is_reported_not_raised(backend):
    backend.vanilla = [RuntimeError("timeout")]
    r = run_pipeline(CLEAN, mode="vanilla")
    assert r["error"].startswith("pipeline:") and r["final_output"] == ""


def test_empty_input(backend):
    r = run_pipeline("   ", mode="full")
    assert r["error"] == "empty_input" and backend.calls == []


def test_pipeline_never_raises_even_if_graph_explodes(backend, monkeypatch):
    class ExplodingGraph:
        def invoke(self, *a, **k):
            raise RuntimeError("graf çöktü")
    monkeypatch.setattr(workflow, "graph_app", ExplodingGraph())
    r = run_pipeline(CLEAN, mode="full")
    assert r["error"].startswith("pipeline:") and r["final_output"] == messages.get_message("technical_error", "tr")


def test_unknown_mode_raises():
    import pytest
    with pytest.raises(ValueError):
        run_pipeline("x", mode="nope")


def test_input_is_truncated(backend, monkeypatch):
    monkeypatch.setattr(config, "MAX_INPUT_CHARS", 20)
    run_pipeline("a" * 500, mode="vanilla")
    assert backend.calls  # çalıştı; kesme hata üretmedi


def test_format_history_excludes_nothing_and_windows():
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(30)]
    text = workflow.format_history(msgs, window=3)
    assert text.splitlines() == ["Patient: m27", "Patient: m28", "Patient: m29"]
    assert workflow.format_history([], window=3) == ""
