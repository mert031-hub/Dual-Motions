"""Egitim amacli klinik depresyon kirmizi bayrak kurallari."""
from typing import Dict, List

RED_FLAG_RULES: Dict[str, Dict[str, object]] = {
    "active_self_harm": {"description": "Aktif intihar veya kendine zarar verme niyeti/plani", "risk_level": "high", "keywords": ["kendime zarar verecegim", "intihar edecegim", "kendimi oldurecegim", "yogun intihar dusunceleri"], "action": "crisis_escalation"},
    "passive_death_wish": {"description": "Pasif olum veya ozkiyim dusuncesi", "risk_level": "medium", "keywords": ["keske sabah uyanmasam", "her sey sona erse", "yasamanin hicbir anlami yok", "ben de onun yanina gitmeliyim"], "action": "ask_safety_question"},
    "psychosis": {"description": "Psikoz veya gercegi degerlendirme bozuklugu", "risk_level": "high", "keywords": ["sesler duyuyorum", "organlarim curudu", "nihilistik sanri", "deluzyon", "halusinasyon"], "action": "urgent_professional_support"},
    "severe_self_neglect": {"description": "Agir oz bakim, beslenme veya sivi ihmali", "risk_level": "high", "keywords": ["gunlerdir yemek yemiyorum", "su icmiyorum", "banyo yapamiyorum", "dislerimi fircalayamiyorum", "oz bakimini tamamen aksatmis"], "action": "urgent_human_support"},
    "violence_risk": {"description": "Baskasina zarar verme veya kontrol edilemeyen siddet riski", "risk_level": "high", "keywords": ["onu oldurecegim", "ona zarar verecegim", "birine saldiracagim", "masayi devirdim", "kitaplari firlattim", "ofke patlamalari"], "action": "crisis_escalation"},
    "substance_withdrawal": {"description": "Madde yoksunlugu veya depresif crash", "risk_level": "high", "keywords": ["kokaini biraktim", "maddeyi biraktiktan sonra", "yoksunluk yasiyorum", "crash"], "action": "urgent_professional_support"},
    "medication_or_organic_cause": {"description": "Ilac, endokrin, norolojik veya malignite kaynakli olasi tablo", "risk_level": "high", "keywords": ["prednizolon", "kortikosteroid", "interferon-alfa", "propranolol", "izotretinoin", "hipotiroidi", "inme sonrasi", "parkinson", "cushing", "pankreas adenokarsinomu"], "action": "medical_differential"},
    "catatonia_or_stupor": {"description": "Agir psikomotor yavaslama veya katatoni riski", "risk_level": "high", "keywords": ["fisilti duzeyinde", "psikomotor retardasyon", "katatoni"], "action": "urgent_professional_support"},
    "severe_functional_decline": {"description": "Belirgin islev kaybi", "risk_level": "high", "keywords": ["ise gidemiyor", "dukkani acamiyor", "yataktan cikamiyor", "gunluk islerini yurutemez"], "action": "urgent_human_support"},
    "severe_dehydration_or_nutrition_risk": {"description": "Dehidratasyon veya malnutrisyon riski", "risk_level": "high", "keywords": ["beslenme reddi", "sivi reddi", "dehidratasyon", "malnutrisyon"], "action": "urgent_medical_evaluation"},
}

def _fold(text: str) -> str:
    return text.casefold().translate(str.maketrans("çğıöşü", "cgiosu"))

def detect_red_flags(message: str) -> List[Dict[str, str]]:
    normalized = _fold(message)
    found = []
    for name, rule in RED_FLAG_RULES.items():
        for keyword in rule["keywords"]:
            if _fold(keyword) in normalized:
                found.append({"name": name, "description": rule["description"], "risk_level": rule["risk_level"], "action": rule["action"], "matched_keyword": keyword})
                break
    return found
