"""Sabit (deterministik) kullanıcı mesajları, Policy yönergeleri ve dil yardımcıları.

ÖNEMLİ: Buradaki kriz/yönlendirme metinleri TASLAKTIR. Gerçek kullanımdan önce
klinisyen tarafından onaylanmalı ve hedef ülkenin acil numaralarıyla eşleştirilmelidir.
Şu an yalnızca Türkçe (tr) ve İngilizce (en) metinler vardır; diğer diller İngilizceye düşer.
"""
import re
from typing import Dict, List, Optional

# ------------------------------------------------------------------
# Dil normalizasyonu
# ------------------------------------------------------------------
_LANG_MAP = {
    "turkish": "tr", "türkçe": "tr", "tr": "tr",
    "english": "en", "ingilizce": "en", "en": "en",
    "russian": "ru", "ru": "ru",
    "german": "de", "de": "de",
    "french": "fr", "fr": "fr",
    "spanish": "es", "es": "es",
}

_TR_CHARS = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
_TR_WORDS = re.compile(
    r"\b(ve|bir|bu|değil|ben|çok|için|ama|keşke|artık|yok|var|gibi|daha|şu|ne|"
    r"kendimi|istiyorum|yapamıyorum|hiç|sanki|yine|bugün|beni|bana)\b",
    re.IGNORECASE,
)
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def detect_language_simple(text: str) -> str:
    """Hafif sezgisel dil tahmini (tr/ru/en). Üretim için gerçek bir dil tespiti gerekir."""
    if not text:
        return "en"
    if _CYRILLIC.search(text):
        return "ru"
    tr_hits = len(_TR_CHARS.findall(text)) + len(_TR_WORDS.findall(text))
    return "tr" if tr_hits >= 1 else "en"


def normalize_language(target_language: Optional[str], text: str = "") -> str:
    """'Auto-Detect' veya dil adını iki harfli koda çevirir."""
    if not target_language or target_language.strip().lower() in ("auto-detect", "auto", ""):
        return detect_language_simple(text)
    return _LANG_MAP.get(target_language.strip().lower(), "en")


