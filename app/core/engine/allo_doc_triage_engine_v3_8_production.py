from __future__ import annotations

"""
ALLODOCTEUR - MOTEUR V3.8 PRODUCTION
====================================

V3.8 = V3.7 Africa Context-Aware + corrections finales production.

Corrections intégrées :
1. Gestion des négations : "sans fièvre", "pas de vomissements", etc.
2. Calibration P3/P4 sur cas bénins.
3. Logique pédiatrique IMCI simplifiée.
4. Stress court terme : P4 au lieu de P3.
5. Vomissements simples avec hydratation possible : P4.
6. Lombalgie simple courte : P4.
7. Dos ≠ flanc.
8. Toux + fièvre : respiratoire dominant, paludisme à éliminer.
9. Risque suicidaire : P1.
"""

from dataclasses import asdict
from typing import Any, Dict, Optional, List
import json
import re

try:
    import allo_doc_triage_engine_v3_7_africa as v37
except ImportError:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parent))
    import allo_doc_triage_engine_v3_7_africa as v37

base = v37.base

NEGATION_TERMS = [
    "sans", "pas de", "pas d", "aucun", "aucune", "ni",
    "ne presente pas", "ne présente pas", "n a pas", "n'ai pas", "n'a pas",
]

def norm(text: Any) -> str:
    try:
        return base.norm_text(str(text or ""))
    except Exception:
        return str(text or "").lower()

def has_any(text: str, patterns: List[str]) -> bool:
    return any(re.search(p, text) for p in patterns)

def has_negated(text: str, patterns: List[str], window: int = 5) -> bool:
    words = text.split()
    for i in range(len(words)):
        for neg in NEGATION_TERMS:
            neg_words = norm(neg).split()
            if words[i:i + len(neg_words)] == neg_words:
                zone = " ".join(words[i:i + len(neg_words) + window])
                if any(re.search(p, zone) for p in patterns):
                    return True
    return False

def detect_positive(text: str, positive_patterns: List[str], negation_patterns: Optional[List[str]] = None) -> bool:
    negation_patterns = negation_patterns or positive_patterns
    if has_negated(text, negation_patterns):
        return False
    return has_any(text, positive_patterns)

def priority_rank(p: str) -> int:
    return {"P1": 4, "P2": 3, "P3": 2, "P4": 1}.get(p, 0)

def set_result(
    result: Any,
    priority: str,
    message: str,
    reason: str,
    domain: Optional[str] = None,
    entry: Optional[str] = None,
    allow_downgrade: bool = False,
):
    if not allow_downgrade and priority_rank(priority) < priority_rank(result.priority_code):
        return result
    if allow_downgrade and result.priority_code in {"P1", "P2"}:
        return result

    result.priority_code = priority
    result.color = base.PRIORITY_META[priority]["color"]
    result.urgency_label = base.PRIORITY_META[priority]["urgency_label"]
    result.orientation = base.PRIORITY_META[priority]["orientation_default"]
    result.message = message

    if domain and domain not in (result.activated_domains or []):
        result.activated_domains.append(domain)
    if entry and entry not in (result.activated_entries or []):
        result.activated_entries.append(entry)
    if reason and reason not in result.reasons:
        result.reasons.append(reason)

    return result

