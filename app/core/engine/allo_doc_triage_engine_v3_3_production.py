from __future__ import annotations

"""
ALLODOCTEUR - MOTEUR V3.3 PRODUCTION
=====================================
Version consolidée après les tests terrain.

Correctifs intégrés :
1. Routing global des syndrome_entry : les syndromes non reliés à un symptom_entry sont évalués.
2. Grossesse + douleur abdominale / bas ventre => P2 minimum.
3. Syndrome général : fatigue + perte d'appétit + durée >= 7 jours => P3.
4. Détection NLP renforcée : bas ventre, douleur pelvienne, fréquence urinaire, crise convulsive, sueurs nocturnes.
5. Correction du faux positif douleur : ne plus activer PAIN_SYM_GENERIC sur "mal" seul dans un contexte psychologique.
6. Hard stop P1 direct sur red flags critiques.
7. Zéro question complémentaire en P1.
8. Un seul syndrome dominant par domaine.

Ce moteur donne une ORIENTATION DE TRIAGE, pas un diagnostic.
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
import json
import re
import unicodedata
from typing import Any, Dict, List, Optional, Set

KB_DEFAULT_PATH = "../data/kb_allodocteur_v3_complete.json"

PRIORITY_RANK = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}
PRIORITY_BY_SCORE = [
    {"min": 0, "max": 1, "priority": "P4"},
    {"min": 2, "max": 3, "priority": "P3"},
    {"min": 4, "max": 100, "priority": "P2"},
]

PRIORITY_META = {
    "P1": {"color": "ROUGE", "urgency_label": "Urgence vitale", "orientation_default": "Urgences / hôpital le plus proche"},
    "P2": {"color": "ORANGE", "urgency_label": "Urgence", "orientation_default": "Centre de santé / service d'urgence"},
    "P3": {"color": "ORANGE", "urgency_label": "Consultation rapide", "orientation_default": "Médecin généraliste / centre de santé"},
    "P4": {"color": "VERT", "urgency_label": "Consultation standard / conseils", "orientation_default": "Médecin généraliste ou spécialiste selon le cas"},
}

DURATION_OPTIONS = [
    "Moins de 24 heures",
    "1 à 3 jours",
    "4 à 7 jours",
    "Plus d’une semaine",
    "Plus d’un mois",
    "Plus d’ une année",
]

CONSULT_OPTIONS = [
    "Oui, dans les 30 derniers jours passés",
    "Oui, il y a plus d’un mois",
    "Oui, il y a plus d’une année",
    "Non",
    "Je ne sais pas",
]

ASSOCIATED_OPTIONS = [
    "Fièvre", "Douleurs intenses", "Essoufflement", "Vomissements / diarrhée",
    "Éruption cutanée", "Fatigue", "Maux de tête", "Perte d’appetit",
    "Perte d'intérêt, de plaisir", "Tristesse persistante", "Anxiété",
    "Troubles du sommeil", "Perte de la libido", "Aucun",
]

HISTORY_OPTIONS = [
    "Diabète", "obésité", "Hypertension", "AVC", "Tuberculose", "Migraine chronique",
    "Epilepsie", "césarienne", "Dépression", "Asthme", "Maladie cardiaque",
    "Allergies alimentaires ou médicamenteuses", "Interventions chirurgicales",
    "Avortements (provoqués ou non provoqués)", "Aucun antécedent",
]

IMMEDIATE_RED_FLAG_KEYS = {
    "severe_breathing": "Difficulté grave à respirer, étouffement ou sifflement respiratoire",
    "chest_pressure": "Douleur ou forte pression dans la poitrine",
    "severe_diarrhea_unable_to_drink": "Diarrhée sévère très fréquente avec incapacité de garder les liquides",
    "severe_dehydration": "Signes de déshydratation grave",
    "stroke_signs": "Faiblesse d'un côté, difficulté à parler, visage dévié",
    "loss_of_consciousness": "Perte de connaissance / inconscient / ne répond plus",
    "sudden_confusion": "Confusion soudaine ou comportement bizarre",
    "uncontrollable_bleeding": "Saignements abondants impossibles à arrêter",
    "board_like_abdomen": "Ventre très dur et douleur insupportable",
    "fever_with_neck_stiffness": "Fièvre élevée avec raideur au cou ou violents maux de tête",
    "seizures": "Convulsions ou tremblements incontrôlables",
    "rash_with_fever": "Boutons, cloques ou taches suspectes avec forte fièvre",
    "poisoning": "Ingestion de produit toxique, poison ou surdosage médicamenteux",
    "severe_burn": "Brûlure grave",
    "suicidal_or_extreme_psy": "Pensées suicidaires, agressivité extrême ou peur immédiate",
    "open_fracture_or_major_accident": "Fracture ouverte ou accident grave",
    "head_trauma": "Choc violent à la tête après chute ou accident",
}

QUESTION_TO_FIELD_MAP = {
    "Q_UNABLE_TO_DRINK": "unable_to_drink",
    "Q_URINE_LOW": "urine_output_low",
    "Q_DRY_MOUTH": "dehydration_signs",
    "Q_NO_TEARS": "no_tears",
    "Q_CONFUSION": "confusion",
    "Q_SEIZURES": "seizures",
    "Q_TEMP": "temperature_c",
    "Q_FEVER_DAYS": "duration_days",
    "Q_RASH_PURPURA": "rash_petechiae_purpura",
    "Q_NECK_STIFFNESS": "neck_stiffness",
    "Q_MENTAL_STATUS": "mental_status_change",
    "Q_BREATHING_DISTRESS": "respiratory_distress",
    "Q_URINARY_BURNING": "urinary_burning",
    "Q_URINARY_FREQ": "urinary_frequency",
    "Q_URINARY_FEVER": "fever",
    "Q_URINARY_FLANK": "flank_pain",
    "Q_URINARY_BLOOD": "hematuria",
    "Q_PSY_IMPACT": "psych_impact",
    "Q_PSY_SUICIDE": "danger_to_self",
    "Q_DENT_SWELLING": "dental_swelling",
    "Q_DENT_FEVER": "dental_fever",
    "Q_DENT_SWALLOW": "difficulty_swallowing",
    "Q_PAIN_LOCATION": "pain_location",
    "Q_PAIN_INTENSITY": "pain_intensity_0_10",
    "Q_PAIN_SUDDEN": "pain_onset_sudden",
    "Q_BLEEDING": "bleeding",
    "Q_SBP": "systolic_bp",
    "Q_CRT": "capillary_refill_seconds",
    "Q_SPO2": "spo2",
    "Q_VAGINAL_BLEEDING": "vaginal_bleeding",
}

TEXT_PATTERNS = {
    "unable_to_drink": [
        r"refuse .*boire", r"refuse de boire", r"ne boit pas", r"ne veut pas boire",
        r"n arrive pas a boire", r"incapable de boire", r"ne garde pas les liquides",
        r"vomit tout ce qu il boit", r"ne peut plus boire"
    ],
    "urine_output_low": [
        r"n urine presque plus", r"urine tres peu", r"plus d urine", r"urine diminuee",
        r"n a presque pas urine"
    ],
    "dehydration_signs": [
        r"bouche seche", r"tres sec", r"pas de larmes", r"yeux creux", r"tres mou", r"abattu", r"somnolent"
    ],
    "respiratory_distress": [
        r"parle difficilement", r"ne finit pas ses phrases", r"etouffe", r"respire tres mal",
        r"cherche l air", r"poitrine se serre", r"mal a respirer", r"difficile de respirer"
    ],
    "rapid_worsening": [
        r"s aggrave vite", r"de pire en pire", r"rapidement", r"depuis cette nuit .* pire", r"brutalement"
    ],
    "flank_pain": [r"douleur lombaire", r"mal au dos", r"douleur dans le dos", r"bas du dos", r"lombaire"],
    "hematuria": [r"sang dans les urines", r"urines rouges"],
    "severe_abdominal_pain": [
        r"ventre tres douloureux", r"douleur tres forte au ventre", r"ventre dur", r"douleur forte .* ventre", r"douleur intense .* ventre"
    ],
    "lower_abdominal_pain": [
        r"bas du ventre", r"douleur bas ventre", r"douleur pelvienne", r"douleur en bas du ventre", r"mal au bas ventre"
    ],
    "vaginal_bleeding": [r"saignement vaginal", r"je saigne", r"pertes de sang", r"saigne du vagin"],
    "seizure_like": [
        r"crise[s]?", r"convulsion[s]?", r"secousse[s]?", r"tremblements? incontr[oô]lables?",
        r"je me suis raidie", r"raidi", r"se raidit", r"corps raide"
    ],
    "urinary_frequency": [
        r"envie d aller aux toilettes souvent", r"envie frequente d uriner", r"urine souvent",
        r"toilettes souvent", r"uriner souvent", r"envie .*souvent"
    ],
    "night_sweats": [
        r"transpire la nuit", r"sueurs nocturnes", r"transpire beaucoup la nuit", r"sue la nuit"
    ],
    "suicidal_text": [
        r"mieux de disparaitre", r"envie de mourir", r"me suicider", r"mettre fin a mes jours", r"ne plus vivre"
    ],
    "dental_swelling": [
    r"joue gonfl",
    r"gonflement",
    r"visage gonfl",
    r"abc[eè]s",
    r"enfl[eé]"
]
}

DOMAIN_CONTEXT_QUESTION_MAP = {
    "digestif": {"Q_RAPID_WORSENING", "Q_IMMUNOCOMPROMISED", "Q_ENDEMIC_AREA", "Q_HIGH_CHOLERA_CONTEXT"},
    "respiratoire": {"Q_RAPID_WORSENING", "Q_IMMUNOCOMPROMISED", "Q_ENDEMIC_AREA"},
    "fievre": {"Q_RAPID_WORSENING", "Q_IMMUNOCOMPROMISED", "Q_ENDEMIC_AREA"},
    "urinaire": {"Q_RAPID_WORSENING", "Q_IMMUNOCOMPROMISED"},
    "psychiatrique": {"Q_RAPID_WORSENING"},
    "dentaire": {"Q_RAPID_WORSENING"},
    "dermatologique": {"Q_RAPID_WORSENING", "Q_IMMUNOCOMPROMISED"},
    "gyn_obs": {"Q_RAPID_WORSENING", "Q_VAGINAL_BLEEDING"},
    "transversal": {"Q_RAPID_WORSENING", "Q_IMMUNOCOMPROMISED"},
    "neurologique": {"Q_RAPID_WORSENING", "Q_IMMUNOCOMPROMISED"},
}

GENERIC_CONTEXT_QUESTIONS = [
    {"id": "Q_RAPID_WORSENING", "label": "Les symptômes s'aggravent-ils rapidement ?", "type": "boolean", "domain": "transversal"},
    {"id": "Q_IMMUNOCOMPROMISED", "label": "La personne est-elle immunodéprimée ?", "type": "boolean", "domain": "transversal"},
    {"id": "Q_ENDEMIC_AREA", "label": "Le patient vit-il en zone endémique palustre ?", "type": "boolean", "domain": "fievre"},
    {"id": "Q_HIGH_CHOLERA_CONTEXT", "label": "Existe-t-il un contexte d'épidémie de diarrhée/choléra ?", "type": "boolean", "domain": "digestif"},
    {"id": "Q_VAGINAL_BLEEDING", "label": "Y a-t-il un saignement vaginal ?", "type": "boolean", "domain": "gyn_obs"},
]

DIRECT_P1_RULES = [
    {"id": "DIRECT_RF_SEVERE_BREATHING", "field": "respiratory_distress", "reason": "Détresse respiratoire", "message": "Urgence vitale détectée. Rendez-vous immédiatement aux urgences ou à l'hôpital le plus proche."},
    {"id": "DIRECT_RF_SEIZURES", "field": "seizures", "reason": "Convulsions", "message": "Des convulsions ont été détectées. Rendez-vous immédiatement aux urgences ou à l'hôpital le plus proche."},
    {"id": "DIRECT_RF_SEIZURE_LIKE", "field": "seizure_like", "reason": "Crise convulsive probable", "message": "Une crise convulsive probable a été détectée. Rendez-vous immédiatement aux urgences ou à l'hôpital le plus proche."},
    {"id": "DIRECT_RF_STROKE", "field": "stroke_signs", "reason": "AVC suspect", "message": "Des signes évocateurs d'un AVC ont été détectés. Rendez-vous immédiatement aux urgences ou à l'hôpital le plus proche."},
    {"id": "DIRECT_RF_SUICIDE", "field": "danger_to_self", "reason": "Danger psychique immédiat", "message": "Des idées suicidaires ou un danger psychique immédiat ont été détectés. Rendez-vous immédiatement aux urgences ou demandez une aide immédiate."},
    {"id": "DIRECT_RF_DEHYDRATION", "field": "severe_diarrhea_unable_to_drink", "reason": "Déshydratation sévère probable", "message": "Des signes de déshydratation sévère ont été détectés. Rendez-vous immédiatement aux urgences ou à l'hôpital le plus proche."},
    {"id": "DIRECT_RF_LOSS_CONSCIOUSNESS", "field": "loss_of_consciousness", "reason": "Perte de connaissance", "message": "Une perte de connaissance a été détectée. Rendez-vous immédiatement aux urgences ou à l'hôpital le plus proche."},
    {"id": "DIRECT_RF_BLEEDING", "field": "severe_bleeding", "reason": "Saignement abondant", "message": "Un saignement abondant a été détecté. Rendez-vous immédiatement aux urgences ou à l'hôpital le plus proche."},
]


@dataclass
class TriageResult:
    priority_code: str
    color: str
    urgency_label: str
    orientation: str
    message: str
    reasons: List[str]
    activated_domains: List[str] = field(default_factory=list)
    activated_entries: List[str] = field(default_factory=list)
    activated_modifiers: List[str] = field(default_factory=list)
    activated_patterns: List[str] = field(default_factory=list)
    score_total: int = 0
    score_breakdown: List[str] = field(default_factory=list)
    normalized_profile: Dict[str, Any] = field(default_factory=dict)
    case_fields: Dict[str, Any] = field(default_factory=dict)
    asked_questions: List[Dict[str, Any]] = field(default_factory=list)


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def norm_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = strip_accents(text.lower())
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ".").strip())
    except Exception:
        return None


def safe_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"o", "oui", "true", "1", "yes", "y"}
    return bool(v)


def compute_age_years(dob: Optional[str]) -> Optional[int]:
    if not dob:
        return None
    try:
        dt = datetime.strptime(dob, "%d/%m/%Y")
        today = datetime.today()
        years = today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
        return max(years, 0)
    except Exception:
        return None


def duration_to_bucket(v: str) -> str:
    mapping = {
        "Moins de 24 heures": "lt_24h",
        "1 à 3 jours": "1_3_days",
        "4 à 7 jours": "4_7_days",
        "Plus d’une semaine": "gt_1_week",
        "Plus d’un mois": "gt_1_month",
        "Plus d’ une année": "gt_1_year",
    }
    return mapping.get(v, "unknown")


def duration_bucket_to_days(bucket: str) -> Optional[int]:
    mapping = {"lt_24h": 1, "1_3_days": 2, "4_7_days": 5, "gt_1_week": 8, "gt_1_month": 35, "gt_1_year": 365}
    return mapping.get(bucket)


def infer_duration_from_text(text: str) -> Optional[int]:
    if "depuis ce matin" in text or "depuis hier" in text:
        return 1
    if "depuis plusieurs jours" in text:
        return 5
    if "depuis quelques jours" in text:
        return 4
    if "depuis plusieurs semaines" in text:
        return 21
    if "depuis plusieurs mois" in text:
        return 60
    return None


def load_kb(path: str = KB_DEFAULT_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        kb = json.load(f)
    ensure_runtime_messages(kb)
    ensure_runtime_entries(kb)
    return kb


def ensure_runtime_messages(kb: Dict[str, Any]) -> None:
    messages = kb.setdefault("messages", {})
    messages.setdefault("MSG_GENERAL_STATE", "Vos symptômes évoquent une altération de l’état général nécessitant une consultation médicale rapide.")
    messages.setdefault("MSG_PREGNANCY_PAIN", "Toute douleur abdominale pendant une grossesse nécessite une évaluation médicale rapide.")
    messages.setdefault("MSG_URI_SIMPLE_P3", "Un syndrome urinaire bas probable nécessite une consultation rapide pour éviter une complication.")


def ensure_runtime_entries(kb: Dict[str, Any]) -> None:
    """Ajoute au runtime les entrées critiques si la KB ne les contient pas encore."""
    entries = kb.setdefault("entries", [])
    ids = {e.get("kb_id") for e in entries}

    if "GENERAL_STATE_SYNDROME" not in ids:
        entries.append({
            "kb_id": "GENERAL_STATE_SYNDROME",
            "entry_class": "syndrome_entry",
            "domain": "transversal",
            "title": "Altération de l’état général",
            "rules": [{
                "id": "RULE_GENERAL_STATE_P3",
                "logic": {"all": [
                    {"field": "fatigue", "op": "==", "value": True},
                    {"field": "loss_of_appetite", "op": "==", "value": True},
                    {"field": "duration_days", "op": ">=", "value": 7}
                ]},
                "decision": {
                    "priority_level": "P3",
                    "orientation": "Médecin généraliste / centre de santé",
                    "base_score": 2,
                    "message_key": "MSG_GENERAL_STATE"
                }
            }]
        })

    if "GYN_PREGNANCY_PAIN" not in ids:
        entries.append({
            "kb_id": "GYN_PREGNANCY_PAIN",
            "entry_class": "syndrome_entry",
            "domain": "gyn_obs",
            "title": "Douleur abdominale chez femme enceinte",
            "rules": [{
                "id": "RULE_PREGNANCY_PAIN_P2",
                "logic": {"all": [
                    {"field": "pregnant", "op": "==", "value": True},
                    {"field": "pain", "op": "==", "value": True}
                ]},
                "decision": {
                    "priority_level": "P2",
                    "orientation": "Centre de santé / service d'urgence",
                    "base_score": 4,
                    "message_key": "MSG_PREGNANCY_PAIN"
                }
            }]
        })


def message_for_key(kb: Dict[str, Any], key: Optional[str], default: str = "") -> str:
    if not key:
        return default
    return kb.get("messages", {}).get(key, default)


def max_priority(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if a is None:
        return b
    if b is None:
        return a
    return a if PRIORITY_RANK[a] >= PRIORITY_RANK[b] else b


def priority_from_score(score: int) -> str:
    for band in PRIORITY_BY_SCORE:
        if band["min"] <= score <= band["max"]:
            return band["priority"]
    return "P2"


def detect_textual_signals(text: str) -> Dict[str, bool]:
    out: Dict[str, bool] = {}
    for key, patterns in TEXT_PATTERNS.items():
        out[key] = any(re.search(p, text) for p in patterns)
    return out


def normalize_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    complaint_text = payload.get("complaint_text", "")
    complaint_norm = norm_text(complaint_text)
    associated = payload.get("associated_signs", []) or []
    associated_norm = [norm_text(x) for x in associated]
    history = payload.get("medical_history", []) or []
    history_norm = [norm_text(x) for x in history]
    age_years = compute_age_years(payload.get("date_of_birth"))
    duration_bucket = duration_to_bucket(payload.get("duration", ""))
    duration_days = infer_duration_from_text(complaint_norm) or duration_bucket_to_days(duration_bucket)
    red_flags = {k: safe_bool(v) for k, v in (payload.get("immediate_red_flags") or {}).items()}
    sex_norm = norm_text(payload.get("sex", ""))
    text_signals = detect_textual_signals(complaint_norm)

    # Évite le faux positif : "je me sens très mal" ne doit pas être interprété comme douleur.
    explicit_pain_text = any(x in complaint_norm for x in ["douleur", "douleurs", "douloureux", "mal au", "mal dans", "mal de dent", "mal a la tete"])
    associated_pain = any("douleurs intenses" in s for s in associated_norm)

    flags = {
        "fever": ("fievre" in complaint_norm) or any("fievre" in s for s in associated_norm),
        "fatigue": ("fatigue" in complaint_norm) or ("tres mou" in complaint_norm) or any("fatigue" in s for s in associated_norm),
        "headache": ("maux de tete" in complaint_norm) or ("mal a la tete" in complaint_norm) or any("maux de tete" in s for s in associated_norm),
        "breathing_issue": ("respir" in complaint_norm) or any("essoufflement" in s for s in associated_norm),
        "digestive_symptom": ("vomissement" in complaint_norm) or ("diarrhee" in complaint_norm) or any("vomissements diarrhee" in s or "vomissements / diarrhee" in s for s in associated_norm),
        "rash": ("eruption" in complaint_norm) or ("rash" in complaint_norm) or ("demangeais" in complaint_norm) or any("eruption cutanee" in s for s in associated_norm),
        "anxiety": ("anxiete" in complaint_norm) or ("angoisse" in complaint_norm) or any("anxiete" in s for s in associated_norm),
        "persistent_sadness": ("tristesse" in complaint_norm) or any("tristesse persistante" in s for s in associated_norm),
        "sleep_disorder": any("troubles du sommeil" in s for s in associated_norm),
        "loss_of_interest": any("perte d interet" in s for s in associated_norm) or ("plus de gout a rien" in complaint_norm),
        "loss_of_appetite": any("perte d appetit" in s for s in associated_norm) or ("plus d appetit" in complaint_norm),
        "urinary_burning": ("urinaire" in complaint_norm) or ("urine" in complaint_norm) or ("miction" in complaint_norm) or ("brule" in complaint_norm) or ("brulure" in complaint_norm),
        "dental_pain": ("dent" in complaint_norm) or ("dentaire" in complaint_norm),
        "pain": explicit_pain_text or associated_pain or text_signals["lower_abdominal_pain"] or text_signals["severe_abdominal_pain"],
        "asthma_history": any("asthme" in s for s in history_norm),
        "depression_history": any("depression" in s for s in history_norm),
        "epilepsy_history": any("epilepsie" in s for s in history_norm),
        "hypertension_history": any("hypertension" in s for s in history_norm),
        "diabetes_history": any("diabete" in s for s in history_norm),
        "heart_disease_history": any("maladie cardiaque" in s for s in history_norm),
        "pregnant": safe_bool(payload.get("pregnant", False)) or ("enceinte" in complaint_norm),
        "child_under_5": age_years is not None and age_years < 5,
        "senior": age_years is not None and age_years >= 65,
        "duration_long": duration_days is not None and duration_days >= 7,
        "sex_male": sex_norm == "homme",
        "sex_female": sex_norm == "femme",
    }

    return {
        "complaint_text": complaint_text,
        "complaint_norm": complaint_norm,
        "associated_signs_raw": associated,
        "associated_norm": associated_norm,
        "medical_history_raw": history,
        "medical_history_norm": history_norm,
        "duration_bucket": duration_bucket,
        "duration_days_est": duration_days,
        "date_of_birth": payload.get("date_of_birth"),
        "age_years": age_years,
        "sex": payload.get("sex"),
        "province": payload.get("province", ""),
        "weight_kg": parse_float(payload.get("weight_kg")),
        "height_m": parse_float(payload.get("height_m")),
        "pregnant": flags["pregnant"],
        "attachment_present": safe_bool(payload.get("attachment_present", False)),
        "immediate_red_flags": red_flags,
        "normalized_flags": flags,
        "text_signals": text_signals,
    }


def build_case_fields(profile: Dict[str, Any], dynamic_answers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    a = dynamic_answers or {}
    flags = profile["normalized_flags"]
    ts = profile["text_signals"]
    rf = profile["immediate_red_flags"]

    fields: Dict[str, Any] = {
        "fever": flags["fever"],
        "fatigue": flags["fatigue"],
        "headache": flags["headache"],
        "breathing_issue": flags["breathing_issue"],
        "digestive_symptom": flags["digestive_symptom"],
        "rash": flags["rash"],
        "anxiety": flags["anxiety"],
        "persistent_sadness": flags["persistent_sadness"],
        "sleep_disorder": flags["sleep_disorder"],
        "loss_of_interest": flags["loss_of_interest"],
        "loss_of_appetite": flags["loss_of_appetite"],
        "urinary_burning": flags["urinary_burning"],
        "dental_pain": flags["dental_pain"],
        "pain": flags["pain"],
        "asthma_history": flags["asthma_history"],
        "depression_history": flags["depression_history"],
        "epilepsy_history": flags["epilepsy_history"],
        "hypertension_history": flags["hypertension_history"],
        "diabetes_history": flags["diabetes_history"],
        "heart_disease_history": flags["heart_disease_history"],
        "pregnant": flags["pregnant"],
        "child_under_5": flags["child_under_5"],
        "senior": flags["senior"],
        "duration_long": flags["duration_long"],
        "sex_male": flags["sex_male"],
        "sex_female": flags["sex_female"],
        "duration_days": profile.get("duration_days_est"),
        "rapid_worsening": ts["rapid_worsening"],
        "immunocompromised": safe_bool(a.get("Q_IMMUNOCOMPROMISED")),
        "endemic_area": safe_bool(a.get("Q_ENDEMIC_AREA")),
        "high_cholera_context": safe_bool(a.get("Q_HIGH_CHOLERA_CONTEXT")),
        "unable_to_drink": ts["unable_to_drink"] or rf.get("severe_diarrhea_unable_to_drink", False),
        "urine_output_low": ts["urine_output_low"],
        "dehydration_signs": ts["dehydration_signs"] or rf.get("severe_dehydration", False),
        "no_tears": False,
        "confusion": rf.get("sudden_confusion", False),
        "mental_status_change": rf.get("sudden_confusion", False),
        "seizures": rf.get("seizures", False),
        "seizure_like": ts["seizure_like"] or rf.get("seizures", False),
        "temperature_c": None,
        "rash_petechiae_purpura": False,
        "neck_stiffness": rf.get("fever_with_neck_stiffness", False),
        "respiratory_distress": ts["respiratory_distress"] or rf.get("severe_breathing", False),
        "flank_pain": ts["flank_pain"],
        "urinary_frequency": ts["urinary_frequency"],
        "hematuria": ts["hematuria"],
        "psych_impact": False,
        "danger_to_self": rf.get("suicidal_or_extreme_psy", False) or ts["suicidal_text"],
        "dental_swelling": False,
        "dental_fever": False,
        "difficulty_swallowing": False,
        "pain_location": "abdomen" if ts["lower_abdominal_pain"] or ts["severe_abdominal_pain"] else None,
        "lower_abdominal_pain": ts["lower_abdominal_pain"],
        "pain_intensity_0_10": 8 if ts["severe_abdominal_pain"] else None,
        "pain_onset_sudden": False,
        "bleeding": rf.get("uncontrollable_bleeding", False),
        "severe_bleeding": rf.get("uncontrollable_bleeding", False),
        "systolic_bp": None,
        "capillary_refill_seconds": None,
        "spo2": None,
        "stroke_signs": rf.get("stroke_signs", False),
        "severe_breathing": rf.get("severe_breathing", False),
        "severe_diarrhea_unable_to_drink": rf.get("severe_diarrhea_unable_to_drink", False),
        "board_like_abdomen": rf.get("board_like_abdomen", False),
        "head_trauma": rf.get("head_trauma", False),
        "loss_of_consciousness": rf.get("loss_of_consciousness", False),
        "severe_abdominal_pain": ts["severe_abdominal_pain"] or rf.get("board_like_abdomen", False),
        "vaginal_bleeding": ts["vaginal_bleeding"],
        "rash_spreading": False,
        "night_sweats": ts["night_sweats"],
    }

    for qid, value in a.items():
        field_name = QUESTION_TO_FIELD_MAP.get(qid)
        if not field_name:
            continue
        if isinstance(fields.get(field_name), bool):
            fields[field_name] = safe_bool(value)
        elif field_name in {"temperature_c", "pain_intensity_0_10", "systolic_bp", "capillary_refill_seconds", "spo2", "duration_days"}:
            fields[field_name] = parse_float(value)
        else:
            fields[field_name] = value

    if fields.get("dental_fever"):
        fields["fever"] = True
    if fields.get("temperature_c") is not None and fields["temperature_c"] >= 37.6:
        fields["fever"] = True
    if fields.get("confusion"):
        fields["mental_status_change"] = True
    if fields.get("pain_location") == "abdomen" and (fields.get("pain_intensity_0_10") or 0) >= 8:
        fields["severe_abdominal_pain"] = True

    return fields


def eval_condition(case_fields: Dict[str, Any], cond: Dict[str, Any]) -> bool:
    field = cond.get("field")
    op = cond.get("op")
    value = cond.get("value")
    current = case_fields.get(field)
    if op == "==":
        return current == value
    if op == "!=":
        return current != value
    if current is None:
        return False
    if op == ">=":
        return current >= value
    if op == "<=":
        return current <= value
    if op == ">":
        return current > value
    if op == "<":
        return current < value
    return False


def eval_logic(case_fields: Dict[str, Any], logic: Dict[str, Any]) -> bool:
    if not logic:
        return False
    if "all" in logic:
        return all(eval_logic(case_fields, c) if isinstance(c, dict) and ("all" in c or "any" in c) else eval_condition(case_fields, c) for c in logic["all"])
    if "any" in logic:
        return any(eval_logic(case_fields, c) if isinstance(c, dict) and ("all" in c or "any" in c) else eval_condition(case_fields, c) for c in logic["any"])
    if "field" in logic:
        return eval_condition(case_fields, logic)
    return False


def symptom_matches(profile: Dict[str, Any], entry: Dict[str, Any]) -> bool:
    if entry.get("entry_class") != "symptom_entry":
        return False
    text = profile["complaint_norm"]
    flags = profile["normalized_flags"]
    ts = profile["text_signals"]

    terms = [norm_text(x) for x in entry.get("trigger_terms", [])]
    if any(term and term in text for term in terms):
        return True

    fallback = {
        "digestif": flags["digestive_symptom"],
        "respiratoire": flags["breathing_issue"],
        "urinaire": flags["urinary_burning"],
        "psychiatrique": flags["persistent_sadness"] or flags["anxiety"] or ts["suicidal_text"],
        "dentaire": flags["dental_pain"],
        "dermatologique": flags["rash"],
        "fievre": flags["fever"],
        "neurologique": flags["headache"] or profile["immediate_red_flags"].get("stroke_signs", False) or ts["seizure_like"] or profile["immediate_red_flags"].get("seizures", False),
        "transversal": flags["pain"],
    }
    return bool(fallback.get(entry.get("domain"), False))


def collect_questions(kb: Dict[str, Any], activated_ids: List[str], activated_domains: List[str], final_priority: Optional[str] = None) -> List[Dict[str, Any]]:
    if final_priority == "P1":
        return []
    questions: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    for entry in kb.get("entries", []):
        if entry.get("kb_id") not in activated_ids:
            continue
        for q in entry.get("triage_questions", []) or []:
            qid = q.get("id")
            if qid not in seen:
                seen.add(qid)
                questions.append(q)

    allowed_context_ids: Set[str] = set()
    for d in activated_domains:
        allowed_context_ids |= DOMAIN_CONTEXT_QUESTION_MAP.get(d, set())

    for q in GENERIC_CONTEXT_QUESTIONS:
        if q["id"] in allowed_context_ids and q["id"] not in seen:
            seen.add(q["id"])
            questions.append(q)

    return questions


def direct_p1_override(case_fields: Dict[str, Any]) -> Optional[Dict[str, str]]:
    for rule in DIRECT_P1_RULES:
        if case_fields.get(rule["field"], False):
            return rule
    return None


def run_triage_v3_3_production(payload: Dict[str, Any], kb: Dict[str, Any], dynamic_answers: Optional[Dict[str, Any]] = None) -> TriageResult:
    ensure_runtime_messages(kb)
    ensure_runtime_entries(kb)

    profile = normalize_input(payload)
    case_fields = build_case_fields(profile, dynamic_answers)

    activated_domains: List[str] = []
    activated_entries: List[str] = []
    activated_modifiers: List[str] = []
    activated_patterns: List[str] = []
    score_breakdown: List[str] = []
    reasons: List[str] = []
    score_total = 0

    route_ids: List[str] = []
    for entry in kb.get("entries", []):
        if entry.get("entry_class") == "symptom_entry" and symptom_matches(profile, entry):
            activated_entries.append(entry["kb_id"])
            if entry.get("domain") and entry["domain"] not in activated_domains:
                activated_domains.append(entry["domain"])
            for rid in entry.get("routes_to", []):
                if rid not in route_ids:
                    route_ids.append(rid)
            reasons.append(f"Symptôme activé: {entry['title']}")

    # Red flag direct, indépendant de la KB
    direct_rf = direct_p1_override(case_fields)
    if direct_rf:
        if direct_rf["reason"] in {"Convulsions", "Crise convulsive probable"} and "neurologique" not in activated_domains:
            activated_domains.append("neurologique")
        if direct_rf["reason"] == "Danger psychique immédiat" and "psychiatrique" not in activated_domains:
            activated_domains.append("psychiatrique")
        reasons.append(f"Red flag direct: {direct_rf['reason']}")
        return TriageResult(
            priority_code="P1",
            color=PRIORITY_META["P1"]["color"],
            urgency_label=PRIORITY_META["P1"]["urgency_label"],
            orientation=PRIORITY_META["P1"]["orientation_default"],
            message=direct_rf["message"],
            reasons=reasons,
            activated_domains=activated_domains,
            activated_entries=activated_entries,
            activated_modifiers=activated_modifiers,
            activated_patterns=activated_patterns,
            score_total=0,
            score_breakdown=["Red flag critique : override P1"],
            normalized_profile=profile,
            case_fields=case_fields,
            asked_questions=[],
        )

    # CORRECTION MAJEURE : on évalue tous les syndromes et patterns globaux, pas seulement les routes.
    eligible_ids = set(route_ids)
    for entry in kb.get("entries", []):
        if entry.get("entry_class") in {
            "context_modifier_entry",
            "risk_pattern_entry",
            "trajectory_modifier_entry",
            "epidemiology_context_entry",
            "red_flag_entry",
            "syndrome_entry",
        }:
            eligible_ids.add(entry["kb_id"])

    forced_priority: Optional[str] = None
    forced_orientation: Optional[str] = None
    forced_message: Optional[str] = None

    # Red flags KB
    for entry in kb.get("entries", []):
        if entry.get("kb_id") not in eligible_ids or entry.get("entry_class") != "red_flag_entry":
            continue
        for rule in entry.get("rules", []) or []:
            if eval_logic(case_fields, rule.get("logic", {})):
                activated_entries.append(entry["kb_id"])
                if entry.get("domain") and entry["domain"] not in activated_domains:
                    activated_domains.append(entry["domain"])
                decision = rule.get("decision", {})
                pri = decision.get("priority_level")
                if pri == "P1" or decision.get("score_override"):
                    reasons.append(f"Règle activée: {rule.get('id')} ({entry['title']})")
                    return TriageResult(
                        priority_code="P1",
                        color=PRIORITY_META["P1"]["color"],
                        urgency_label=PRIORITY_META["P1"]["urgency_label"],
                        orientation=decision.get("orientation") or PRIORITY_META["P1"]["orientation_default"],
                        message=message_for_key(kb, decision.get("message_key"), "Urgence vitale détectée."),
                        reasons=reasons,
                        activated_domains=activated_domains,
                        activated_entries=activated_entries,
                        activated_modifiers=activated_modifiers,
                        activated_patterns=activated_patterns,
                        score_total=0,
                        score_breakdown=["Red flag critique : override P1"],
                        normalized_profile=profile,
                        case_fields=case_fields,
                        asked_questions=[],
                    )

    # Modificateurs et patterns
    for entry in kb.get("entries", []):
        if entry.get("kb_id") not in eligible_ids:
            continue
        entry_class = entry.get("entry_class")
        if entry_class == "context_modifier_entry" and eval_logic(case_fields, entry.get("logic", {})):
            activated_modifiers.append(entry["title"])
            effect = entry.get("effect", {})
            delta = int(effect.get("score_delta", 0) or 0)
            score_total += delta
            if delta:
                score_breakdown.append(f"Modificateur {entry['title']}: +{delta}")
            min_priority = effect.get("min_priority")
            if min_priority:
                forced_priority = max_priority(forced_priority, min_priority)
            reasons.append(f"Modificateur activé: {entry['title']}")
            if entry.get("domain") and entry["domain"] not in activated_domains:
                activated_domains.append(entry["domain"])

        elif entry_class in {"risk_pattern_entry", "trajectory_modifier_entry", "epidemiology_context_entry"} and eval_logic(case_fields, entry.get("logic", {})):
            activated_patterns.append(entry["title"])
            effect = entry.get("effect", {})
            delta = int(effect.get("score_delta", 0) or 0)
            score_total += delta
            if delta:
                score_breakdown.append(f"Pattern {entry['title']}: +{delta}")
            min_priority = effect.get("min_priority") or effect.get("upgrade_to")
            if min_priority:
                forced_priority = max_priority(forced_priority, min_priority)
            msg = message_for_key(kb, effect.get("message_key"), "")
            if msg and not forced_message:
                forced_message = msg
            reasons.append(f"Pattern activé: {entry['title']}")
            if entry.get("domain") and entry["domain"] not in activated_domains:
                activated_domains.append(entry["domain"])

    # Syndromes : meilleur par domaine
    best_syndrome_by_domain: Dict[str, Dict[str, Any]] = {}
    for entry in kb.get("entries", []):
        if entry.get("kb_id") not in eligible_ids or entry.get("entry_class") != "syndrome_entry":
            continue
        for rule in entry.get("rules", []) or []:
            if eval_logic(case_fields, rule.get("logic", {})):
                decision = rule.get("decision", {})
                base_score = int(decision.get("base_score", 0) or 0)
                domain = entry.get("domain", "unknown")
                candidate = {"entry": entry, "rule": rule, "base_score": base_score, "priority": decision.get("priority_level")}
                current = best_syndrome_by_domain.get(domain)
                if current is None or base_score > current["base_score"] or (
                    base_score == current["base_score"] and PRIORITY_RANK.get(candidate["priority"], 0) > PRIORITY_RANK.get(current["priority"], 0)
                ):
                    best_syndrome_by_domain[domain] = candidate
                break

    for domain, candidate in best_syndrome_by_domain.items():
        entry = candidate["entry"]
        rule = candidate["rule"]
        decision = rule.get("decision", {})
        base_score = candidate["base_score"]
        activated_entries.append(entry["kb_id"])
        if domain not in activated_domains:
            activated_domains.append(domain)
        if base_score:
            score_total += base_score
            score_breakdown.append(f"{entry['title']}: +{base_score}")
        reasons.append(f"Règle activée: {rule.get('id')} ({entry['title']})")
        forced_priority = max_priority(forced_priority, decision.get("priority_level"))
        msg = message_for_key(kb, decision.get("message_key"), "")
        if msg and not forced_message:
            forced_message = msg
        if decision.get("orientation") and not forced_orientation:
            forced_orientation = decision.get("orientation")

    score_priority = priority_from_score(score_total)
    final_priority = max_priority(score_priority, forced_priority) or "P4"
    orientation = forced_orientation or PRIORITY_META[final_priority]["orientation_default"]
    message = forced_message or message_for_key(kb, {"P1": "MSG_P1_GENERAL", "P2": "MSG_P2_GENERAL", "P3": "MSG_P3_GENERAL", "P4": "MSG_P4_GENERAL"}[final_priority], "")
    asked_questions = collect_questions(kb, list({*activated_entries, *route_ids}), activated_domains, final_priority=final_priority)

    return TriageResult(
        priority_code=final_priority,
        color=PRIORITY_META[final_priority]["color"],
        urgency_label=PRIORITY_META[final_priority]["urgency_label"],
        orientation=orientation,
        message=message,
        reasons=reasons,
        activated_domains=activated_domains,
        activated_entries=activated_entries,
        activated_modifiers=activated_modifiers,
        activated_patterns=activated_patterns,
        score_total=score_total,
        score_breakdown=score_breakdown,
        normalized_profile=profile,
        case_fields=case_fields,
        asked_questions=asked_questions,
    )


# CLI

def ask_bool(prompt: str) -> bool:
    """Lecture oui/non robuste pour usage terrain.

    Accepte les variantes fréquentes saisies sous stress :
    o/oui/y/yes/1/vrai, n/non/no/0/faux, ainsi que oo/nn.
    Une réponse vide reste invalide pour éviter de valider par erreur un red flag.
    """
    yes_values = {"o", "oui", "ou", "y", "yes", "1", "vrai", "true", "ok", "daccord", "d accord", "oo"}
    no_values = {"n", "non", "no", "0", "faux", "false", "nn", "non non"}
    while True:
        raw = input(f"{prompt} (o/n) : ")
        v = norm_text(raw).strip()
        if v in yes_values or (len(v) > 1 and set(v) == {"o"}):
            return True
        if v in no_values or (len(v) > 1 and set(v) == {"n"}):
            return False
        print("Réponse invalide. Répondez par oui ou non (o/n).")


def choose_one(prompt: str, options: List[str]) -> str:
    print(prompt)
    for i, opt in enumerate(options, start=1):
        print(f"  {i}. {opt}")
    while True:
        v = input("Votre choix : ").strip()
        if v.isdigit() and 1 <= int(v) <= len(options):
            return options[int(v) - 1]
        print("Choix invalide. Recommencez.")


def choose_many(prompt: str, options: List[str]) -> List[str]:
    print(prompt)
    for i, opt in enumerate(options, start=1):
        print(f"  {i}. {opt}")
    print("Entrez les numéros séparés par des virgules. Exemple : 1,3,5")
    while True:
        raw = input("Votre choix : ").strip()
        try:
            nums = [int(x.strip()) for x in raw.split(",") if x.strip()]
            if all(1 <= n <= len(options) for n in nums):
                return [options[n - 1] for n in nums]
        except Exception:
            pass
        print("Choix invalide. Recommencez.")


def interactive_cli() -> None:
    kb = load_kb()
    print("=" * 80)
    print("SERVICE DE TRIAGE - MODE INTERACTIF (MOTEUR V3.3 PRODUCTION)")
    print("Ce service donne une orientation et non un diagnostic.")
    print("En cas d'urgence vitale, rendez-vous immédiatement à l'hôpital.")
    print("=" * 80)

    payload = {
        "complaint_text": input("1. Quelle est votre plainte principale ? ").strip(),
        "duration": choose_one("\n2. Depuis quand avez-vous ce problème ?", DURATION_OPTIONS),
        "associated_signs": choose_many("\n3. Avez-vous des signes associés ?", ASSOCIATED_OPTIONS),
        "prior_consultation": choose_one("\n4. Avez-vous déjà consulté pour ce problème ?", CONSULT_OPTIONS),
        "attachment_present": ask_bool("5. Voulez-vous signaler qu'une photo ou un document est disponible ?"),
        "medical_history": choose_many("\n6. Quels sont vos antécédents médicaux ?", HISTORY_OPTIONS),
        "date_of_birth": input("7. Date de naissance (JJ/MM/AAAA) : ").strip(),
        "weight_kg": input("8. Poids en kg (optionnel) : ").strip(),
        "height_m": input("8b. Taille en mètre (optionnel) : ").strip(),
        "sex": input("Sexe (Homme/Femme) : ").strip(),
        "pregnant": False,
        "province": input("Province : ").strip(),
        "immediate_red_flags": {},
    }

    if norm_text(payload["sex"]) == "femme":
        payload["pregnant"] = ask_bool("Êtes-vous enceinte ?")

    print("\nSignes d'alerte immédiats :")
    for key, label in IMMEDIATE_RED_FLAG_KEYS.items():
        payload["immediate_red_flags"][key] = ask_bool(label)

    preview = run_triage_v3_3_production(payload, kb, dynamic_answers={})
    print("\n[DEBUG V3.3] Domaines activés :", preview.activated_domains)
    print("[DEBUG V3.3] Entrées activées :", preview.activated_entries)
    print("[DEBUG V3.3] Score initial :", preview.score_total)

    dynamic_answers: Dict[str, Any] = {}
    if preview.priority_code != "P1" and preview.asked_questions:
        print("\n" + "=" * 80)
        print("QUESTIONS COMPLÉMENTAIRES")
        for q in preview.asked_questions:
            qid = q.get("id")
            qlabel = q.get("label")
            qtype = q.get("type")
            if qtype == "boolean":
                dynamic_answers[qid] = ask_bool(qlabel)
            elif qtype == "single_select":
                dynamic_answers[qid] = choose_one(f"\n{qlabel}", q.get("options", []))
            else:
                dynamic_answers[qid] = input(f"{qlabel} : ").strip()

    result = run_triage_v3_3_production(payload, kb, dynamic_answers=dynamic_answers)
    print("\n" + "=" * 80)
    print("RÉSULTAT FINAL")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    interactive_cli()
