import pytest

from messages import detect_language_simple, get_message, normalize_language
from red_flags import _fold, detect_red_flags
from triage import build_canned_message, run_triage


@pytest.mark.parametrize("text", [
    "İntihar edeceğim",            # büyük noktalı İ (eski _fold hatası)
    "KEŞKE SABAH UYANMASAM",       # tamamı büyük harf, I/İ karışık
    "keşke   sabah\tuyanmasam",    # fazla boşluk
    "Keşke sabah uyanmasam.",
])
def test_fold_handles_turkish_casing_and_whitespace(text):
    assert detect_red_flags(text), f"yakalanmalıydı: {text}"


def test_fold_basic():
    assert _fold("İŞE GİDEMİYORUM") == "ise gidemiyorum"
    assert _fold("ığüşöç") == "igusoc"


def test_clean_message_has_no_flags():
    r = run_triage("Bugün hava çok güzel, parkta yürüdüm.")
    assert r["tier"] == 0 and r["flags"] == [] and r["risk_level"] == "none"


def test_multiple_flags_sorted_by_severity_not_dict_order():
    r = run_triage("Sesler duyuyorum ve kendimi öldüreceğim")
    names = [f["name"] for f in r["flags"]]
    assert names[0] == "active_self_harm"          # en ciddi önce
    assert "psychosis" in names
    assert r["canned_keys"] == ["crisis_self_harm", "urgent_professional"]
    assert r["tier"] == 1


def test_violence_gets_its_own_message():
    r = run_triage("Onu öldüreceğim")
    assert r["canned_keys"][0] == "crisis_violence"


def test_passive_death_is_guided_not_canned():
    r = run_triage("Keşke sabah uyanmasam")
    assert r["tier"] == 2
    assert r["canned_keys"] == []
    assert r["directive_keys"] == ["ask_safety_question"]
    assert "ONE direct" in r["directives"][0]


def test_medication_flag_is_guided_with_no_stop_medication_rule():
    r = run_triage("Yüksek doz prednizolon başladığımdan beri ağlıyorum")
    assert r["tier"] == 2
    assert "NEVER tell them to stop" in r["directives"][0]


def test_unknown_action_fails_safe_to_escalation():
    def det(_):
        return [{"name": "yeni", "description": "d", "risk_level": "high", "action": "mystery", "matched_keyword": "k"}]
    r = run_triage("x", detector=det)
    assert r["tier"] == 1 and r["canned_keys"] == ["urgent_professional"]


def test_canned_message_language_and_fallback():
    tr = build_canned_message(["crisis_self_harm"], "tr")
    en = build_canned_message(["crisis_self_harm"], "en")
    de = build_canned_message(["crisis_self_harm"], "de")  # İngilizceye düşer
    assert "112" in tr and "988" in en and de == en


def test_canned_message_joins_at_most_two():
    msg = build_canned_message(["crisis_self_harm", "crisis_violence", "urgent_professional"], "en")
    assert msg.count("\n\n") == 1


def test_language_normalization():
    assert normalize_language("Auto-Detect", "Kendimi çok kötü hissediyorum") == "tr"
    assert normalize_language("Auto-Detect", "I feel terrible today") == "en"
    assert normalize_language("Auto-Detect", "Мне очень плохо") == "ru"
    assert normalize_language("Turkish", "anything") == "tr"
    assert normalize_language("Spanish", "x") == "es"
    assert detect_language_simple("") == "en"


def test_get_message_unknown_key_is_safe():
    assert "112" in get_message("does_not_exist", "tr")