def extract_v38_signals(payload: Dict[str, Any]) -> Dict[str, Any]:
    text = norm(payload.get("complaint_text", ""))
    associated = [norm(x) for x in payload.get("associated_signs", [])]
    red = payload.get("immediate_red_flags", {}) or {}

    age = None
    dob = str(payload.get("date_of_birth") or "").strip()
    if "/" in dob:
        try:
            age = 2026 - int(dob.split("/")[-1])
        except Exception:
            age = None

    fever = detect_positive(text, [r"\bfievre\b", r"temperature", r"frissons"]) or any("fievre" in x for x in associated)
    vomiting = detect_positive(text, [r"vomis", r"vomissement", r"vomissements"]) or any("vomissements" in x for x in associated)
    diarrhea = detect_positive(text, [r"diarrh", r"selles liquides", r"selles aqueuses"]) or any("diarrhee" in x for x in associated)
    digestive = vomiting or diarrhea
    rash = detect_positive(text, [r"boutons", r"eruption", r"plaques", r"taches", r"cloques"]) or any("eruption" in x for x in associated)

    cough = detect_positive(text, [r"\btoux\b", r"tousse", r"tousser", r"crachat", r"crache"])
    breathing_issue = (
        detect_positive(text, [r"essouffl", r"difficulte.*respir", r"respire mal", r"cherche l air"])
        or any("essoufflement" in x for x in associated)
        or bool(red.get("severe_breathing"))
    )

    unable_to_drink = detect_positive(text, [
        r"ne peux pas boire", r"ne peut pas boire", r"ne boit plus",
        r"refuse de boire", r"vomis tout ce que je bois", r"ne garde pas les liquides",
    ])
    can_drink = detect_positive(text, [
        r"je peux boire", r"peut boire", r"boit normalement",
        r"bois normalement", r"arrive a boire", r"arrive à boire",
    ])
    dehydration = detect_positive(text, [
        r"bouche seche", r"soif intense", r"yeux creux", r"urine presque plus", r"urine tres peu",
    ]) or bool(red.get("severe_dehydration")) or bool(red.get("severe_diarrhea_unable_to_drink"))

    urinary_burning = detect_positive(text, [
        r"brule quand j urine", r"brulure.*urine", r"brule.*uriner", r"douleur.*urine",
    ])

    back_pain = detect_positive(text, [r"mal au dos", r"douleur.*dos", r"lombalg", r"bas du dos"])
    flank_pain = detect_positive(text, [r"flanc", r"cote.*dos", r"douleur.*rein", r"reins"])

    chest_pain = detect_positive(text, [r"poitrine", r"thorax", r"douleur thorac"])
    pleuritic_chest_pain = chest_pain and detect_positive(text, [r"respire profond", r"inspiration", r"quand je respire"])

    dental_pain = detect_positive(text, [r"\bdent\b", r"dentaire", r"gencive", r"molaire", r"joue.*gonfl"])
    dental_swelling = dental_pain and detect_positive(text, [r"gonfl", r"joue", r"visage"])

    anxiety = detect_positive(text, [r"stress", r"stresse", r"anxieux", r"anxiete", r"angoisse"]) or any("anxiete" in x for x in associated)
    sleep_disorder = detect_positive(text, [r"dors mal", r"insomnie", r"sommeil"]) or any("troubles du sommeil" in x for x in associated)
    persistent_sadness = detect_positive(text, [r"triste", r"tristesse", r"pleure"]) or any("tristesse" in x for x in associated)
    loss_of_interest = detect_positive(text, [r"envie de rien", r"plus envie", r"perte d interet", r"plaisir"]) or any("perte d interet" in x for x in associated)

    suicidal = (
        detect_positive(text, [
            r"envie de mourir", r"me suicider", r"suicide", r"mettre fin a mes jours",
            r"me faire du mal", r"disparaitre",
        ])
        or bool(red.get("suicidal_or_extreme_psy"))
    )

    pain = detect_positive(text, [r"douleur", r"mal ", r"tres mal", r"forte douleur"]) or any("douleurs intenses" in x for x in associated)

    child = ("enfant" in text) or (age is not None and age <= 5)
    child_under_5 = age is not None and age < 5
    child_5_or_less = age is not None and age <= 5
    pregnant = bool(payload.get("pregnant")) or detect_positive(text, [r"enceinte", r"grossesse"])

    duration_days = None
    duration_raw = norm(payload.get("duration", ""))
    if "moins de 24" in duration_raw:
        duration_days = 1
    elif "1 a 3" in duration_raw or "1 à 3" in duration_raw:
        duration_days = 2
    elif "4 a 7" in duration_raw or "4 à 7" in duration_raw:
        duration_days = 5
    elif "semaine" in duration_raw:
        duration_days = 8
    elif "mois" in duration_raw:
        duration_days = 30
    elif "annee" in duration_raw:
        duration_days = 365

    if has_any(text, [r"depuis hier"]):
        duration_days = min(duration_days or 1, 1)
    if has_any(text, [r"quelques jours"]):
        duration_days = duration_days or 4
    if has_any(text, [r"deux semaines", r"2 semaines"]):
        duration_days = 14
    if has_any(text, [r"plusieurs semaines"]):
        duration_days = 21

    duration_days = duration_days or 2

    return {
        "text": text,
        "age": age,
        "fever": fever,
        "vomiting": vomiting,
        "diarrhea": diarrhea,
        "digestive": digestive,
        "rash": rash,
        "cough": cough,
        "breathing_issue": breathing_issue,
        "unable_to_drink": unable_to_drink,
        "can_drink": can_drink,
        "dehydration": dehydration,
        "urinary_burning": urinary_burning,
        "back_pain": back_pain,
        "flank_pain": flank_pain,
        "chest_pain": chest_pain,
        "pleuritic_chest_pain": pleuritic_chest_pain,
        "dental_pain": dental_pain,
        "dental_swelling": dental_swelling,
        "anxiety": anxiety,
        "sleep_disorder": sleep_disorder,
        "persistent_sadness": persistent_sadness,
        "loss_of_interest": loss_of_interest,
        "suicidal": suicidal,
        "pain": pain,
        "child": child,
        "child_under_5": child_under_5,
        "child_5_or_less": child_5_or_less,
        "pregnant": pregnant,
        "duration_days": duration_days,
        "duration_long": duration_days >= 7,
        "red_flags": red,
    }

