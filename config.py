"""Merkezi yapılandırma: model adları, limitler, sistem (ablation) tanımları, sürüm bilgisi.

Tüm değerler ortam değişkeni (.env) ile ezilebilir. Bu dosya import edildiğinde
API anahtarı GEREKMEZ; modeller yalnızca ilk kullanımda (llm_factory) oluşturulur.
"""
import os
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------
# Modeller
# ------------------------------------------------------------------
MODEL_NAME: str = os.getenv("MODEL_NAME", "openai/gpt-oss-120b")

POLICY_TEMPERATURE: float = _float("POLICY_TEMPERATURE", 0.6)
VANILLA_TEMPERATURE: float = _float("VANILLA_TEMPERATURE", 0.7)
CRITIC_TEMPERATURE: float = _float("CRITIC_TEMPERATURE", 0.1)
JUDGE_TEMPERATURE: float = _float("JUDGE_TEMPERATURE", 0.0)

# Yargıç modelleri (virgülle ayrılmış). Üretimle AYNI model ailesi kendi çıktısını
# kayırabilir; bağımsız bir aileden en az bir yargıç eklemeniz önerilir, örn:
#   JUDGE_MODELS=openai/gpt-oss-120b,llama-3.3-70b-versatile
JUDGE_MODELS: List[str] = [
    m.strip() for m in os.getenv("JUDGE_MODELS", MODEL_NAME).split(",") if m.strip()
]

# ------------------------------------------------------------------
# Güvenilirlik / limitler
# ------------------------------------------------------------------
REQUEST_TIMEOUT: int = _int("REQUEST_TIMEOUT", 45)   # saniye
MAX_RETRIES: int = _int("MAX_RETRIES", 2)            # ChatGroq HTTP yeniden denemeleri
STRUCTURED_RETRIES: int = _int("STRUCTURED_RETRIES", 1)  # şema doğrulama hatasında ek deneme
MAX_REVISIONS: int = _int("MAX_REVISIONS", 3)        # Critic'in verebileceği en fazla RET sayısı; aşılırsa güvenli yedek mesaj
MAX_INPUT_CHARS: int = _int("MAX_INPUT_CHARS", 4000)
HISTORY_WINDOW: int = _int("HISTORY_WINDOW", 10)     # Policy/Critic'e verilen son mesaj sayısı

# ------------------------------------------------------------------
# Sürümleme (deney kayıtları için)
# ------------------------------------------------------------------
PROMPT_VERSION: str = "2026.10.v2"
CODE_VERSION: str = "v2-faz1-faz2"

# ------------------------------------------------------------------
# Sistem kolları (ablation).  Word taslağındaki A/B/C/D + ek kontrol kolu.
#   use_triage : kural tabanlı ön-trijaj açık mı
#   use_critic : Critic denetimi + revizyon döngüsü açık mı
#   use_policy : Policy (klinik sistem prompt'u) kullanılıyor mu (False => ham LLM)
# ------------------------------------------------------------------
SYSTEMS: Dict[str, Dict[str, object]] = {
    "vanilla": {
        "label": "A: Vanilla",
        "use_triage": False, "use_critic": False, "use_policy": False,
    },
    "triage_only": {
        "label": "B: Triage Only",
        "use_triage": True, "use_critic": False, "use_policy": True,
    },
    "critic_only": {
        "label": "C: Critic Only",
        "use_triage": False, "use_critic": True, "use_policy": True,
    },
    "full": {
        "label": "D: Full Architecture",
        "use_triage": True, "use_critic": True, "use_policy": True,
    },
    # Ek kontrol kolu: Policy prompt'unun tek başına etkisini ayırır
    # (A'ya göre kazanç prompt'tan mı, mimariden mi?).
    "policy_only": {
        "label": "Kontrol: Policy Only",
        "use_triage": False, "use_critic": False, "use_policy": True,
    },
}

DEFAULT_ABLATION_SYSTEMS: List[str] = ["vanilla", "triage_only", "critic_only", "full"]

# ------------------------------------------------------------------
# Duygu durumu -> iletişim yönergesi (TASLAK: klinisyen onayı gerekir)
# ------------------------------------------------------------------
EMOTION_GUIDANCE: Dict[str, str] = {
    "Normal / Sakin": "Keep a warm, natural, conversational tone.",
    "Üzgün": "Be gentle and validating; reflect the feeling; avoid cheerleading and quick fixes.",
    "Kaygılı": "Be calm and grounding; use short, steady sentences; do not amplify worry or use alarming medical terms.",
    "Öfkeli": "De-escalate: stay calm, acknowledge the anger without agreeing with harmful ideas, avoid advice lists, bullet points and 'calm down' phrasing.",
}