# ------------------------------------------------------------------
# Sabit mesajlar  (anahtar -> dil -> metin)
# ------------------------------------------------------------------
MESSAGES: Dict[str, Dict[str, str]] = {
    "crisis_self_harm": {
        "tr": (
            "Şu an çok zor bir şeyden geçtiğinizi duyuyorum ve bunu benimle paylaştığınız için teşekkür ederim. "
            "Güvenliğiniz benim için çok önemli. Kendinize zarar verme ihtimali varsa ya da şu an güvende "
            "hissetmiyorsanız lütfen hemen 112 Acil Çağrı Merkezi'ni arayın veya en yakın acil servise gidin. "
            "Mümkünse güvendiğiniz birine haber verin ve yalnız kalmamaya çalışın. "
            "Ben bir yapay zekâ asistanıyım; acil durumda bir hekimin veya kriz ekibinin yerini tutamam."
        ),
        "en": (
            "I hear that you are going through something very hard, and I'm glad you told me. "
            "Your safety matters. If there is any chance you might hurt yourself, or you don't feel safe right now, "
            "please call your local emergency number now (for example 112 in Europe/Türkiye, 911 in the US; "
            "in the US you can also call or text 988) or go to the nearest emergency department. "
            "If you can, tell someone you trust and try not to be alone. "
            "I'm an AI assistant and can't replace a clinician or a crisis team in an emergency."
        ),
    },
    "crisis_violence": {
        "tr": (
            "Çok yoğun bir öfke ve baskı altında olduğunuzu duyuyorum. Birine ya da kendinize zarar verme riski "
            "varsa lütfen önce ortamdan uzaklaşın, güvenli bir yere geçin ve 112'yi arayın. "
            "Mümkünse güvendiğiniz biriyle iletişime geçin. Ben bir yapay zekâ asistanıyım; "
            "acil durumda bir hekimin veya kriz ekibinin yerini tutamam."
        ),
        "en": (
            "I hear how intense the anger and pressure are right now. If there is a risk that you might hurt someone "
            "or yourself, please first step away, move to a safe place and call your local emergency number "
            "(for example 112 in Europe/Türkiye, 911 in the US). If you can, contact someone you trust. "
            "I'm an AI assistant and can't replace a clinician or a crisis team in an emergency."
        ),
    },
    "urgent_professional": {
        "tr": (
            "Anlattığınız belirtiler (örneğin sesler duymak, gerçeklikten kopma hissi veya yoksunluk) bir sağlık "
            "uzmanı tarafından en kısa sürede değerlendirilmesi gereken durumlar olabilir. Lütfen bugün bir "
            "psikiyatri polikliniğine/acil servise ya da hekiminize başvurun. Kendinizi güvende hissetmiyorsanız "
            "112'yi arayın. Yanınızda güvendiğiniz birinin olması iyi olur."
        ),
        "en": (
            "What you describe (for example hearing voices, losing touch with reality, or withdrawal) may need "
            "to be assessed by a health professional soon. Please contact a psychiatric service, an emergency "
            "department or your doctor today. If you don't feel safe, call your local emergency number "
            "(112 in Europe/Türkiye, 911 in the US). It would help to have someone you trust with you."
        ),
    },
    "urgent_medical": {
        "tr": (
            "Beslenme veya sıvı alımınızla ilgili anlattıklarınız tıbbi olarak acil değerlendirme gerektirebilir. "
            "Lütfen bugün bir sağlık kuruluşuna başvurun. Çok halsizseniz, başınız dönüyorsa ya da bayılacak gibi "
            "hissediyorsanız 112'yi arayın."
        ),
        "en": (
            "What you describe about eating or drinking may need urgent medical assessment. Please contact a "
            "health service today. If you feel very weak, dizzy or faint, call your local emergency number "
            "(112 in Europe/Türkiye, 911 in the US)."
        ),
    },
    "safe_fallback": {
        "tr": (
            "Bu mesajınıza şu an güvenilir bir yanıt veremiyorum; dikkatle ele alınması gereken bir durum olabilir. "
            "Yaşadıkları sizi zorluyorsa lütfen güvendiğiniz biriyle ya da bir sağlık uzmanıyla konuşun. "
            "Acil bir tehlike varsa 112'yi arayın."
        ),
        "en": (
            "I can't give a reliably safe answer to this message right now; it may need careful attention. "
            "If what you're going through is hard, please talk to someone you trust or a health professional. "
            "If you are in immediate danger, call your local emergency number (112 in Europe/Türkiye, 911 in the US)."
        ),
    },
    "technical_error": {
        "tr": (
            "Teknik bir sorun nedeniyle şu an yanıt veremiyorum. Lütfen biraz sonra tekrar deneyin. "
            "Acil bir durumdaysanız beklemeden 112'yi arayın."
        ),
        "en": (
            "I can't respond right now because of a technical problem. Please try again shortly. "
            "If this is an emergency, call your local emergency number (112 in Europe/Türkiye, 911 in the US) right away."
        ),
    },
    "empty_input": {
        "tr": "Mesajınız boş görünüyor. Dilerseniz yazmaya devam edebilirsiniz.",
        "en": "Your message seems to be empty. Feel free to keep writing.",
    },
}


def get_message(key: str, lang: str = "en") -> str:
    table = MESSAGES.get(key) or MESSAGES["technical_error"]
    return table.get(lang) or table["en"]


# ------------------------------------------------------------------
# Yönlendirmeli (guided) trijaj yönergeleri.
# Policy'ye "zorunlu içerik" olarak verilir, Critic bunları denetler.
# ------------------------------------------------------------------
DIRECTIVES: Dict[str, str] = {
    "ask_safety_question": (
        "The patient may be expressing passive thoughts of death or hopelessness. Reflect their feelings briefly "
        "and warmly, then ask a direct, non-judgmental question about whether they are having thoughts "
        "of ending their life or hurting themselves. Do not minimize, do not give advice lists, do not diagnose."
    ),
    "medical_differential": (
        "The patient mentions a medication, medical or neurological condition that may be linked to mood "
        "symptoms. Validate their experience and say gently that such symptoms can sometimes be related to the "
        "condition or medication and are worth discussing soon with their treating physician. NEVER tell them to "
        "stop, reduce or change a medication. Do not diagnose."
    ),
    "urgent_human_support": (
        "The patient describes severe self-neglect or loss of daily functioning. Use warm, simple language, avoid "
        "long advice lists, gently encourage reaching a trusted person or health professional soon, and ask "
        "whether someone nearby could help them today."
    ),
    "uncertain_check_in": (
        "The message may contain a risk signal that is ambiguous, refers to the past, is hypothetical, concerns "
        "another person, or could not be assessed reliably. Respond warmly to what the patient said, do not assume "
        "the worst and do not dismiss it, and ask a brief, non-leading question relevant to their current safety or needs "
        "right now. For unwanted intrusive thoughts, distinguish intent from feared content without declaring safety or diagnosing OCD. Do not assume third-party events happened to the speaker. Do not diagnose."
    ),
}


def get_directive(key: str) -> Optional[str]:
    return DIRECTIVES.get(key)


def all_directive_keys() -> List[str]:
    return list(DIRECTIVES.keys())
