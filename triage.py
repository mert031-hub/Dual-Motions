"""Ön-trijaj: kural motoru çıktısını çoklu bayrak + eylem şemasına çevirir.

Eski sürümdeki sorunlar:
  * Birden fazla bayrak eşleşince sözlük sırasındaki İLK bayrak seçiliyordu (ciddiyete bakılmıyordu).
  * Eylemlerin çoğu aynı genel mesaja düşüyordu (ask_safety_question, urgent_* ayrışmıyordu).
  * Şiddet riski de intihar mesajını alıyordu.
  * Mesajlar sabit Türkçeydi.

Yeni şema iki mod içerir:
  canned : kullanıcıya doğrudan, deterministik (yerelleştirilmiş) mesaj gider; LLM çağrılmaz.
  guided : akış Policy'ye gider ama trijaj yönergeleri ZORUNLU içerik olarak eklenir ve Critic denetler.

Bilinmeyen bir eylem tipi gelirse güvenli tarafa düşülür (canned / urgent_professional).
Eylem->mod eşlemesi klinisyen onayına tabidir; yalnızca ACTION_SCHEMA değiştirilerek güncellenir.
"""
from typing import Any, Callable, Dict, List, Optional

from messages import get_directive, get_message
from red_flags import detect_red_flags

# eylem -> {mode, priority, message_key | directive_key}
ACTION_SCHEMA: Dict[str, Dict[str, Any]] = {
    "crisis_escalation": {"mode": "canned", "priority": 100, "message_key": "crisis_self_harm"},
    "urgent_professional_support": {"mode": "canned", "priority": 80, "message_key": "urgent_professional"},
    "urgent_medical_evaluation": {"mode": "canned", "priority": 70, "message_key": "urgent_medical"},
    "ask_safety_question": {"mode": "guided", "priority": 60, "directive_key": "ask_safety_question"},
    "medical_differential": {"mode": "guided", "priority": 50, "directive_key": "medical_differential"},
    "urgent_human_support": {"mode": "guided", "priority": 40, "directive_key": "urgent_human_support"},
}

# Belirli bayraklar için eylem şemasının üzerine yazılan özel durumlar.
FLAG_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "violence_risk": {"message_key": "crisis_violence", "priority": 95},
}

# Bilinmeyen eylem -> güvenli varsayılan
_UNKNOWN_ACTION = {"mode": "canned", "priority": 75, "message_key": "urgent_professional"}

_RISK_ORDER = {"low": 1, "medium": 2, "high": 3}


def _schema_for(flag: Dict[str, str]) -> Dict[str, Any]:
    schema = dict(ACTION_SCHEMA.get(flag["action"], _UNKNOWN_ACTION))
    schema.update(FLAG_OVERRIDES.get(flag["name"], {}))
    return schema


def run_triage(message: str, detector: Optional[Callable[[str], List[Dict[str, str]]]] = None) -> Dict[str, Any]:
    """Mesajı kurallara göre tarar ve yapılandırılmış trijaj sonucu döndürür.

    Dönen sözlük:
      flags            : eşleşen tüm bayraklar, ciddiyete göre sıralı (en ciddi ilk)
      tier             : 0 temiz, 1 acil/canned, 2 yönlendirmeli/guided
      canned_keys      : tier 1 için mesaj anahtarları (öncelik sırasıyla, tekrarsız)
      directive_keys   : tier 2 için yönerge anahtarları
      directives       : yönerge metinleri (Policy'ye ve Critic'e verilir)
      risk_level       : kuralların en yüksek risk seviyesi ('none'/'low'/'medium'/'high')
    """
    raw = (detector or detect_red_flags)(message or "")
    enriched: List[Dict[str, Any]] = []
    for flag in raw:
        schema = _schema_for(flag)
        item = dict(flag)
        item["mode"] = schema["mode"]
        item["priority"] = schema["priority"]
        item["message_key"] = schema.get("message_key")
        item["directive_key"] = schema.get("directive_key")
        enriched.append(item)

    enriched.sort(key=lambda f: f["priority"], reverse=True)

    canned = [f for f in enriched if f["mode"] == "canned"]
    guided = [f for f in enriched if f["mode"] == "guided"]

    canned_keys: List[str] = []
    for f in canned:
        if f["message_key"] and f["message_key"] not in canned_keys:
            canned_keys.append(f["message_key"])

    directive_keys: List[str] = []
    for f in guided:
        if f["directive_key"] and f["directive_key"] not in directive_keys:
            directive_keys.append(f["directive_key"])
    directives = [d for d in (get_directive(k) for k in directive_keys) if d]

    if canned:
        tier = 1
    elif guided:
        tier = 2
    else:
        tier = 0

    risk = "none"
    for f in enriched:
        if _RISK_ORDER.get(f.get("risk_level", ""), 0) > _RISK_ORDER.get(risk, 0):
            risk = f["risk_level"]

    return {
        "flags": enriched,
        "tier": tier,
        "canned_keys": canned_keys,
        "directive_keys": directive_keys,
        "directives": directives,
        "risk_level": risk,
    }


def build_canned_message(canned_keys: List[str], lang: str, max_parts: int = 2) -> str:
    """Birden fazla acil kategori varsa (örn. intihar + şiddet) en fazla `max_parts` mesajı birleştirir."""
    keys = canned_keys[:max_parts] or ["urgent_professional"]
    return "\n\n".join(get_message(k, lang) for k in keys)


def summarize_flags(flags: List[Dict[str, Any]]) -> str:
    if not flags:
        return "Yok"
    return "; ".join(f"{f['name']} ({f['description']})" for f in flags)