def apply_v38_corrections(result: Any, payload: Dict[str, Any]) -> Any:
    s = extract_v38_signals(payload)

    if result.priority_code == "P1":
        return result

    if s["suicidal"]:
        return set_result(result, "P1",
            "Risque psychique immédiat détecté. Contactez immédiatement un service d'urgence ou une personne de confiance et ne restez pas seul(e).",
            "V3.8 production: risque suicidaire => P1", "psychiatrique", "V38_PSY_SUICIDAL_P1")

    if s["chest_pain"] and result.priority_code not in {"P1", "P2"}:
        return set_result(result, "P2",
            "Une douleur dans la poitrine nécessite une évaluation médicale rapide.",
            "V3.8 production: douleur thoracique non banalisable => P2", "cardio", "V38_CHEST_PAIN_P2")

    if s["child_5_or_less"] and s["fever"]:
        if s["unable_to_drink"] or s["dehydration"] or s["red_flags"].get("seizures"):
            return set_result(result, "P1",
                "Enfant avec signe général de danger. Rendez-vous immédiatement aux urgences.",
                "V3.8 IMCI: enfant fébrile avec signe de danger => P1", "pediatrie", "V38_IMCI_CHILD_DANGER_P1")
        if s["can_drink"] and not s["breathing_issue"] and result.priority_code == "P3":
            return set_result(result, "P4",
                "Fièvre chez l'enfant sans signe de gravité immédiate. Surveillez l'évolution, assurez une bonne hydratation et consultez si la fièvre persiste ou s'aggrave.",
                "V3.8 IMCI: enfant fébrile qui boit bien, sans danger => P4",
                "pediatrie", "V38_IMCI_CHILD_FEVER_SAFE_P4", allow_downgrade=True)

    if s["cough"] and s["fever"] and result.priority_code == "P2":
        if "paludisme" in norm(result.message):
            result.message = (
                "Une infection respiratoire est probable devant la toux avec fièvre. "
                "Consultez rapidement. En contexte africain, un paludisme reste possible et doit aussi être éliminé."
            )
            if "respiratoire" not in result.activated_domains:
                result.activated_domains.append("respiratoire")
            if "V38_RESP_FEVER_DOMINANT_P2" not in result.activated_entries:
                result.activated_entries.append("V38_RESP_FEVER_DOMINANT_P2")
            result.reasons.append("V3.8 production: toux + fièvre => respiratoire dominant, paludisme à éliminer")
            return result

    if result.priority_code == "P3" and s["digestive"]:
        if s["can_drink"] and not s["fever"] and not s["dehydration"] and not s["unable_to_drink"]:
            return set_result(result, "P4",
                "Vomissements ou troubles digestifs sans signe de gravité immédiate. Hydratez-vous et consultez si cela persiste, s'aggrave ou si vous ne pouvez plus boire.",
                "V3.8 calibration: digestif simple avec hydratation possible => P4",
                "digestif", "V38_DIGESTIVE_SIMPLE_SAFE_P4", allow_downgrade=True)

    if result.priority_code == "P3" and "sans vomissement" in s["text"]:
        if not s["fever"] and not s["diarrhea"] and not s["dehydration"]:
            return set_result(result, "P4",
                "Douleur abdominale légère sans signe associé de gravité. Surveillez l'évolution et consultez si la douleur augmente, persiste ou s'accompagne de fièvre/vomissements.",
                "V3.8 négation: sans vomissements => digestif simple non grave => P4",
                "digestif", "V38_NEG_NO_VOMITING_ABDO_P4", allow_downgrade=True)

    if s["rash"] and has_negated(s["text"], [r"fievre"]):
        if result.priority_code in {"P3", "P4"}:
            return set_result(result, "P4",
                "Une éruption cutanée simple sans fièvre a été détectée. Consultez si les lésions persistent, s'étendent ou si la fièvre apparaît.",
                "V3.8 négation: rash sans fièvre => P4",
                "dermatologique", "V38_RASH_NO_FEVER_P4", allow_downgrade=True)

    if result.priority_code == "P3" and (s["anxiety"] or s["sleep_disorder"]):
        if not s["persistent_sadness"] and not s["loss_of_interest"] and s["duration_days"] < 7:
            return set_result(result, "P4",
                "Vos symptômes évoquent un stress ou un trouble du sommeil récent. Surveillez l'évolution et consultez si cela persiste, s'aggrave ou impacte fortement votre quotidien.",
                "V3.8 calibration psy: stress court sans danger => P4",
                "psychiatrique", "V38_PSY_ACUTE_STRESS_P4", allow_downgrade=True)

    if result.priority_code in {"P4", "P3"} and (s["persistent_sadness"] and s["loss_of_interest"]):
        if s["duration_days"] >= 14:
            return set_result(result, "P3",
                "Vos symptômes évoquent une souffrance psychique persistante. Une consultation avec un professionnel de santé mentale est recommandée rapidement.",
                "V3.8 psy: tristesse + perte d'intérêt prolongées => P3",
                "psychiatrique", "V38_PSY_PERSISTENT_P3")

    if result.priority_code == "P3" and s["back_pain"]:
        no_red_flags = not s["fever"] and not s["dehydration"] and not s["red_flags"].get("head_trauma")
        if no_red_flags and s["duration_days"] < 14:
            return set_result(result, "P4",
                "Douleur du dos sans signe de gravité immédiate. Surveillez l'évolution, évitez les efforts importants et consultez si la douleur persiste, s'aggrave ou s'accompagne de fièvre/faiblesse.",
                "V3.8 calibration musculo: lombalgie simple courte => P4",
                "musculo", "V38_BACK_PAIN_SIMPLE_P4", allow_downgrade=True)

    if not s["dental_pain"]:
        if "dentaire" in result.activated_domains:
            result.activated_domains = [d for d in result.activated_domains if d != "dentaire"]
        result.activated_entries = [e for e in result.activated_entries if not ("DENTAL" in e or "DENTAIRE" in e or "DENT" in e)]
        result.reasons = [r for r in result.reasons if "dentaire" not in norm(r) and "dent" not in norm(r)]

    if has_negated(s["text"], [r"fievre"]):
        result.reasons = [r for r in result.reasons if "Symptôme activé: Fièvre" not in r]
        result.activated_entries = [e for e in result.activated_entries if e != "SYM_FEVER"]
        if "fievre" in result.activated_domains and not s["fever"]:
            result.activated_domains = [d for d in result.activated_domains if d != "fievre"]

    return result

def load_kb(path: str = base.KB_DEFAULT_PATH) -> Dict[str, Any]:
    return v37.load_kb(path)

def run_triage_v3_8_production(payload: Dict[str, Any], kb: Dict[str, Any], dynamic_answers: Optional[Dict[str, Any]] = None):
    result = v37.run_triage_v3_7_africa(payload, kb, dynamic_answers=dynamic_answers)
    return apply_v38_corrections(result, payload)

run_triage = run_triage_v3_8_production

def interactive_cli() -> None:
    kb = load_kb()
    print("=" * 80)
    print("SERVICE DE TRIAGE - MODE INTERACTIF (MOTEUR V3.8 PRODUCTION)")
    print("Ce service donne une orientation et non un diagnostic.")
    print("En cas d'urgence vitale, rendez-vous immédiatement à l'hôpital.")
    print("=" * 80)

    payload = {
        "complaint_text": input("1. Quelle est votre plainte principale ? ").strip(),
        "duration": base.choose_one("\n2. Depuis quand avez-vous ce problème ?", base.DURATION_OPTIONS),
        "associated_signs": base.choose_many("\n3. Avez-vous des signes associés ?", base.ASSOCIATED_OPTIONS),
        "prior_consultation": base.choose_one("\n4. Avez-vous déjà consulté pour ce problème ?", base.CONSULT_OPTIONS),
        "attachment_present": base.ask_bool("5. Voulez-vous signaler qu'une photo ou un document est disponible ?"),
        "medical_history": base.choose_many("\n6. Quels sont vos antécédents médicaux ?", base.HISTORY_OPTIONS),
        "date_of_birth": input("7. Date de naissance (JJ/MM/AAAA) : ").strip(),
        "weight_kg": input("8. Poids en kg (optionnel) : ").strip(),
        "height_m": input("8b. Taille en mètre (optionnel) : ").strip(),
        "sex": input("Sexe (Homme/Femme) : ").strip(),
        "pregnant": False,
        "province": input("Province : ").strip(),
        "immediate_red_flags": {},
    }

    if base.norm_text(payload["sex"]) == "femme":
        payload["pregnant"] = base.ask_bool("Êtes-vous enceinte ?")

    print("\nSignes d'alerte immédiats :")
    for key, label in base.IMMEDIATE_RED_FLAG_KEYS.items():
        payload["immediate_red_flags"][key] = base.ask_bool(label)

    result = run_triage_v3_8_production(payload, kb, dynamic_answers={})
    print("\n" + "=" * 80)
    print("RÉSULTAT FINAL")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    interactive_cli()
