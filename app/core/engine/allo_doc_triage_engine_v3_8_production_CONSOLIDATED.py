from __future__ import annotations
import time
"""
ALLODOCTEUR - MOTEUR V3.8 PRODUCTION CONSOLIDÉ
==============================================

Cette version remplace la logique finale V3.8 sans multiplier les fichiers.
Elle reste compatible avec la pile existante V3.7/V3.6/V3.5, mais ajoute une
surcouche clinique plus robuste :

1. NLP médical renforcé : négations, fautes fréquentes, phrases incomplètes,
   symptômes implicites, langage parent/patient.
2. Cohérence globale : case_fields, normalized_profile, reasons, messages et
   activated_entries sont resynchronisés après correction.
3. Urgences implicites sans dépendre uniquement des checkboxes : AVC, suicide,
   déshydratation, douleur thoracique, méningite, appendicite, détresse respiratoire.
4. Multiplicités associées : combinaisons de symptômes et contextes aggravants.
5. Contexte Afrique/RDC + contexte global : paludisme, choléra, TB, infections,
   tout en gardant les règles utiles hors Afrique.
6. Modules spécialisés : digestif, abdominal, respiratoire/asthme, cardio,
   neurologique, psy, urinaire/rénal, dentaire, dermatologique, ORL, pédiatrie.

Ce moteur donne une ORIENTATION DE TRIAGE, pas un diagnostic médical autonome.
"""

from dataclasses import asdict
from typing import Any, Dict, Optional, List, Set, Callable
from pathlib import Path
import csv
import json
import re

try:
    from medical_nlp_extractor import extract_medical_features
except Exception:
    extract_medical_features = None

# Extracteur large optionnel (modèle 143 features en span extraction / QA).
# Ce module reste indépendant de medical_nlp_extractor.py.

USE_SPAN_EXTRACTOR = False
extract_features_from_note = None

try:
    import allo_doc_triage_engine_v3_7_africa as v37
except ImportError:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parent))
    import allo_doc_triage_engine_v3_7_africa as v37

# V3.9 intégré nativement ci-dessous

base = v37.base


#_extract_span_features

# -----------------------------------------------------------------------------
# CONSTANTES CONTEXTE
# -----------------------------------------------------------------------------

DRC_PROVINCES: Set[str] = {
    "kinshasa", "kongo central", "kwango", "kwilu", "mai ndombe", "mai ndombe",
    "kasai", "kasai central", "kasai oriental", "lomami", "sankuru",
    "haut lomami", "haut katanga", "lualaba", "tanganyika", "sud kivu",
    "nord kivu", "maniema", "tshopo", "ituri", "bas uele", "haut uele",
    "mongala", "nord ubangi", "sud ubangi", "equateur", "tshuapa"
}

HIGH_CHOLERA_RISK_PROVINCES: Set[str] = {
    "kinshasa", "kongo central", "kwilu", "mai ndombe", "equateur", "tshopo",
    "nord kivu", "sud kivu", "tanganyika", "haut lomami", "ituri", "sankuru"
}

NEGATION_TERMS = [
    "sans", "pas de", "pas d", "aucun", "aucune", "ni", "jamais de",
    "ne presente pas", "ne présente pas", "n a pas", "n ai pas", "n'a pas", "n'ai pas",
    "ne ressent pas", "ne souffre pas de"
]

SPELL_CORRECTIONS = {
    "vente": "ventre",
    "boutopns": "boutons",
    "fatique": "fatigue",
    "fiable": "faible",
    "ma faire du mal": "me faire du mal",
    "essoufle": "essouffle",
    "essouffle": "essouffle",
    "fievre": "fievre",
    # [FIX V3.9] Fautes RDC sur "boire"
    "ne boir plus": "ne peut plus boire",
    "ne boire plus": "ne peut plus boire",
    "ne bois plus": "ne peut plus boire",
    "il ne boir": "il ne peut plus boire",
    "elle ne boir": "elle ne peut plus boire",
    "boir plus": "peut plus boire",
    # [FIX V3.9] Fièvre subjective RDC
    "il est chaud": "il a de la fievre",
    "elle est chaude": "elle a de la fievre",
    "bebe est chaud": "bebe a de la fievre",
    "est chaud depuis": "a fievre depuis",
    "chaud depuis": "fievre depuis",
    "il a chaud": "il a de la fievre",
    "elle a chaud": "elle a de la fievre",
    # [FIX V3.9] Autres fautes fréquentes
    "convultion": "convulsion",
    "convultions": "convulsions",
    "grossese": "grossesse",
    "encinte": "enceinte",
    "saignment": "saignement",
    "diarée": "diarrhee",
    "mal o ": "mal au ",
    "o vantre": "au ventre",
    "o ventre": "au ventre",
}

# -----------------------------------------------------------------------------
# UTILITAIRES NLP
# -----------------------------------------------------------------------------

def norm(text: Any) -> str:
    try:
        s = base.norm_text(str(text or ""))
    except Exception:
        s = str(text or "").lower()
    for wrong, right in SPELL_CORRECTIONS.items():
        s = re.sub(rf"\b{re.escape(wrong)}\b", right, s)
    return re.sub(r"\s+", " ", s).strip()


def has_any(text: str, patterns: List[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def has_negated(text: str, patterns: List[str], window: int = 6) -> bool:
    """
    Détecte une négation locale, y compris 'sans X ni Y'.
    [FIX V3.9] Fenêtre réduite à 6 mots et la négation doit PRÉCÉDER le symptôme.
    Corrige le faux positif : 'il est chaud, il ne boir plus' ne niait pas 'chaud'.
    """
    words = text.split()
    for i in range(len(words)):
        for neg in NEGATION_TERMS:
            neg_words = norm(neg).split()
            if words[i:i + len(neg_words)] == neg_words:
                # Zone après la négation seulement
                zone_after_neg = " ".join(words[i + len(neg_words): i + len(neg_words) + window])
                if any(re.search(p, zone_after_neg) for p in patterns):
                    return True
    # Forme explicite : sans vomissements ni fièvre
    for p in patterns:
        if re.search(rf"sans .{{0,40}}\bni\b .{{0,20}}{p}", text):
            return True
    return False


def detect_positive(text: str, positive_patterns: List[str], negation_patterns: Optional[List[str]] = None) -> bool:
    negation_patterns = negation_patterns or positive_patterns
    if has_negated(text, negation_patterns):
        return False
    return has_any(text, positive_patterns)


def priority_rank(p: str) -> int:
    return {"P1": 4, "P2": 3, "P3": 2, "P4": 1}.get(p, 0)


def add_unique(seq: List[str], item: Optional[str]) -> None:
    if item and item not in seq:
        seq.append(item)


def remove_items_containing(seq: List[str], tokens: List[str]) -> List[str]:
    toks = [norm(t) for t in tokens]
    return [x for x in seq if not any(t in norm(x) for t in toks)]


def set_result(
    result: Any,
    priority: str,
    message: str,
    reason: str,
    domain: Optional[str] = None,
    entry: Optional[str] = None,
    orientation: Optional[str] = None,
    allow_downgrade: bool = False,
):
    if not allow_downgrade and priority_rank(priority) < priority_rank(result.priority_code):
        return result
    if allow_downgrade and result.priority_code == "P1":
        return result

    result.priority_code = priority
    result.color = base.PRIORITY_META[priority]["color"]
    result.urgency_label = base.PRIORITY_META[priority]["urgency_label"]
    result.orientation = orientation or base.PRIORITY_META[priority]["orientation_default"]
    result.message = message
    add_unique(result.reasons, reason)
    if domain:
        add_unique(result.activated_domains, domain)
    if entry:
        add_unique(result.activated_entries, entry)
    return result


# -----------------------------------------------------------------------------
# NLP HYBRIDE : CRITIQUE + SPAN EXTRACTION 143 FEATURES
# -----------------------------------------------------------------------------

_FEATURES_CACHE: Optional[List[Dict[str, Any]]] = None


def _load_features_csv() -> List[Dict[str, Any]]:
    """Charge features.csv si le span extractor historique demande une liste de features.

    Le moteur ne dépend pas obligatoirement de ce fichier : si absent, on ignore
    simplement la couche span large.
    """
    global _FEATURES_CACHE
    if _FEATURES_CACHE is not None:
        return _FEATURES_CACHE

    candidate_paths = [
        Path(__file__).resolve().parent / "features.csv",
        Path(__file__).resolve().parent.parent / "features.csv",
        Path("features.csv"),
    ]
    for path in candidate_paths:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                _FEATURES_CACHE = list(csv.DictReader(f))
            return _FEATURES_CACHE

    _FEATURES_CACHE = []
    return _FEATURES_CACHE


def _map_span_items_to_fields(span_items: Any) -> Dict[str, bool]:
    """Convertit les sorties du modèle 143 features vers les champs utiles AlloDocteur.

    Le modèle span est un enrichisseur large : il ne doit jamais supprimer ou nier
    un signal critique déjà trouvé par le NLP manuel. On ne renvoie donc que des
    booléens positifs.
    """
    fields: Dict[str, bool] = {}
    if not span_items:
        return fields

    if isinstance(span_items, dict):
        # Format déjà prêt : {"fields": {...}} ou {"nlp_fields": {...}}
        raw = span_items.get("fields") or span_items.get("nlp_fields") or span_items.get("span_fields")
        if isinstance(raw, dict):
            return {str(k): bool(v) for k, v in raw.items() if bool(v)}
        items = span_items.get("spans") or span_items.get("features") or span_items.get("results") or []
    else:
        items = span_items

    if not isinstance(items, list):
        return fields

    mapping = {
        "pregnant": ["pregnan", "grossesse", "enceinte"],
        "fever": ["fever", "febrile", "fievre", "fièvre"],
        "chills": ["chills", "frissons"],
        "headache": ["headache", "cephalea", "céphal", "maux de tete", "maux de tête"],
        "severe_headache": ["severe headache", "forts maux", "violent headache", "maux de tete intense"],
        "visual_disturbance": ["blurry vision", "vision", "visual", "vision floue", "troubles visuels"],
        "vaginal_bleeding": ["vaginal bleeding", "bleeding", "saignement", "pertes de sang"],
        "vomiting": ["vomiting", "vomit", "vomissement", "vomissements"],
        "diarrhea": ["diarrhea", "diarrhoea", "diarrhee", "diarrhée"],
        "unable_to_drink": ["unable to drink", "can't drink", "cannot drink", "ne boit plus", "vomit all", "vomit tout"],
        "dehydration": ["dehydrat", "déshydrat", "dry mouth", "urine low"],
        "abdominal_pain": ["abdominal pain", "belly pain", "stomach pain", "ventre", "abdomen"],
        "lower_abdominal_pain": ["lower abdominal", "pelvic pain", "bas du ventre", "pelvienne"],
        "lower_right_abdominal_pain": ["right lower", "right iliac", "rlq", "bas a droite", "bas à droite"],
        "severe_abdominal_pain": ["severe abdominal", "intense abdominal", "douleur intense", "ventre tres douloureux"],
        "chest_pain": ["chest pain", "chest pressure", "poitrine", "thoracic"],
        "breathing_issue": ["shortness of breath", "dyspnea", "breathing", "essouffl", "respir"],
        "stroke_signs": ["stroke", "weakness", "speech difficulty", "facial droop", "avc", "parle difficilement"],
        "suicidal_text": ["suicid", "self harm", "me faire du mal", "envie de mourir"],
        "cough": ["cough", "toux"],
        "weight_loss": ["weight loss", "perte de poids", "amaigr"],
        "night_sweats": ["night sweats", "sueurs nocturnes"],
        "urinary_burning": ["dysuria", "urinary burning", "brule", "brûle", "urine"],
        "flank_pain": ["flank", "kidney", "rein", "flanc"],
        "dental_swelling": ["dental", "tooth", "swelling", "joue gonfl", "abc"],
        "neck_stiffness": ["neck stiffness", "stiff neck", "raideur", "nuque"],
    }

    for item in items:
        if not isinstance(item, dict):
            continue
        text_blob = " ".join(str(item.get(k, "")) for k in [
            "feature_text", "span", "text", "label", "entity", "entity_group"
        ]).lower()
        for target, keywords in mapping.items():
            if any(k.lower() in text_blob for k in keywords):
                fields[target] = True
    return fields


def _extract_span_bundle(raw_text: str) -> Dict[str, Any]:
    """Appelle la couche span large si disponible, sans jamais bloquer le moteur."""
    if not raw_text:
        return {"span_fields": {}, "span_items": [], "span_error": None}

    try:
        if _extract_span_features is not None:
            out = _extract_span_features(raw_text) or {}
            if isinstance(out, dict):
                fields = out.get("span_fields") or out.get("nlp_fields") or out.get("fields")
                if not isinstance(fields, dict):
                    fields = _map_span_items_to_fields(out)
                items = out.get("spans") or out.get("features") or out.get("results") or []
                return {"span_fields": fields or {}, "span_items": items or [], "span_error": None}
            return {"span_fields": _map_span_items_to_fields(out), "span_items": out or [], "span_error": None}

        if _extract_features_from_note is not None:
            features_rows = _load_features_csv()
            if not features_rows:
                return {"span_fields": {}, "span_items": [], "span_error": "features.csv introuvable"}
            items = _extract_features_from_note(raw_text, features_rows) or []
            return {"span_fields": _map_span_items_to_fields(items), "span_items": items, "span_error": None}

        return {"span_fields": {}, "span_items": [], "span_error": "medical_nlp_span_extractor indisponible"}
    except Exception as exc:
        return {"span_fields": {}, "span_items": [], "span_error": str(exc)}

# -----------------------------------------------------------------------------
# EXTRACTION SIGNAUX CLINIQUES CONSOLIDÉE
# -----------------------------------------------------------------------------

def _age_from_dob(dob: Any) -> Optional[int]:
    s = str(dob or "").strip()
    if "/" not in s:
        return None
    try:
        # Cohérent avec tes versions précédentes, mais stable pour 2026.
        from datetime import date as _date
        parts = s.strip().split("/")
        if len(parts) == 3:
            born = _date(int(parts[2]), int(parts[1]), int(parts[0]))
            return (_date.today() - born).days // 365
        return _date.today().year - int(parts[-1])
    except Exception:
        return None


def _duration_days(payload: Dict[str, Any], text: str) -> int:
    raw = norm(payload.get("duration", ""))
    days: Optional[int] = None
    if "moins de 24" in raw:
        days = 1
    elif "1 a 3" in raw or "1 à 3" in raw:
        days = 2
    elif "4 a 7" in raw or "4 à 7" in raw:
        days = 5
    elif "semaine" in raw:
        days = 8
    elif "mois" in raw:
        days = 35
    elif "annee" in raw:
        days = 365

    if has_any(text, [r"depuis hier"]):
        days = 1
    elif has_any(text, [r"deux jours", r"2 jours"]):
        days = 2
    elif has_any(text, [r"quelques jours"]):
        days = days or 4
    elif has_any(text, [r"plusieurs jours"]):
        days = days or 5
    elif has_any(text, [r"deux semaines", r"2 semaines"]):
        days = 14
    elif has_any(text, [r"plusieurs semaines", r"trois semaines", r"3 semaines"]):
        days = 21
    elif has_any(text, [r"plus d un mois", r"un mois"]):
        days = 35
    return days or 2


def extract_v38_signals(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_text = str(payload.get("complaint_text", "") or "")
    text = norm(raw_text)

    # 1) NLP critique : medical_nlp_extractor.py
    nlp_bundle: Dict[str, Any] = {}
    nlp_fields: Dict[str, Any] = {}
    nlp_entities: List[Dict[str, Any]] = []
    if extract_medical_features is not None:
        try:
            nlp_bundle = extract_medical_features(raw_text) or {}
            nlp_fields = nlp_bundle.get("nlp_fields", {}) or {}
            nlp_entities = nlp_bundle.get("nlp_entities", []) or []
        except Exception:
            nlp_bundle, nlp_fields, nlp_entities = {}, {}, []

    # 2) NLP large : medical_nlp_span_extractor.py (optionnel, 143 features)
    #span_bundle = _extract_span_bundle(raw_text)
    span_fields: Dict[str, Any] = {}
    span_items: List[Dict[str, Any]] = []
    span_error = None

    # Fusion : le span large ajoute des signaux ; le NLP critique garde la priorité
    # pour les négations et les règles de sécurité.
    merged_nlp_fields: Dict[str, Any] = dict(span_fields)
    merged_nlp_fields.update(nlp_fields)
    nlp_fields = merged_nlp_fields

    associated = [norm(x) for x in payload.get("associated_signs", [])]
    history = [norm(x) for x in payload.get("medical_history", [])]
    red = payload.get("immediate_red_flags", {}) or {}
    province = norm(payload.get("province", ""))
    sex = norm(payload.get("sex", ""))
    age = _age_from_dob(payload.get("date_of_birth"))
    duration_days = _duration_days(payload, text)

    is_drc = province in DRC_PROVINCES or province == "rdc" or "congo" in province
    africa_context = is_drc or province in {"brazzaville", "abidjan", "douala", "yaounde", "lagos", "dakar", "bamako"}
    endemic_area = is_drc or bool(payload.get("endemic_area"))
    high_cholera_context = bool(payload.get("high_cholera_context")) or province in HIGH_CHOLERA_RISK_PROVINCES

    fever_p = [r"\bfievre\b", r"temperature", r"chaud.*corps", r"frissons",
               r"il est chaud", r"elle est chaude", r"bebe.*chaud", r"enfant.*chaud",
               r"a de la fievre", r"il a de la fievre",
               r"bebe.*fievre", r"38", r"39", r"40", r"41"]
    vomit_p = [r"\bvomis\b", r"vomit", r"vomissement", r"vomissements", r"rejette tout"]
    diarrhea_p = [r"diarrh", r"selles liquides", r"selles aqueuses", r"eau de riz"]
    pain_p = [r"douleur", r"tres mal", r"forte douleur", r"mal a", r"mal au", r"mal aux"]

    fever = detect_positive(text, fever_p) or (any("fievre" in x for x in associated) and not has_negated(text, fever_p))
    vomiting = detect_positive(text, vomit_p) or (any("vomissements" in x for x in associated) and not has_negated(text, vomit_p))
    diarrhea = detect_positive(text, diarrhea_p) or (any("diarrhee" in x for x in associated) and not has_negated(text, diarrhea_p))
    digestive = vomiting or diarrhea

    cough = detect_positive(text, [r"\btoux\b", r"tousse", r"tousser", r"crachat", r"crache"])
    sputum = detect_positive(text, [r"crachat", r"crache"])
    hemoptysis = detect_positive(text, [r"crache.*sang", r"sang.*crachat", r"toux.*sang"])
    night_sweats = detect_positive(text, [r"sueurs nocturnes", r"transpire.*nuit", r"sueur.*nuit"])
    weight_loss = detect_positive(text, [r"perte de poids", r"maigri", r"amaigr", r"minci"])
    appetite_loss = detect_positive(text, [r"perte d appetit", r"pas d appetit", r"mange plus"]) or any("perte d appetit" in x for x in associated)
    fatigue = detect_positive(text, [r"fatigue", r"faible", r"faiblesse", r"courbature", r"mou", r"abattu"]) or any("fatigue" in x for x in associated)

    breathing_issue = (
        detect_positive(text, [r"essouffl", r"difficulte.*respir", r"respire mal", r"manque d air", r"cherche l air"])
        or any("essoufflement" in x for x in associated)
        or bool(red.get("severe_breathing"))
    )
    respiratory_distress = bool(red.get("severe_breathing")) or detect_positive(text, [
        r"respire tres mal", r"n arrive pas a respirer", r"cherche l air", r"etouffe",
        r"ne finit pas ses phrases", r"parle difficilement"  # attention: aussi AVC, géré plus bas
    ])

    unable_to_drink = detect_positive(text, [
        r"ne peux plus boire", r"peux plus boire", r"ne peux pas boire", r"ne peut plus boire", r"peut plus boire", r"ne peut pas boire",
        r"ne boit plus", r"ne boir plus", r"ne boi plus", r"refuse de boire",
        r"incapable de boire", r"n arrive pas a boire", r"plu boire",
        r"ne garde pas les liquides", r"vomit tout", r"vomis tout", r"rejette tout",
        r"rend tout", r"vomis.*tout", r"garde.*rien"
    ,
        # [FIX V3.9] Fautes sur "boire" fréquentes RDC
        r"ne boir plus", r"ne boir\b", r"peut plus boir",
        r"rend tout", r"rejette.*tout", r"garde.*rien",
    ])
    can_drink = detect_positive(text, [r"je peux boire", r"peut boire", r"boit normalement", r"bois normalement", r"arrive a boire"])
    urine_output_low = detect_positive(text, [r"urine presque plus", r"urine tres peu", r"plus d urine", r"pipi tres peu"])
    dehydration = (
        detect_positive(text, [r"bouche seche", r"soif intense", r"yeux creux", r"urine presque plus", r"urine tres peu", r"tres faible", r"somnolent"])
        or bool(red.get("severe_dehydration"))
        or bool(red.get("severe_diarrhea_unable_to_drink"))
        or (digestive and unable_to_drink)
    )

    chest_pain = detect_positive(text, [r"poitrine", r"thorax", r"thorac", r"oppression", r"serrement", r"pression.*poitrine"])
    pleuritic_chest_pain = chest_pain and detect_positive(text, [r"respire profond", r"inspiration", r"quand je respire"])
    chest_pressure = bool(red.get("chest_pressure")) or (chest_pain and detect_positive(text, [r"pression", r"serre", r"oppression"]))

    stroke_signs = bool(red.get("stroke_signs")) or detect_positive(text, [
        r"faiblesse.*cote", r"un cote.*faible", r"bras.*faible", r"jambe.*faible",
        r"difficilement.*parle", r"parle difficilement", r"difficulte a parler", r"bouche.*devi", r"visage.*devi"
    ])
    # Si c'est neurologique, ne pas confondre "parle difficilement" avec détresse respiratoire.
    if stroke_signs and not has_any(text, [r"respire", r"air", r"etouff", r"essouff"]):
        respiratory_distress = False

    neck_stiffness = bool(red.get("fever_with_neck_stiffness")) or detect_positive(text, [r"raideur.*cou", r"raideur.*nuque", r"nuque raide", r"cou raide", r"cou bloque"])
    headache = detect_positive(text, [r"maux de tete", r"mal a la tete", r"cephale"]) or any("maux de tete" in x for x in associated)
    meningitis = (fever and neck_stiffness) or bool(red.get("fever_with_neck_stiffness"))
    seizures = bool(red.get("seizures")) or detect_positive(text, [r"convulsion", r"crise convulsive", r"tremblements incontr", r"secousses"])
    confusion = bool(red.get("sudden_confusion")) or detect_positive(text, [r"confusion", r"confus", r"delire", r"desoriente", r"comportement bizarre"])

    suicidal = bool(red.get("suicidal_or_extreme_psy")) or detect_positive(text, [
        r"envie de mourir", r"me suicider", r"suicide", r"mettre fin a mes jours", r"me faire du mal", r"disparaitre", r"fatigue de vivre"
    ])
    anxiety = detect_positive(text, [r"stress", r"stresse", r"anxieux", r"anxiete", r"angoisse"]) or any("anxiete" in x for x in associated)
    sleep_disorder = detect_positive(text, [r"dors mal", r"insomnie", r"sommeil"]) or any("troubles du sommeil" in x for x in associated)
    persistent_sadness = detect_positive(text, [r"triste", r"tristesse", r"pleure"]) or any("tristesse" in x for x in associated)
    loss_of_interest = detect_positive(text, [r"envie de rien", r"plus envie", r"perte d interet", r"plaisir"]) or any("perte d interet" in x for x in associated)

    urinary_burning = detect_positive(text, [r"brule.*urin", r"brulure.*urin", r"pique.*urin", r"douleur.*urin", r"ca brule.*urine"])
    urinary_frequency = detect_positive(text, [r"urine souvent", r"uriner souvent", r"envie frequente", r"toilettes souvent"])
    hematuria = detect_positive(text, [r"sang.*urine", r"urines rouges"])

    back_pain = detect_positive(text, [r"mal au dos", r"douleur.*dos", r"lombalg", r"bas du dos"])
    flank_pain = detect_positive(text, [r"flanc", r"cote.*dos", r"douleur.*rein", r"reins", r"colique neph"])

    abdominal_pain = detect_positive(text, [r"mal au ventre", r"douleur.*ventre", r"douleur.*abd", r"ventre.*douloureux", r"bas.*ventre"])
    lower_abdominal_pain = detect_positive(text, [r"bas.*ventre", r"douleur.*pelv", r"douleur.*bas"])
    lower_right_abdominal_pain = detect_positive(text, [
        r"bas a droite.*ventre", r"bas droite.*ventre", r"droite.*bas.*ventre", r"fosse iliaque droite",
        r"cote droit.*bas.*ventre", r"bas a droite.*abd"
    ])
    severe_abdominal_pain = bool(red.get("board_like_abdomen")) or detect_positive(text, [r"douleur forte.*ventre", r"douleur intense.*ventre", r"ventre tres douloureux", r"ventre dur"])
    pain_intense = detect_positive(text, [r"douleur forte", r"forte douleur", r"douleurs intenses", r"tres mal", r"insupportable"]) or any("douleurs intenses" in x for x in associated)
    pain = detect_positive(text, pain_p) or pain_intense or any("douleurs intenses" in x for x in associated)

    rash = detect_positive(text, [r"boutons", r"eruption", r"plaques", r"taches", r"cloques", r"rougeurs"]) or any("eruption" in x for x in associated)
    itching = detect_positive(text, [r"demange", r"gratte", r"prurit"])
    allergy_history = any("allerg" in x for x in history)

    dental_pain = detect_positive(text, [r"\bdent\b", r"dentaire", r"gencive", r"molaire", r"joue.*gonfl", r"abces"])
    dental_swelling = dental_pain and detect_positive(text, [r"gonfl", r"joue", r"visage", r"abces", r"enfl"])
    difficulty_swallowing = detect_positive(text, [r"difficile.*avaler", r"mal.*avaler", r"n arrive pas.*avaler"])

    runny_nose = detect_positive(text, [r"nez qui coule", r"rhume", r"rhinorrhee"])
    sore_throat = detect_positive(text, [r"mal a la gorge", r"gorge", r"angine"])

    diabetes = any("diabete" in x for x in history)
    hypertension = any("hypertension" in x for x in history)
    asthma = any("asthme" in x for x in history)
    depression_history = any("depression" in x for x in history)
    immunocompromised = bool(payload.get("immunocompromised")) or any("vih" in x or "immun" in x for x in history)

    child = "enfant" in text or (age is not None and age <= 5)
    child_under_5 = age is not None and age < 5
    pregnant = bool(payload.get("pregnant")) or detect_positive(text, [r"enceinte", r"grossesse"])

    # Apports du NLP hybride. Les négations détectées par medical_nlp_extractor
    # ont priorité sur les signaux positifs du span extractor.
    fever = (fever or bool(nlp_fields.get("fever"))) and not bool(nlp_fields.get("fever_negated"))
    vomiting = (vomiting or bool(nlp_fields.get("vomiting"))) and not bool(nlp_fields.get("vomiting_negated"))
    diarrhea = (diarrhea or bool(nlp_fields.get("diarrhea"))) and not bool(nlp_fields.get("diarrhea_negated"))
    digestive = vomiting or diarrhea
    fatigue = fatigue or bool(nlp_fields.get("fatigue"))
    headache = headache or bool(nlp_fields.get("headache")) or bool(nlp_fields.get("severe_headache"))
    severe_headache = bool(nlp_fields.get("severe_headache"))
    visual_disturbance = bool(nlp_fields.get("visual_disturbance"))
    pregnant = pregnant or bool(nlp_fields.get("pregnant"))
    vaginal_bleeding = bool(nlp_fields.get("vaginal_bleeding")) or detect_positive(text, [r"saignement vaginal", r"je saigne", r"pertes de sang", r"saignements?"])
    abdominal_pain = abdominal_pain or bool(nlp_fields.get("abdominal_pain"))
    lower_abdominal_pain = lower_abdominal_pain or bool(nlp_fields.get("lower_abdominal_pain"))
    lower_right_abdominal_pain = lower_right_abdominal_pain or bool(nlp_fields.get("lower_right_abdominal_pain")) or bool(nlp_fields.get("appendicitis_risk"))
    severe_abdominal_pain = severe_abdominal_pain or bool(nlp_fields.get("severe_abdominal_pain")) or (abdominal_pain and pain_intense)
    unable_to_drink = unable_to_drink or bool(nlp_fields.get("unable_to_drink"))
    dehydration = dehydration or bool(nlp_fields.get("dehydration")) or bool(nlp_fields.get("severe_dehydration"))
    stroke_signs = stroke_signs or bool(nlp_fields.get("stroke_signs"))
    suicidal = suicidal or bool(nlp_fields.get("suicidal_text"))
    urinary_burning = urinary_burning or bool(nlp_fields.get("urinary_burning"))
    flank_pain = flank_pain or bool(nlp_fields.get("flank_pain"))
    dental_swelling = dental_swelling or bool(nlp_fields.get("dental_swelling"))
    night_sweats = night_sweats or bool(nlp_fields.get("night_sweats"))
    weight_loss = weight_loss or bool(nlp_fields.get("weight_loss"))
    neck_stiffness = neck_stiffness or bool(nlp_fields.get("neck_stiffness"))
    cough = cough or bool(nlp_fields.get("cough"))
    breathing_issue = breathing_issue or bool(nlp_fields.get("breathing_issue"))
    chest_pain = chest_pain or bool(nlp_fields.get("chest_pain"))
    preeclampsia_risk = bool(pregnant and (headache or severe_headache) and visual_disturbance) or bool(nlp_fields.get("preeclampsia_risk"))

    malaria_suspect = fever and endemic_area and (has_any(text, [r"frissons", r"courbature", r"fatique", r"fatigue"]) or bool(nlp_fields.get("chills")) or fatigue or headache)
    malaria_severe = malaria_suspect and (confusion or seizures or unable_to_drink or severe_abdominal_pain or respiratory_distress)
    watery_diarrhea = detect_positive(text, [r"diarrhee aqueuse", r"selles aqueuses", r"eau de riz", r"diarrhee liquide"])
    cholera_suspect = high_cholera_context and (watery_diarrhea or (diarrhea and dehydration))
    tb_suspect = cough and duration_days >= 14 and (weight_loss or night_sweats or appetite_loss or fatigue or hemoptysis)
    pneumonia_suspect = cough and fever and (duration_days >= 4 or breathing_issue or chest_pain)
    # [FIX-1] print debug supprimé
    return {
        "text": text,
        "province": province,
        "age": age,
        "sex": sex,
        "is_drc": is_drc,
        "africa_context": africa_context,
        "endemic_area": endemic_area,
        "high_cholera_context": high_cholera_context,
        "duration_days": duration_days,
        "duration_long": duration_days >= 7,
        "fever": fever,
        "vomiting": vomiting,
        "diarrhea": diarrhea,
        "digestive": digestive,
        "cough": cough,
        "sputum": sputum,
        "hemoptysis": hemoptysis,
        "night_sweats": night_sweats,
        "weight_loss": weight_loss,
        "appetite_loss": appetite_loss,
        "fatigue": fatigue,
        "breathing_issue": breathing_issue,
        "respiratory_distress": respiratory_distress,
        "unable_to_drink": unable_to_drink,
        "can_drink": can_drink,
        "urine_output_low": urine_output_low,
        "dehydration": dehydration,
        "chest_pain": chest_pain,
        "pleuritic_chest_pain": pleuritic_chest_pain,
        "chest_pressure": chest_pressure,
        "stroke_signs": stroke_signs,
        "neck_stiffness": neck_stiffness,
        "headache": headache,
        "meningitis": meningitis,
        "seizures": seizures,
        "confusion": confusion,
        "suicidal": suicidal,
        "anxiety": anxiety,
        "sleep_disorder": sleep_disorder,
        "persistent_sadness": persistent_sadness,
        "loss_of_interest": loss_of_interest,
        "urinary_burning": urinary_burning,
        "urinary_frequency": urinary_frequency,
        "hematuria": hematuria,
        "back_pain": back_pain,
        "flank_pain": flank_pain,
        "abdominal_pain": abdominal_pain,
        "lower_abdominal_pain": lower_abdominal_pain,
        "lower_right_abdominal_pain": lower_right_abdominal_pain,
        "severe_abdominal_pain": severe_abdominal_pain,
        "pain_intense": pain_intense,
        "pain": pain,
        "rash": rash,
        "itching": itching,
        "allergy_history": allergy_history,
        "dental_pain": dental_pain,
        "dental_swelling": dental_swelling,
        "difficulty_swallowing": difficulty_swallowing,
        "runny_nose": runny_nose,
        "sore_throat": sore_throat,
        "diabetes": diabetes,
        "hypertension": hypertension,
        "asthma": asthma,
        "depression_history": depression_history,
        "immunocompromised": immunocompromised,
        "child": child,
        "child_under_5": child_under_5,
        "child_5_or_less": age is not None and age <= 5,
        "pregnant": pregnant,
        "vaginal_bleeding": vaginal_bleeding,
        "visual_disturbance": visual_disturbance,
        "severe_headache": severe_headache,
        "preeclampsia_risk": preeclampsia_risk,
        "malaria_suspect": malaria_suspect,
        "malaria_severe": malaria_severe,
        "cholera_suspect": cholera_suspect,
        "tb_suspect": tb_suspect,
        "pneumonia_suspect": pneumonia_suspect,
        "nlp_fields": nlp_fields,
        "nlp_entities": nlp_entities,
        "span_fields": span_fields,
        "span_items": span_items,
        "span_error": None,
        "red_flags": red,
    }

# -----------------------------------------------------------------------------
# COHÉRENCE RESULTAT / FEATURES
# -----------------------------------------------------------------------------

def sync_result_fields(result: Any, s: Dict[str, Any]) -> None:
    fields = result.case_fields or {}
    profile = result.normalized_profile or {}
    text_signals = profile.get("text_signals") or {}
    norm_flags = profile.get("normalized_flags") or {}

    updates = {
        "fever": s["fever"], "fatigue": s["fatigue"], "headache": s["headache"],
        "breathing_issue": s["breathing_issue"], "digestive_symptom": s["digestive"],
        "rash": s["rash"], "anxiety": s["anxiety"], "persistent_sadness": s["persistent_sadness"],
        "sleep_disorder": s["sleep_disorder"], "loss_of_interest": s["loss_of_interest"],
        "loss_of_appetite": s["appetite_loss"], "urinary_burning": s["urinary_burning"],
        "dental_pain": s["dental_pain"], "pain": s["pain"], "asthma_history": s["asthma"],
        "depression_history": s["depression_history"], "hypertension_history": s["hypertension"],
        "diabetes_history": s["diabetes"], "pregnant": s["pregnant"], "vaginal_bleeding": s.get("vaginal_bleeding", False),
        "visual_disturbance": s.get("visual_disturbance", False), "preeclampsia_risk": s.get("preeclampsia_risk", False),
        "child_under_5": s["child_under_5"],
        "duration_long": s["duration_long"], "duration_days": s["duration_days"],
        "endemic_area": s["endemic_area"], "high_cholera_context": s["high_cholera_context"],
        "unable_to_drink": s["unable_to_drink"], "urine_output_low": s["urine_output_low"],
        "dehydration_signs": s["dehydration"], "confusion": s["confusion"],
        "mental_status_change": s["confusion"], "seizures": s["seizures"], "seizure_like": s["seizures"],
        "neck_stiffness": s["neck_stiffness"], "respiratory_distress": s["respiratory_distress"],
        "flank_pain": s["flank_pain"], "urinary_frequency": s["urinary_frequency"],
        "hematuria": s["hematuria"], "danger_to_self": s["suicidal"],
        "dental_swelling": s["dental_swelling"], "difficulty_swallowing": s["difficulty_swallowing"],
        "lower_abdominal_pain": s["lower_abdominal_pain"], "severe_abdominal_pain": s["severe_abdominal_pain"],
        "stroke_signs": s["stroke_signs"], "chest_pain": s["chest_pain"],
        "pleuritic_chest_pain": s["pleuritic_chest_pain"], "chest_pressure": s["chest_pressure"],
        "itching": s["itching"], "severe_dehydration": s["dehydration"],
    }
    fields.update(updates)
    norm_flags.update({k: v for k, v in updates.items() if k in norm_flags or k in {
        "fever", "fatigue", "headache", "breathing_issue", "digestive_symptom", "rash", "anxiety",
        "persistent_sadness", "sleep_disorder", "loss_of_interest", "loss_of_appetite",
        "urinary_burning", "dental_pain", "pain", "asthma_history", "depression_history",
        "hypertension_history", "diabetes_history", "pregnant", "child_under_5", "duration_long"
    }})
    text_signals.update({
        "unable_to_drink": s["unable_to_drink"], "urine_output_low": s["urine_output_low"],
        "dehydration_signs": s["dehydration"], "respiratory_distress": s["respiratory_distress"],
        "flank_pain": s["flank_pain"], "hematuria": s["hematuria"],
        "severe_abdominal_pain": s["severe_abdominal_pain"], "lower_abdominal_pain": s["lower_abdominal_pain"],
        "vaginal_bleeding": s.get("vaginal_bleeding", False),
        "night_sweats": s["night_sweats"], "suicidal_text": s["suicidal"],
        "dental_swelling": s["dental_swelling"], "stroke_signs": s["stroke_signs"],
        "chest_pain": s["chest_pain"], "pleuritic_chest_pain": s["pleuritic_chest_pain"],
        "itching": s["itching"],
    })
    profile["text_signals"] = text_signals
    profile["normalized_flags"] = norm_flags
    profile["complaint_norm"] = s["text"]
    profile["nlp_fields"] = s.get("nlp_fields", {})
    profile["nlp_entities"] = s.get("nlp_entities", [])
    profile["span_fields"] = s.get("span_fields", {})
    profile["span_error"] = s.get("span_error")
    result.case_fields = fields
    result.normalized_profile = profile


def cleanup_contradictions(result: Any, s: Dict[str, Any]) -> None:
    if not s["fever"]:
        result.reasons = remove_items_containing(result.reasons, ["Symptôme activé: Fièvre", "syndrome fébrile", "fievre"])
        result.activated_entries = [e for e in result.activated_entries if e not in {"SYM_FEVER", "SYN_FEVER_SIMPLE"}]
        if "fievre" in result.activated_domains:
            result.activated_domains = [d for d in result.activated_domains if d != "fievre"]
    if not s["digestive"]:
        result.reasons = remove_items_containing(result.reasons, ["Vomissements / diarrhée", "digestif"])
        result.activated_entries = [e for e in result.activated_entries if e not in {"SYM_DIGESTIVE", "SYN_DIGESTIVE_SIMPLE"}]
    if not s["dental_pain"]:
        result.reasons = remove_items_containing(result.reasons, ["dentaire", "dent"])
        result.activated_entries = [e for e in result.activated_entries if "DENT" not in e]
        result.activated_domains = [d for d in result.activated_domains if d != "dentaire"]

# -----------------------------------------------------------------------------
# QUESTIONS DYNAMIQUES INDICATIVES POUR LE PRODUIT
# -----------------------------------------------------------------------------

def enrich_dynamic_questions(result: Any, s: Dict[str, Any]) -> None:
    if result.priority_code == "P1":
        result.asked_questions = []
        return
    existing = {q.get("id") for q in (result.asked_questions or [])}
    def add(qid: str, label: str, domain: str, qtype: str = "boolean"):
        if qid not in existing:
            result.asked_questions.append({"id": qid, "label": label, "type": qtype, "domain": domain})
            existing.add(qid)
    if s["abdominal_pain"]:
        add("Q_ABD_LOCATION", "Où est localisée exactement la douleur du ventre ?", "digestif", "text")
        add("Q_ABD_INTENSITY", "Sur une échelle de 0 à 10, quelle est l'intensité de la douleur ?", "digestif", "number")
        add("Q_ABD_MOVEMENT", "La douleur augmente-t-elle quand vous marchez ou bougez ?", "digestif")
    if s["urinary_burning"] or s["flank_pain"]:
        add("Q_URINARY_FEVER", "Avez-vous de la fièvre ?", "urinaire")
        add("Q_URINARY_BLOOD", "Avez-vous du sang dans les urines ?", "urinaire")
        add("Q_URINARY_FLANK", "Avez-vous mal sur le côté du dos, vers les reins ?", "urinaire")
    if s["cough"]:
        add("Q_SPUTUM", "Toussez-vous avec des crachats ?", "respiratoire")
        add("Q_HEMOPTYSIS", "Y a-t-il du sang dans les crachats ?", "respiratoire")
        add("Q_NIGHT_SWEATS", "Avez-vous des sueurs nocturnes ?", "respiratoire")
    if s["breathing_issue"] and s["asthma"]:
        add("Q_ASTHMA_SPEAK", "Pouvez-vous parler normalement ?", "respiratoire")
        add("Q_ASTHMA_INHALER", "Avez-vous utilisé votre inhalateur et vous soulage-t-il ?", "respiratoire")
    if s["dental_pain"]:
        add("Q_DENT_SWALLOW", "Avez-vous du mal à avaler ?", "dentaire")
        add("Q_DENT_FEVER", "Avez-vous de la fièvre ?", "dentaire")
    if s["rash"]:
        add("Q_RASH_SPREAD", "Les boutons ou plaques s'étendent-ils rapidement ?", "dermatologique")
        add("Q_RASH_NIGHT_ITCH", "Les démangeaisons sont-elles plus fortes la nuit ?", "dermatologique")


# =============================================================================
# RÈGLES V3.9 — INTÉGRÉES NATIVEMENT
# 30 nouvelles règles de triage + 4 corrections de bugs V3.8
# =============================================================================



# ============================================================
# UTILITAIRES (repris du moteur V3.8 pour cohérence)
# ============================================================

def _p(priority: str) -> int:
    return {"P1": 4, "P2": 3, "P3": 2, "P4": 1}.get(priority, 0)


def _set(result, priority, message, reason, domain=None, entry=None, allow_downgrade=False):
    """Alias de set_result pour les règles V3.9."""
    return set_result(result, priority, message, reason, domain, entry, allow_downgrade=allow_downgrade)


def _has(text: str, patterns: List[str]) -> bool:
    return any(re.search(p, text) for p in patterns)

# ============================================================
# [FIX-1/2] EXTRACTION SIGNAUX V3.9 — CORRIGÉE
# ============================================================

def extract_v39_signals(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Réutilise extract_v38_signals() et y ajoute les nouveaux signaux V3.9.
    [FIX-1] : print() supprimé
    [FIX-2] : timer t0 local à chaque appel
    [FIX-3] : respiratory_distress isolé de stroke_signs
    """
    t0_local = time.time()  # [FIX-2] timer local

    # Récupérer tous les signaux V3.8 (même fichier)
    s = extract_v38_signals(payload)

    raw_text = str(payload.get("complaint_text", "") or "")
    text = norm(raw_text)
    nlp = s.get("nlp_fields", {})
    red = payload.get("immediate_red_flags", {}) or {}
    history = [norm(x) for x in payload.get("medical_history", [])]
    age = _age_from_dob(payload.get("date_of_birth"))
    province = norm(payload.get("province", ""))

    # [FIX-3] Isoler stroke_signs de respiratory_distress
    # "parle difficilement" = AVC, pas détresse respiratoire
    if s.get("stroke_signs") and not _has(text, [r"respire", r"air", r"etouff", r"essouff"]):
        s["respiratory_distress"] = False

    # ── Calcul âge en jours (pour néonatal) ──────────────────────────────
    dob_raw = str(payload.get("date_of_birth", "") or "")
    age_days: Optional[int] = None
    try:
        parts = dob_raw.strip().split("/")
        if len(parts) == 3:
            from datetime import date
            born = date(int(parts[2]), int(parts[1]), int(parts[0]))
            age_days = (date.today() - born).days
    except Exception:
        pass

    # [C8] Détecter néonatal aussi via texte libre (bébé X jours/semaines)
    neonatal_text = bool(re.search(
        r"bebe.*?([0-9]+)\s*jours?|nouveau.?ne|nourrisson.*?([0-9]+)\s*jours?"
        r"|([0-9]+)\s*jours?.*?bebe|accouche.*?([0-9]+)\s*jours?",
        text
    ))
    neonatal = (age_days is not None and age_days <= 28) or bool(nlp.get("neonatal_danger")) or neonatal_text

    # ── Signaux spécifiques V3.9 ─────────────────────────────────────────

    # [R01] Néonatal
    s["neonatal"] = neonatal
    s["neonatal_fever"] = (neonatal or bool(nlp.get("neonatal_danger"))) and (
        s.get("fever")
        or bool(nlp.get("fever"))
        or _has(text, [r"fievre", r"chaud", r"a de la fievre", r"38", r"39", r"40"])
    )
    s["neonatal_hypothermia"] = neonatal and _has(text, [r"froid.*bebe", r"bebe.*froid", r"bebe.*ne.*chauffe"])

    # [R02] Hémorragie digestive
    s["upper_gi_bleeding"] = (
        bool(nlp.get("upper_gi_bleeding"))
        or detect_positive(text, [r"vomit.*sang", r"hematemese", r"sang.*vomit", r"cafe.*moulu.*vomit"])
        or bool(red.get("vomiting_blood"))
    )
    s["lower_gi_bleeding"] = (
        bool(nlp.get("lower_gi_bleeding"))
        or detect_positive(text, [r"selles noires", r"\bmelena\b", r"sang.*selles", r"rectorragie", r"sang.*rectum"])
    )
    s["gi_bleeding"] = s["upper_gi_bleeding"] or s["lower_gi_bleeding"]

    # [R03] Morsure serpent / rage
    s["snake_bite"] = (
        bool(nlp.get("snake_bite"))
        or detect_positive(text, [r"morsure.*serpent", r"mordu.*serpent", r"piqure.*serpent",
                                   r"envenimation", r"mamba", r"vipere", r"cobra"])
        or bool(red.get("snake_bite"))
    )
    s["animal_bite_rabies_risk"] = (
        detect_positive(text, [r"mordu.*chien", r"chien.*mordu", r"mordu.*chat",
                                r"morsure.*animal", r"mordu.*chauve.*souris",
                                r"morsure.*singe", r"bete.*mordu"])
        and not _has(text, [r"vaccin.*rage", r"vaccine.*rage"])
    )

    # [R04] Ingestion toxique
    s["toxic_ingestion"] = (
        bool(nlp.get("toxic_ingestion"))
        or detect_positive(text, [r"avale.*medicament", r"avale.*produit", r"avale.*poison",
                                   r"empoisonnement", r"surdosage", r"intoxication",
                                   r"avale.*quelque chose", r"mange.*champignon.*sauvage",
                                   r"a bu.*produit.*nettoyant", r"avale.*liquide"])
        or bool(red.get("toxic_ingestion"))
    )

    # [R05] Traumatisme crânien
    s["head_trauma"] = (
        bool(nlp.get("head_trauma"))
        or detect_positive(text, [r"choc.*tete", r"coup.*tete", r"tete.*frappe",
                                   r"tombe.*tete", r"trauma.*cranien", r"blessure.*tete",
                                   r"accident.*tete"])
        or bool(red.get("head_trauma"))
    )
    s["head_trauma_with_loc"] = s["head_trauma"] and (
        s.get("confusion") or bool(nlp.get("loss_of_consciousness"))
        or detect_positive(text, [r"perdu.*connaissance", r"inconscient", r"ne repond plus"])
    )

    # [R06] Fièvre hémorragique virale (RDC — Ebola, Marburg)
    s["hemorrhagic_fever"] = (
        bool(nlp.get("hemorrhagic_fever_signs"))
        or (s.get("fever") and detect_positive(text, [
            r"saigne.*nez.*bouche", r"saigne.*partout", r"sang.*partout",
            r"saignement.*spontane", r"saigne.*gencive.*fievre",
            r"hemorragie.*fievre", r"saigne.*yeux",
        ]))
        or bool(red.get("hemorrhagic_fever"))
    )

    # [R07] Crise drépanocytaire
    sickle_history = any("drepanocytose" in x or "hemoglobine ss" in x for x in history)
    s["sickle_cell_crisis"] = (
        bool(nlp.get("sickle_cell_crisis"))
        or (sickle_history and (s.get("pain_intense") or s.get("fever") or s.get("breathing_issue")))
        or detect_positive(text, [r"mon sang.*mal", r"le sang.*fait.*mal",
                                   r"crise.*drepanocytaire", r"drepanocytose.*douleur"])
    )

    # [R08] Grossesse extra-utérine
    s["ectopic_risk"] = (
        bool(nlp.get("ectopic_risk"))
        or (
            s.get("pregnant")
            and s.get("lower_abdominal_pain")
            and detect_positive(text, [r"malaise", r"vertiges", r"perd.*connaissance",
                                        r"tres faible", r"evanouie", r"evanoui"])
        )
        or detect_positive(text, [r"pas.*regles.*douleur.*ventre",
                                   r"grossesse.*extra.?uterine"])
    )

    # [R09] Brûlure grave
    s["burn_severe"] = (
        bool(nlp.get("burn_severe"))
        or detect_positive(text, [r"brulure.*visage", r"brulure.*grave",
                                   r"brule.*\d{2}.*pourcent", r"brulure.*etendue",
                                   r"brulure.*respir", r"brule.*chimique",
                                   r"acide.*peau"])
        or bool(red.get("burn_severe"))
    )

    # [R10] Éclampsie
    s["eclampsia"] = (
        bool(nlp.get("eclampsia_risk"))
        or (s.get("pregnant") and s.get("seizures"))
    )

    # [R11] Acidocétose diabétique
    s["dka"] = (
        bool(nlp.get("diabetic_emergency")) or bool(nlp.get("dka_risk"))
        or (
            any("diabete" in x for x in history)
            and (s.get("vomiting") or s.get("confusion"))
            and detect_positive(text, [r"haleine.*acetonique", r"haleine.*sucree",
                                        r"haleine.*fruit", r"diabetique.*vomit",
                                        r"diabetique.*confusion"])
        )
    )

    # Hypoglycémie sévère
    s["severe_hypoglycemia"] = (
        bool(nlp.get("hypoglycemia_signs"))
        or (
            any("diabete" in x for x in history)
            and detect_positive(text, [r"inconscient", r"ne repond plus",
                                        r"diabetique.*malaise", r"hypoglycemie",
                                        r"glycemie.*tres.*basse", r"pas mange.*faible.*diabete"])
        )
    )

    # [R12] Tirage sous-costal / stridor pédiatrique
    s["child_chest_indrawing"] = (
        bool(nlp.get("child_danger_signs"))
        or detect_positive(text, [r"poitrine.*rentre.*respir", r"sa poitrine.*rentre",
                                   r"tirage.*sous.*costal", r"tirage.*poitrine"])
    )
    s["stridor"] = detect_positive(text, [r"\bstridor\b", r"sifflement.*inspiratoire",
                                           r"bruit.*aigu.*inspirat", r"siffle.*respir"])

    # [R13] Corps étranger voie aérienne
    s["airway_foreign_body"] = (
        detect_positive(text, [r"avale.*quelque chose.*tousse.*respir",
                                r"avale.*objet.*ne.*respir",
                                r"avale.*et.*respir.*mal",
                                r"mange.*et.*etouffe",
                                r"avale.*de.*travers.*respir"])
        or (detect_positive(text, [r"avale.*quelque chose", r"a avale.*objet"])
            and s.get("respiratory_distress"))
    )

    # [R14] Perte de connaissance
    s["loss_of_consciousness"] = (
        bool(nlp.get("loss_of_consciousness"))
        or detect_positive(text, [r"perdu.*connaissance", r"perd.*connaissance",
                                   r"evanoui", r"s est evanoui", r"inconscient",
                                   r"ne repond plus", r"ne reagit plus", r"\bsyncope\b"])
        or bool(red.get("loss_of_consciousness"))
    )

    # [R15] Ictère / Jaunisse
    s["jaundice"] = (
        bool(nlp.get("jaundice"))
        or detect_positive(text, [r"ictere", r"yeux jaunes", r"peau jaune",
                                   r"jaunisse", r"teint jaune"])
    )

    # [R16] Distension abdominale / occlusion
    s["bowel_obstruction"] = (
        bool(nlp.get("bowel_obstruction_signs"))
        or detect_positive(text, [r"arret.*matieres", r"arret.*gaz",
                                   r"ne.*plus.*selles.*depuis \d+",
                                   r"ventre.*dur.*arret", r"occlusion"])
    )

    # [R17] Fièvre post-partum
    s["postpartum"] = bool(nlp.get("postpartum")) or detect_positive(
        text, [r"vient.*accoucher", r"accouche.*hier", r"apres.*accouchement",
               r"post.?partum", r"suites.*couches", r"nouveau.?ne.*jours"]
    )
    s["postpartum_fever"] = s["postpartum"] and s.get("fever", False)

    # [R18] Rupture des membranes
    s["membrane_rupture"] = (
        bool(nlp.get("membrane_rupture"))
        or detect_positive(text, [r"perdu les eaux", r"poche.*rompue",
                                   r"eaux.*coulees", r"liquide.*vagin.*couler"])
    )

    # [R19] Absence mouvements fœtaux
    s["absent_fetal_movement"] = (
        bool(nlp.get("fetal_movement_absent"))
        or detect_positive(text, [r"bebe.*ne bouge plus", r"bebe.*bouge.*plus",
                                   r"plus.*sentir.*bebe", r"bebe.*inactif"])
    )

    # [R20] Anémie sévère
    s["severe_anemia"] = (
        bool(nlp.get("severe_anemia"))
        or detect_positive(text, [r"tres pale", r"pale.*comme.*linge",
                                   r"levres.*blanches", r"muqueuses.*blanches",
                                   r"yeux.*blancs", r"anemie.*severe"])
    )

    # [R21] Rétention urinaire
    s["urinary_retention"] = (
        bool(nlp.get("urinary_retention"))
        or detect_positive(text, [r"ne peut plus uriner", r"ne peux plus uriner",
                                   r"n arrive pas.*uriner", r"globe.*vesical",
                                   r"retenti.*urinaire"])
    )

    # [R22] Céphalée en coup de tonnerre
    s["thunderclap_headache"] = (
        bool(nlp.get("thunderclap_headache"))
        or detect_positive(text, [r"coup de tonnerre.*tete", r"pire.*mal.*tete.*vie",
                                   r"mal de tete.*jamais.*ressenti",
                                   r"soudain.*violent.*tete", r"d un coup.*mal.*tete"])
    )

    # [R23] Hémorragie digestive basse
    # (déjà dans s["lower_gi_bleeding"])

    # [R24] Psychose aiguë
    s["acute_psychosis"] = (
        bool(nlp.get("acute_psychosis"))
        or detect_positive(text, [r"entend.*voix", r"voit.*choses.*pas.*la",
                                   r"hallucination", r"delire.*persecution",
                                   r"croit.*persecute", r"comportement.*bizarre.*soudain"])
    )

    # [R25] Sevrage alcool
    s["alcohol_withdrawal_severe"] = (
        bool(nlp.get("alcohol_withdrawal"))
        or (detect_positive(text, [r"alcool.*arrete", r"arrete.*alcool", r"sevrage.*alcool"])
            and (s.get("seizures") or s.get("confusion") or
                 detect_positive(text, [r"tremble.*fort", r"agitation.*extreme"])))
    )

    # [R26] Palpitations + malaise
    s["palpitations"] = (
        bool(nlp.get("palpitations"))
        or detect_positive(text, [r"coeur.*bat.*fort", r"coeur.*s emballe",
                                   r"palpitation", r"coeur.*rapide.*malaise",
                                   r"tachycardie"])
    )

    # [R27] Signe IMCI enfant pâle + ne boit plus
    s["imci_danger_combined"] = (
        s.get("child_under_5")
        and (s.get("unable_to_drink") or s.get("child_chest_indrawing"))
        and (s.get("severe_anemia") or s.get("fever") or s.get("dehydration"))
    )

    # [R28] Paludisme grave renforcé
    s["malaria_severe_v39"] = (
        s.get("malaria_severe", False)
        or (s.get("malaria_suspect", False)
            and (s.get("seizures") or s.get("confusion")
                 or s.get("unable_to_drink") or s.get("severe_anemia")
                 or s.get("respiratory_distress") or s.get("loss_of_consciousness")))
    )

    # [R29] Malnutrition sévère avec complication
    s["severe_malnutrition_complicated"] = (
        bool(nlp.get("severe_malnutrition"))
        or detect_positive(text, [r"tres maigre.*fievre", r"malnutrition.*severe",
                                   r"oedeme.*pieds.*enfant.*maigre",
                                   r"bras.*tres.*mince.*enfant"])
    ) and (s.get("fever") or s.get("dehydration") or s.get("breathing_issue"))

    # [R30] Méningite nourrisson
    s["meningitis_infant"] = (
        neonatal or (age is not None and age <= 2)
    ) and (
        s.get("fever")
        or detect_positive(text, [r"fontanelle.*bombante", r"fontanelle.*gonfl",
                                   r"nuque.*raide.*bebe", r"bebe.*nuque.*raide"])
    )

    # Couche de validation des signaux avant règles finales.
    s = _apply_signal_safety_layer(payload, s)

    # Temps d'extraction V3.9
    s["v39_elapsed_seconds"] = round(time.time() - t0_local, 4)

    return s

# ============================================================
# [FIX-4] CLEANUP CONTRADICTIONS ÉTENDU
# ============================================================

def _clean_lower_priority_entries(result: Any) -> None:
    """[C4] Supprimer les entrées de priorité inférieure quand P1 est final."""
    if result.priority_code == "P1":
        # Garder uniquement les entrées P1
        result.activated_entries = [
            e for e in (result.activated_entries or [])
            if "P1" in e or not any(f"P{n}" in e for n in [2, 3, 4])
        ]

def cleanup_contradictions_v39(result: Any, s: Dict[str, Any]) -> None:
    """
    Étend cleanup_contradictions() à tous les domaines.
    V3.8 ne nettoyait que fever, digestive, dental.
    """
    # cleanup_contradictions et remove_items_containing disponibles dans ce fichier

    # Nettoyage V3.8 de base
    cleanup_contradictions(result, s)

    # Nettoyages supplémentaires V3.9
    if not s.get("breathing_issue") and not s.get("respiratory_distress"):
        result.reasons = remove_items_containing(result.reasons, ["respiratoire", "essoufflement"])
        result.activated_entries = [e for e in result.activated_entries if "RESP" not in e and "BREATH" not in e]
        result.activated_domains = [d for d in result.activated_domains if d != "respiratoire"]

    if not s.get("stroke_signs"):
        result.reasons = remove_items_containing(result.reasons, ["AVC", "avc", "stroke"])
        result.activated_entries = [e for e in result.activated_entries if "STROKE" not in e]

    if not s.get("suicidal"):
        result.reasons = remove_items_containing(result.reasons, ["suicidaire", "suicide"])
        result.activated_entries = [e for e in result.activated_entries if "SUICID" not in e]
        result.activated_domains = [d for d in result.activated_domains if d != "psychiatrique" or s.get("anxiety") or s.get("sleep_disorder")]

    if not s.get("chest_pain") and not s.get("chest_pressure"):
        result.reasons = remove_items_containing(result.reasons, ["thoracique", "poitrine", "cardiaque"])
        result.activated_domains = [d for d in result.activated_domains if d != "cardio"]

# ============================================================
# RÈGLES CLINIQUES V3.9 — COMPLÈTES
# ============================================================

def apply_v39_rules(result: Any, payload: Dict[str, Any]) -> Any:
    """
    Moteur de règles V3.9.
    Appelle apply_v38_corrections() en base, puis ajoute les règles nouvelles.

    ORDRE DE PRIORITÉ :
    1. Urgences vitales absolues (P1 sans discussion)
    2. Urgences P1 composites (combinaisons)
    3. Urgences P1 contextuelles (histoire + symptôme)
    4. P2 urgents
    5. Délégation à V3.8 pour le reste
    """
    # Fonctions disponibles dans ce fichier

    # Extraire les signaux V3.9
    s = extract_v39_signals(payload)

    # Synchroniser le résultat avec les signaux
    sync_result_fields(result, s)
    cleanup_contradictions_v39(result, s)

    MSG_URGENCE = "URGENCE MÉDICALE ⚠️"
    MSG_HOP = "Rendez-vous immédiatement à l'hôpital ou aux urgences les plus proches."
    MSG_NR = "Ne restez pas seul(e)."

    # ══════════════════════════════════════════════════════════════════
    # [R01] NÉONATAL — Règle OMS absolue
    # Toute fièvre ou hypothermie chez un nourrisson ≤ 28 jours = P1
    # ══════════════════════════════════════════════════════════════════
    if s.get("neonatal_fever") or s.get("neonatal_hypothermia"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Nourrisson de moins de 28 jours avec fièvre ou hypothermie : "
            f"urgence médicale absolue. {MSG_HOP}",
            "V3.9 [R01] OMS: tout nourrisson ≤28j avec fièvre/hypothermie = P1 absolu",
            "pediatrie", "V39_NEONATAL_FEVER_P1")

    if s.get("neonatal") and (s.get("unable_to_drink") or s.get("seizures") or s.get("loss_of_consciousness")):
        return _set(result, "P1",
            f"{MSG_URGENCE} Nourrisson de moins de 28 jours avec signe de danger : "
            f"urgence médicale absolue. {MSG_HOP}",
            "V3.9 [R01b] Nourrisson ≤28j avec signe de danger = P1",
            "pediatrie", "V39_NEONATAL_DANGER_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R06] FIÈVRE HÉMORRAGIQUE VIRALE (Ebola/Marburg — RDC)
    # Priorité maximale : isolement immédiat nécessaire
    # ══════════════════════════════════════════════════════════════════
    if s.get("hemorrhagic_fever"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Fièvre avec saignements multiples : suspicion de fièvre hémorragique "
            f"(Ebola, Marburg). Isolement immédiat. {MSG_HOP} Évitez tout contact avec les liquides "
            f"biologiques du patient.",
            "V3.9 [R06] Fièvre hémorragique virale suspectée — isolement P1",
            "infectieux", "V39_HEMORRHAGIC_FEVER_P1_ISOLATION")

    # ══════════════════════════════════════════════════════════════════
    # [R03] MORSURE DE SERPENT / RAGE
    # ══════════════════════════════════════════════════════════════════
    if s.get("snake_bite"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Morsure de serpent détectée. Immobilisez le membre atteint, "
            f"ne sucez pas la plaie, ne posez pas de garrot. {MSG_HOP} "
            f"Emmenez le patient immédiatement en gardant le membre immobile.",
            "V3.9 [R03] Morsure serpent — envenimation = P1",
            "urgence", "V39_SNAKE_BITE_P1")

    if s.get("animal_bite_rabies_risk"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Morsure d'animal à risque rabique (chien, chat, singe, chauve-souris) "
            f"sans vaccination antirabique connue. Lavez immédiatement la plaie à l'eau et au savon "
            f"pendant 15 minutes. {MSG_HOP} pour la prophylaxie post-exposition.",
            "V3.9 [R03b] Morsure animal risque rage = P1",
            "urgence", "V39_ANIMAL_BITE_RABIES_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R04] INGESTION TOXIQUE / EMPOISONNEMENT
    # ══════════════════════════════════════════════════════════════════
    if s.get("toxic_ingestion"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Ingestion de substance toxique, médicament ou poison suspectée. "
            f"Ne faites PAS vomir sauf avis médical. {MSG_HOP} immédiatement. "
            f"Apportez l'emballage du produit si possible.",
            "V3.9 [R04] Ingestion toxique = P1",
            "urgence", "V39_TOXIC_INGESTION_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R05] TRAUMATISME CRÂNIEN AVEC PERTE DE CONNAISSANCE
    # ══════════════════════════════════════════════════════════════════
    if s.get("head_trauma_with_loc"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Traumatisme crânien avec perte de connaissance : "
            f"risque d'hémorragie intracrânienne. Ne mobilisez pas le cou. {MSG_HOP}",
            "V3.9 [R05] Trauma crânien + perte de connaissance = P1",
            "neurologique", "V39_HEAD_TRAUMA_LOC_P1")

    if s.get("head_trauma") and not s.get("head_trauma_with_loc"):
        return _set(result, "P2",
            "Traumatisme crânien sans perte de connaissance. Surveillance rapprochée nécessaire. "
            "Consultez rapidement : si vomissements, somnolence, maux de tête qui s'aggravent "
            "ou comportement inhabituel → urgences immédiatement.",
            "V3.9 [R05b] Trauma crânien sans LOC = P2",
            "neurologique", "V39_HEAD_TRAUMA_P2")

    # ══════════════════════════════════════════════════════════════════
    # [R09] BRÛLURE GRAVE
    # ══════════════════════════════════════════════════════════════════
    if s.get("burn_severe"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Brûlure grave étendue ou touchant le visage / les voies respiratoires. "
            f"Refroidissez avec de l'eau froide (pas de glace, pas de beurre). {MSG_HOP}",
            "V3.9 [R09] Brûlure grave = P1",
            "urgence", "V39_BURN_SEVERE_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R10] ÉCLAMPSIE — Convulsions + Grossesse
    # ══════════════════════════════════════════════════════════════════
    if s.get("eclampsia"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Convulsions chez une femme enceinte : éclampsie possible. "
            f"Allongez-la sur le côté gauche. {MSG_HOP} / maternité immédiatement.",
            "V3.9 [R10] Éclampsie : convulsions + grossesse = P1",
            "gyn_obs", "V39_ECLAMPSIA_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R08] GROSSESSE EXTRA-UTÉRINE (GEU)
    # ══════════════════════════════════════════════════════════════════
    if s.get("ectopic_risk"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Grossesse avec douleur abdominale intense et malaise : "
            f"grossesse extra-utérine possible (urgence chirurgicale). {MSG_HOP}",
            "V3.9 [R08] GEU suspectée : grossesse + douleur + malaise = P1",
            "gyn_obs", "V39_ECTOPIC_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R18] RUPTURE DES MEMBRANES
    # ══════════════════════════════════════════════════════════════════
    if s.get("membrane_rupture"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Rupture des membranes (perte des eaux). {MSG_HOP} / maternité.",
            "V3.9 [R18] Rupture membranes = P1",
            "gyn_obs", "V39_MEMBRANE_RUPTURE_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R19] ABSENCE MOUVEMENTS FŒTAUX
    # ══════════════════════════════════════════════════════════════════
    if s.get("absent_fetal_movement") and s.get("pregnant"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Le bébé ne bouge plus. {MSG_HOP} / maternité immédiatement "
            f"pour un monitoring fœtal.",
            "V3.9 [R19] Absence MF = P1",
            "gyn_obs", "V39_ABSENT_FETAL_MOVEMENT_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R17] FIÈVRE POST-PARTUM
    # ══════════════════════════════════════════════════════════════════
    if s.get("postpartum_fever"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Fièvre après un accouchement récent : infection du post-partum possible. "
            f"Complication pouvant mettre la vie en danger. {MSG_HOP}",
            "V3.9 [R17] Fièvre post-partum = P1",
            "gyn_obs", "V39_POSTPARTUM_FEVER_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R02] HÉMORRAGIE DIGESTIVE HAUTE
    # ══════════════════════════════════════════════════════════════════
    if s.get("upper_gi_bleeding"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Vomissement de sang ou selles noires (méléna) détectés : "
            f"hémorragie digestive haute possible. {MSG_HOP}",
            "V3.9 [R02] Hémorragie digestive haute = P1",
            "digestif", "V39_UPPER_GI_BLEED_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R22] CÉPHALÉE EN COUP DE TONNERRE
    # Hémorragie sous-arachnoïdienne jusqu'à preuve du contraire
    # ══════════════════════════════════════════════════════════════════
    if s.get("thunderclap_headache"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Céphalée soudaine et violente d'apparition brutale "
            f"(« coup de tonnerre ») : hémorragie cérébrale possible. {MSG_HOP}",
            "V3.9 [R22] Céphalée en coup de tonnerre = P1 HSA",
            "neurologique", "V39_THUNDERCLAP_HEADACHE_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R14] PERTE DE CONNAISSANCE
    # ══════════════════════════════════════════════════════════════════
    if s.get("loss_of_consciousness"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Perte de connaissance ou état de non-réponse détecté. "
            f"Placez le patient en position latérale de sécurité (sur le côté). {MSG_HOP}",
            "V3.9 [R14] Perte de connaissance = P1",
            "neurologique", "V39_LOSS_OF_CONSCIOUSNESS_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R13] CORPS ÉTRANGER VOIE AÉRIENNE
    # ══════════════════════════════════════════════════════════════════
    if s.get("airway_foreign_body"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Corps étranger dans les voies aériennes suspecté. "
            f"Si l'enfant/patient peut tousser, encouragez à tousser. "
            f"Si obstruction totale : manœuvre de Heimlich. {MSG_HOP}",
            "V3.9 [R13] Corps étranger voie aérienne = P1",
            "respiratoire", "V39_AIRWAY_FB_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R12] TIRAGE SOUS-COSTAL / STRIDOR PÉDIATRIQUE (IMCI)
    # ══════════════════════════════════════════════════════════════════
    if s.get("stridor"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Bruit respiratoire anormal (stridor) : obstruction des voies "
            f"aériennes possible. {MSG_HOP}",
            "V3.9 [R12] Stridor = P1 IMCI",
            "respiratoire", "V39_STRIDOR_P1")

    if s.get("child_chest_indrawing") and s.get("child"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Tirage sous-costal chez un enfant : signe de détresse respiratoire "
            f"grave (IMCI). {MSG_HOP}",
            "V3.9 [R12b] Tirage sous-costal enfant = P1 IMCI",
            "pediatrie", "V39_CHEST_INDRAWING_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R11] ACIDOCÉTOSE DIABÉTIQUE / HYPOGLYCÉMIE SÉVÈRE
    # ══════════════════════════════════════════════════════════════════
    if s.get("dka"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Diabétique avec vomissements et/ou haleine sucrée/fruitée : "
            f"acidocétose diabétique possible. {MSG_HOP} sans délai.",
            "V3.9 [R11] Acidocétose diabétique = P1",
            "endocrinien", "V39_DKA_P1")

    if s.get("severe_hypoglycemia"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Diabétique inconscient ou ne répondant plus : hypoglycémie sévère "
            f"possible. Si le patient peut avaler : donner du sucre/jus sucré. {MSG_HOP}",
            "V3.9 [R11b] Hypoglycémie sévère = P1",
            "endocrinien", "V39_HYPOGLYCEMIA_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R25] SEVRAGE ALCOOL AVEC CONVULSIONS
    # ══════════════════════════════════════════════════════════════════
    if s.get("alcohol_withdrawal_severe"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Sevrage alcool avec convulsions ou agitation extrême : "
            f"delirium tremens possible. {MSG_HOP}",
            "V3.9 [R25] Sevrage alcool sévère = P1",
            "psychiatrique", "V39_ALCOHOL_WITHDRAWAL_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R24] PSYCHOSE AIGUË
    # ══════════════════════════════════════════════════════════════════
    if s.get("acute_psychosis"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Hallucinations, délire ou comportement très désorganisé détectés. "
            f"{MSG_NR} Contactez les urgences psychiatriques ou {MSG_HOP}",
            "V3.9 [R24] Psychose aiguë = P1",
            "psychiatrique", "V39_ACUTE_PSYCHOSIS_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R28] PALUDISME GRAVE RENFORCÉ
    # ══════════════════════════════════════════════════════════════════
    if s.get("malaria_severe_v39"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Paludisme avec signe de danger (convulsions, confusion, "
            f"incapacité de boire, anémie sévère ou détresse respiratoire). {MSG_HOP}",
            "V3.9 [R28] Paludisme grave = P1 renforcé",
            "infectieux", "V39_MALARIA_SEVERE_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R07] CRISE DRÉPANOCYTAIRE
    # ══════════════════════════════════════════════════════════════════
    if s.get("sickle_cell_crisis"):
        if s.get("fever") or s.get("breathing_issue") or s.get("stroke_signs"):
            return _set(result, "P1",
                f"{MSG_URGENCE} Crise drépanocytaire avec fièvre, difficultés respiratoires "
                f"ou signes neurologiques. {MSG_HOP}",
                "V3.9 [R07] Crise drépanocytaire compliquée = P1",
                "hematologie", "V39_SICKLE_CRISIS_SEVERE_P1")
        return _set(result, "P2",
            "Crise drépanocytaire probable (douleurs intenses chez patient drépanocytaire). "
            "Consultez rapidement un centre de santé avec vos documents médicaux.",
            "V3.9 [R07b] Crise drépanocytaire simple = P2",
            "hematologie", "V39_SICKLE_CRISIS_P2")

    # ══════════════════════════════════════════════════════════════════
    # [R27] IMCI COMBINÉ — Enfant pâle + ne boit plus
    # ══════════════════════════════════════════════════════════════════
    if s.get("imci_danger_combined"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Enfant avec plusieurs signes de danger IMCI (pâleur + ne boit plus "
            f"ou difficultés respiratoires). {MSG_HOP}",
            "V3.9 [R27] Combinaison IMCI enfant = P1",
            "pediatrie", "V39_IMCI_COMBINED_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R30] MÉNINGITE NOURRISSON
    # ══════════════════════════════════════════════════════════════════
    if s.get("meningitis_infant"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Nourrisson avec fièvre et fontanelle bombante ou nuque raide : "
            f"méningite possible. {MSG_HOP}",
            "V3.9 [R30] Méningite nourrisson = P1",
            "neurologique", "V39_MENINGITIS_INFANT_P1")

    # ══════════════════════════════════════════════════════════════════
    # [R29] MALNUTRITION SÉVÈRE COMPLIQUÉE
    # ══════════════════════════════════════════════════════════════════
    if s.get("severe_malnutrition_complicated"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Malnutrition sévère avec complication (fièvre, déshydratation "
            f"ou difficultés respiratoires). {MSG_HOP}",
            "V3.9 [R29] Malnutrition sévère compliquée = P1",
            "pediatrie", "V39_SEVERE_MALNUTRITION_P1")

    # ══════════════════════════════════════════════════════════════════
    # P2 — URGENCES RELATIVES NOUVELLES
    # ══════════════════════════════════════════════════════════════════

    # [R15] Ictère + fièvre → hépatite grave / paludisme
    if s.get("jaundice") and s.get("fever"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Jaunisse (yeux ou peau jaunes) avec fièvre : hépatite grave ou "
            f"paludisme compliqué possible. {MSG_HOP}",
            "V3.9 [R15] Ictère fébrile = P1",
            "infectieux", "V39_JAUNDICE_FEVER_P1")

    if s.get("jaundice") and not s.get("fever"):
        return _set(result, "P2",
            "Jaunisse (yeux ou peau jaunes) sans fièvre : hépatite ou autre cause biliaire à "
            "évaluer. Consultez rapidement un médecin.",
            "V3.9 [R15b] Ictère sans fièvre = P2",
            "infectieux", "V39_JAUNDICE_P2")

    # [R16] Distension abdominale + arrêt des matières
    if s.get("bowel_obstruction"):
        return _set(result, "P1",
            f"{MSG_URGENCE} Arrêt des matières et des gaz avec ventre gonflé : "
            f"occlusion intestinale possible. {MSG_HOP} (chirurgie potentielle).",
            "V3.9 [R16] Occlusion intestinale = P1",
            "digestif", "V39_BOWEL_OBSTRUCTION_P1")

    # [R20] Anémie sévère (pâleur extrême)
    if s.get("severe_anemia"):
        if s.get("breathing_issue") or s.get("confusion"):
            return _set(result, "P1",
                f"{MSG_URGENCE} Pâleur extrême avec difficultés respiratoires ou confusion : "
                f"anémie sévère décompensée. {MSG_HOP} en urgence.",
                "V3.9 [R20] Anémie sévère décompensée = P1",
                "hematologie", "V39_SEVERE_ANEMIA_DECOMP_P1")
        return _set(result, "P2",
            "Pâleur importante (lèvres blanches, muqueuses décolorées) : anémie sévère possible. "
            "Consultez rapidement pour une prise de sang et prise en charge adaptée.",
            "V3.9 [R20b] Anémie sévère = P2",
            "hematologie", "V39_SEVERE_ANEMIA_P2")

    # [R21] Rétention urinaire
    if s.get("urinary_retention"):
        return _set(result, "P2",
            "Incapacité à uriner avec envie douloureuse : rétention urinaire aiguë possible. "
            "Consultez rapidement un centre de santé ou urgences (sondage vésical nécessaire).",
            "V3.9 [R21] Rétention urinaire = P2",
            "urinaire", "V39_URINARY_RETENTION_P2")

    # [R23] Hémorragie digestive basse
    if s.get("lower_gi_bleeding"):
        return _set(result, "P2",
            "Sang rouge dans les selles : rectorragie nécessitant une évaluation médicale rapide. "
            "Consultez rapidement, surtout si abondant, douleurs intenses ou malaise.",
            "V3.9 [R23] Rectorragie = P2",
            "digestif", "V39_LOWER_GI_BLEED_P2")

    # [R26] Palpitations + malaise
    if s.get("palpitations") and (s.get("chest_pain") or s.get("fatigue") or s.get("loss_of_consciousness")):
        return _set(result, "P2",
            "Palpitations avec douleur thoracique ou malaise : arythmie cardiaque possible. "
            "Consultez rapidement.",
            "V3.9 [R26] Palpitations complexes = P2",
            "cardio", "V39_PALPITATIONS_P2")

    # Déléguer au moteur V3.8 pour tous les autres cas
    return apply_v38_corrections(result, payload)


# ============================================================
# FONCTION PRINCIPALE V3.9
# ============================================================



# ============================================================
# VALIDATION LAYER V3.9 SAFE — anti faux positifs NLP/règles
# ============================================================

def _patient_denies_pregnancy(text: str) -> bool:
    return has_any(text, [
        r"je ne suis pas enceinte", r"je suis pas enceinte", r"je ne suis oas enceinte",
        r"ne suis pas enceinte", r"pas enceinte", r"moi.*pas enceinte"
    ])


def _third_party_pregnancy_only(text: str) -> bool:
    return has_any(text, [r"ma voisine.*enceinte", r"mon voisin.*enceinte", r"ma soeur.*enceinte", r"ma fille.*enceinte"]) and not has_any(text, [r"je suis enceinte", r"moi.*enceinte", r"enceinte de \d+ mois"])


def _explicit_fever_positive(text: str) -> bool:
    if has_any(text, [r"pas de fievre", r"sans fievre", r"aucune fievre", r"ni fievre"]):
        return False
    return has_any(text, [r"\bfievre\b", r"un peu de fievre", r"temperature", r"frissons", r"il a de la fievre", r"elle a de la fievre"])


def _explicit_bleeding_positive(text: str) -> bool:
    if has_any(text, [r"pas de saignement", r"pas de saignemen", r"sans saignement", r"aucun saignement", r"ni saignement"]):
        return False
    return has_any(text, [
        r"saigne du nez", r"nez.*saigne", r"saigne des gencives", r"saigne.*genciv", r"genciv.*saign",
        r"saignement nasal", r"saignement gingival", r"vomit.*sang", r"crache.*sang",
        r"selles noires", r"saigne.*partout", r"saignement.*spontane"
    ])


def _explicit_vaginal_bleeding(text: str) -> bool:
    return has_any(text, [r"saignement vaginal", r"sang.*vagin", r"pertes.*sang", r"pertes rouges", r"pertes sanglantes"])


def _force_priority(result: Any, priority: str, message: str, reason: str, domain: Optional[str] = None, entry: Optional[str] = None) -> Any:
    """Force une priorité, y compris downgrade, uniquement dans la validation anti-faux positifs."""
    result.priority_code = priority
    result.color = base.PRIORITY_META[priority]["color"]
    result.urgency_label = base.PRIORITY_META[priority]["urgency_label"]
    result.orientation = base.PRIORITY_META[priority]["orientation_default"]
    result.message = message
    if reason not in (result.reasons or []):
        result.reasons.append(reason)
    if domain:
        add_unique(result.activated_domains, domain)
    if entry:
        add_unique(result.activated_entries, entry)
    return result


def _apply_signal_safety_layer(payload: Dict[str, Any], s: Dict[str, Any]) -> Dict[str, Any]:
    """Corrige les signaux avant application des règles V3.9."""
    raw_text = str(payload.get("complaint_text", "") or "")
    text = norm(raw_text)
    sex = norm(payload.get("sex", ""))
    associated = [norm(x) for x in payload.get("associated_signs", [])]
    history = [norm(x) for x in payload.get("medical_history", [])]
    nlp = s.get("nlp_fields", {}) or {}

    # Fièvre : la présence dans les choix associés compte, sauf négation explicite dans le texte.
    fever_positive = _explicit_fever_positive(text) or (any("fievre" in x for x in associated) and not has_any(text, [r"pas de fievre", r"sans fievre"]))
    if fever_positive:
        s["fever"] = True
        nlp["fever"] = True
        nlp["fever_negated"] = False

    # Grossesse : négation du patient et contexte tiers ont priorité.
    if _patient_denies_pregnancy(text) or _third_party_pregnancy_only(text):
        s["pregnant"] = False
        nlp["pregnant"] = False
        nlp["pregnant_negated"] = True
        s["preeclampsia_risk"] = False
        nlp["preeclampsia_risk"] = False
        nlp["eclampsia_risk"] = False

    # Lombalgie et négation locale.
    if has_any(text, [r"mal au dos", r"douleur.*dos", r"bas du dos", r"lombalg"]):
        s["back_pain"] = True
        s["pain"] = True
        nlp["back_pain"] = True
        nlp["back_pain_negated"] = False

    # Pleurs aigu ≠ tristesse persistante.
    if has_any(text, [r"\bpleure\b", r"il pleure", r"elle pleure"]) and not has_any(text, [r"tristesse", r"triste depuis", r"deprime", r"depression", r"plus envie"]):
        s["persistent_sadness"] = False
        nlp["persistent_sadness"] = False
        nlp["emotional_distress"] = True

    # Saignements muqueux / hémorragie.
    epistaxis = has_any(text, [r"saigne du nez", r"nez.*saigne", r"saignement nasal"])
    gingival = has_any(text, [r"saigne des gencives", r"saigne.*genciv", r"genciv.*saign", r"saignement.*genciv"])
    bleeding_positive = _explicit_bleeding_positive(text)
    bleeding_negated = has_any(text, [r"pas de saignement", r"pas de saignemen", r"sans saignement", r"aucun saignement"])
    if epistaxis:
        nlp["epistaxis"] = True
    if gingival:
        nlp["gingival_bleeding"] = True
        s["dental_pain"] = False
        nlp["dental_pain"] = False
    if epistaxis or gingival:
        nlp["mucosal_bleeding"] = True
        nlp["bleeding"] = True

    # Saignement vaginal uniquement explicite + sexe féminin.
    if sex == "homme" or not _explicit_vaginal_bleeding(text):
        s["vaginal_bleeding"] = False
        nlp["vaginal_bleeding"] = False
    elif sex == "femme":
        s["vaginal_bleeding"] = True
        nlp["vaginal_bleeding"] = True

    # Fièvre hémorragique : exiger fièvre ET saignement réel non nié.
    if bleeding_negated:
        s["hemorrhagic_fever"] = False
        nlp["hemorrhagic_fever_signs"] = False
        nlp["hemorrhagic_fever_signs_negated"] = True
    else:
        valid_hemorrhagic = bool(s.get("fever")) and (bleeding_positive or bool(nlp.get("mucosal_bleeding")))
        if not valid_hemorrhagic:
            s["hemorrhagic_fever"] = False
            nlp["hemorrhagic_fever_signs"] = False
        elif valid_hemorrhagic and (has_any(text, [r"voisin.*meme", r"voisine.*meme", r"memes symptomes", r"contact", r"epidemie"]) or epistaxis or gingival):
            s["hemorrhagic_fever"] = True
            nlp["hemorrhagic_fever_signs"] = True

    # Expression locale : douleur diffuse, pas hémorragie ni drépanocytose sans contexte.
    if has_any(text, [r"mon sang.*mal", r"sang fait.*mal", r"le sang.*mal"]):
        s["diffuse_pain"] = True
        s["pain"] = True
        s["hemorrhagic_fever"] = False
        nlp["hemorrhagic_fever_signs"] = False
        if not (any("drepanocyt" in x or "hemoglobine ss" in x for x in history) or has_any(text, [r"drepanocytose", r"drepanocytaire", r"hemoglobine ss"])):
            s["sickle_cell_crisis"] = False
            nlp["sickle_cell_crisis"] = False
            nlp["sickle_crisis_severe"] = False

    # Ingestion toxique : enrichir signes, cohérence poisoning.
    if s.get("toxic_ingestion") or has_any(text, [r"avale.*produit", r"produit de nettoyage", r"a bu.*produit", r"avale.*poison"]):
        s["toxic_ingestion"] = True
        nlp["toxic_ingestion"] = True
        nlp["poisoning"] = True
    if has_any(text, [r"bave", r"salive beaucoup", r"hypersalivation"]):
        s["hypersalivation"] = True
        nlp["hypersalivation"] = True
    if s.get("toxic_ingestion") and has_any(text, [r"produit de nettoyage", r"javel", r"acide", r"soude", r"detergent"]):
        s["corrosive_risk"] = True
        nlp["corrosive_risk"] = True

    # Éclampsie : grossesse + crise/tremblements/amnésie.
    seizure_text = has_any(text, [r"convulsion", r"crise", r"tremblait", r"tout mon corps trembl", r"secousse", r"ne me souviens plus", r"ne me souvies plus"])
    if s.get("pregnant") and seizure_text:
        s["seizures"] = True
        s["eclampsia"] = True
        nlp["eclampsia_risk"] = True
        nlp["postictal_state"] = has_any(text, [r"ne me souviens plus", r"ne me souvies plus"])

    # GEU : aménorrhée + douleur bas ventre latéralisée + malaise.
    amenorrhea = has_any(text, [r"pas eu mes regles", r"pas de regles", r"retard.*regles", r"regles depuis \d+ mois"])
    lower_pain = s.get("lower_abdominal_pain") or has_any(text, [r"bas du ventre", r"ventre.*gauche", r"ventre.*droite", r"pelvien"])
    presyncope = has_any(text, [r"failli tomber", r"presque tombe", r"vertige", r"malaise", r"tres faible"])
    if amenorrhea:
        nlp["amenorrhea"] = True
        nlp["possible_pregnancy"] = True
    if amenorrhea and lower_pain and presyncope and sex == "femme":
        s["ectopic_risk"] = True
        nlp["ectopic_risk"] = True

    # DKA enrichi.
    if has_any(text, [r"haleine.*fruit", r"haleine.*sucree", r"haleine.*acetonique"]):
        nlp["acetone_breath"] = True
    if s.get("dka") or bool(nlp.get("dka_risk")):
        nlp["metabolic_emergency"] = True

    s["nlp_fields"] = nlp
    return s


def _remove_v39_entry_noise(result: Any, entry_tokens: List[str], reason_tokens: List[str], domain_tokens: Optional[List[str]] = None) -> None:
    result.activated_entries = [e for e in (result.activated_entries or []) if not any(tok in e for tok in entry_tokens)]
    result.reasons = remove_items_containing(result.reasons or [], reason_tokens)
    if domain_tokens:
        result.activated_domains = [d for d in (result.activated_domains or []) if not any(tok in d for tok in domain_tokens)]


def _apply_result_safety_layer(result: Any, payload: Dict[str, Any]) -> Any:
    """Validation finale, y compris downgrade de faux P1 dangereux."""
    s = extract_v39_signals(payload)
    sync_result_fields(result, s)

    # Faux P1 fièvre hémorragique : on downgrade si les conditions minimales ne sont pas réunies.
    has_hemo_entry = any("HEMORRHAGIC" in e or "HEMORRH" in e for e in (result.activated_entries or []))
    if has_hemo_entry and not s.get("hemorrhagic_fever"):
        _remove_v39_entry_noise(result, ["HEMORRHAGIC", "HEMORRH", "AFR_HEMORRHAGIC"], ["hémorragique", "hemorragique", "Ebola", "Marburg", "saignement ou jaunisse"], ["infectieux"])
        if s.get("abdominal_pain") and s.get("fever"):
            return _force_priority(result, "P3",
                "Douleur abdominale avec fièvre légère sans signe de gravité immédiate. Consultez rapidement si la fièvre persiste, si la douleur augmente, ou si un saignement/vomissement apparaît.",
                "Validation V3.9 safe: fièvre hémorragique non retenue faute de saignement réel", "digestif", "V39_SAFE_ABD_FEVER_P3")
        if s.get("diffuse_pain") or s.get("pain"):
            return _force_priority(result, "P3",
                "Douleurs diffuses sans signe de gravité immédiate détecté. Une consultation standard/rapide est recommandée si la douleur persiste, s’aggrave ou s’accompagne de fièvre élevée.",
                "Validation V3.9 safe: douleur diffuse sans critère P1", "transversal", "V39_SAFE_DIFFUSE_PAIN_P3")
        return _force_priority(result, "P3",
            "Symptômes sans critère d'urgence vitale confirmé après validation. Une consultation médicale est recommandée si les signes persistent ou s'aggravent.",
            "Validation V3.9 safe: faux P1 bloqué", "transversal", "V39_SAFE_FALSE_P1_BLOCKED")

    # Grossesse faussement attribuée : nettoyer les règles gynéco si le patient nie la grossesse.
    text = s.get("text", "")
    if _patient_denies_pregnancy(text) or _third_party_pregnancy_only(text):
        _remove_v39_entry_noise(result, ["PREGN", "PREGNANCY", "GYN_PREGNANCY", "ECLAMPSIA", "PREECLAMPSIA"], ["Grossesse", "grossesse", "enceinte"], ["gyn_obs"])
        sync_result_fields(result, s)

    # Si GEU détectée, priorité P1 explicite.
    if s.get("ectopic_risk"):
        return _force_priority(result, "P1",
            "URGENCE MÉDICALE ⚠️ Absence de règles avec douleur bas ventre localisée et malaise : grossesse extra-utérine possible. Rendez-vous immédiatement à l’hôpital ou aux urgences.",
            "Validation V3.9 safe: suspicion GEU = P1", "gyn_obs", "V39_ECTOPIC_SAFE_P1")

    # Si éclampsie détectée, priorité P1 explicite.
    if s.get("eclampsia"):
        return _force_priority(result, "P1",
            "URGENCE MÉDICALE ⚠️ Convulsions/crise chez une femme enceinte : éclampsie possible. Allongez-la sur le côté gauche et rendez-vous immédiatement à l’hôpital ou à la maternité.",
            "Validation V3.9 safe: grossesse + crise/convulsions = éclampsie P1", "gyn_obs", "V39_ECLAMPSIA_SAFE_P1")

    return result

def apply_v39_corrections(result: Any, payload: Dict[str, Any]) -> Any:
    """
    Point d'entrée principal V3.9 sécurisé.
    1) applique les règles V3.9
    2) nettoie les entrées de priorité inférieure
    3) applique une validation médicale finale anti faux positifs / incohérences
    """
    result = apply_v39_rules(result, payload)
    _clean_lower_priority_entries(result)  # [C4]
    result = _apply_result_safety_layer(result, payload)
    _clean_lower_priority_entries(result)
    return result


# ============================================================
# INTÉGRATION : MONKEY-PATCH run_triage pour utiliser V3.9
# ============================================================

# =============================================================================
# FIN RÈGLES V3.9
# =============================================================================

# -----------------------------------------------------------------------------
# CORRECTIONS CLINIQUES V3.8 CONSOLIDÉES
# -----------------------------------------------------------------------------

def apply_v38_corrections(result: Any, payload: Dict[str, Any]) -> Any:
    s = extract_v38_signals(payload)
    sync_result_fields(result, s)
    cleanup_contradictions(result, s)

    # ---- P1 directs et cohérence des messages/reasons ----
    if s.get("preeclampsia_risk"):
        result.reasons = ["Red flag direct: grossesse + céphalées fortes + vision floue => suspicion pré-éclampsie"]
        result.activated_domains = ["gyn_obs", "neurologique", "urgence"]
        result.activated_entries = ["V38_PREECLAMPSIA_P1"]
        return set_result(result, "P1",
            "URGENCE MÉDICALE ⚠️ Maux de tête avec troubles de la vision chez une femme enceinte : pré-éclampsie possible. Rendez-vous immédiatement à l’hôpital. Ne restez pas à domicile.",
            "V3.8 consolidé + NLP hybride: suspicion de pré-éclampsie => P1", "gyn_obs", "V38_PREECLAMPSIA_P1")

    if s.get("pregnant") and (s.get("vaginal_bleeding") or (s.get("red_flags") or {}).get("uncontrollable_bleeding")):
        result.reasons = ["Red flag direct: saignement pendant grossesse"]
        result.activated_domains = ["gyn_obs", "urgence"]
        result.activated_entries = ["V38_PREGNANCY_BLEEDING_P1"]
        return set_result(result, "P1",
            "URGENCE MÉDICALE ⚠️ Saignement pendant une grossesse. Rendez-vous immédiatement à l’hôpital ou à la maternité la plus proche.",
            "V3.8 consolidé + NLP hybride: saignement pendant grossesse => P1", "gyn_obs", "V38_PREGNANCY_BLEEDING_P1")

    if s["stroke_signs"]:
        result.reasons = ["Red flag direct: Signes neurologiques évocateurs d'AVC"]
        result.activated_domains = ["neurologique"]
        result.activated_entries = ["RF_STROKE_SUSPECT"]
        return set_result(result, "P1",
            "URGENCE MÉDICALE ⚠️ Signes pouvant correspondre à un AVC (faiblesse d’un côté, difficulté à parler). Rendez-vous immédiatement à l’hôpital. Chaque minute compte.",
            "V3.8 consolidé: AVC suspect => P1", "neurologique", "V38_STROKE_P1")

    if s["suicidal"]:
        result.reasons = ["Red flag direct: Danger psychique immédiat"]
        result.activated_domains = ["psychiatrique"]
        result.activated_entries = ["RF_SUICIDAL_CRISIS"]
        return set_result(result, "P1",
            "URGENCE ⚠️ Vous semblez traverser une situation très difficile avec des pensées de vous faire du mal. Ne restez pas seul(e), contactez immédiatement un proche ou un service d’urgence.",
            "V3.8 consolidé: risque suicidaire explicite => P1", "psychiatrique", "V38_SUICIDE_P1")

    if s["meningitis"]:
        result.reasons = ["Red flag direct: Fièvre + raideur nuque/cou => suspicion méningite"]
        result.activated_domains = ["fievre", "infectieux", "neurologique"]
        result.activated_entries = ["V38_MENINGITIS_P1"]
        return set_result(result, "P1",
            "URGENCE MÉDICALE ⚠️ Fièvre avec raideur de la nuque ou violents maux de tête : suspicion de méningite. Rendez-vous immédiatement à l’hôpital.",
            "V3.8 consolidé: méningite suspecte => P1", "infectieux", "V38_MENINGITIS_P1")

    if s["seizures"] or s["confusion"]:
        result.reasons = ["Red flag direct: Altération neurologique ou convulsions"]
        result.activated_domains = ["neurologique"]
        return set_result(result, "P1",
            "URGENCE MÉDICALE ⚠️ Convulsions, confusion ou trouble neurologique détecté. Rendez-vous immédiatement à l’hôpital.",
            "V3.8 consolidé: urgence neurologique => P1", "neurologique", "V38_NEURO_P1")

    if s["child_under_5"] and s["digestive"] and (s["unable_to_drink"] or s["dehydration"]):
        result.reasons = ["Red flag direct: enfant <5 ans ne boit plus / vomit tout"]
        result.activated_domains = ["pediatrie", "digestif"]
        return set_result(result, "P1",
            "URGENCE MÉDICALE ⚠️ Votre enfant ne boit plus ou vomit tout. Risque de déshydratation sévère. Rendez-vous immédiatement à l’hôpital ou au centre de santé le plus proche.",
            "V3.8 consolidé IMCI: enfant avec signe général de danger => P1", "pediatrie", "V38_IMCI_CHILD_DANGER_P1")

    if s["child_5_or_less"] and s["fever"] and s["can_drink"] and not s["dehydration"] and not s["breathing_issue"] and not s["seizures"]:
        return set_result(result, "P4",
            "Fièvre chez l'enfant sans signe de gravité immédiate. Surveillez l'évolution, assurez une bonne hydratation et consultez si la fièvre persiste ou s'aggrave.",
            "V3.8 consolidé IMCI: enfant fébrile qui boit bien, sans danger => P4", "pediatrie", "V38_IMCI_CHILD_FEVER_SAFE_P4", allow_downgrade=True)

    if s["digestive"] and (s["unable_to_drink"] or s["urine_output_low"] or s["dehydration"] and s["pain_intense"]):
        return set_result(result, "P1",
            "URGENCE MÉDICALE ⚠️ Vomissements/diarrhée avec incapacité de boire ou signes de déshydratation. Rendez-vous immédiatement à l’hôpital.",
            "V3.8 consolidé: déshydratation sévère probable => P1", "digestif", "V38_DEHYDRATION_P1")

    if s["respiratory_distress"]:
        return set_result(result, "P1",
            "URGENCE MÉDICALE ⚠️ Détresse respiratoire détectée. Rendez-vous immédiatement à l’hôpital.",
            "V3.8 consolidé: détresse respiratoire => P1", "respiratoire", "V38_RESP_DISTRESS_P1")

    if s["chest_pressure"] or (s["chest_pain"] and (s["breathing_issue"] or s["hypertension"] or s["pleuritic_chest_pain"])):
        return set_result(result, "P1" if s["chest_pressure"] and s["breathing_issue"] else "P2",
            "Douleur ou gêne dans la poitrine détectée. Cela peut correspondre à un problème cardiaque ou pulmonaire. Consultez en urgence, surtout en cas d’essoufflement.",
            "V3.8 consolidé: douleur thoracique non banalisable", "cardio", "V38_CHEST_PAIN_ALERT")

    # ---- Obstétrique critique hors saignement/pré-éclampsie ----
    if s["pregnant"] and s["abdominal_pain"] and (s["severe_abdominal_pain"] or s["pain_intense"]):
        return set_result(result, "P2",
            "Douleur abdominale intense pendant la grossesse. Une évaluation médicale rapide en maternité ou à l’hôpital est recommandée, surtout en cas de saignement, contractions, fièvre ou aggravation.",
            "V3.8 consolidé + NLP hybride: grossesse + douleur abdominale intense => P2 renforcé", "gyn_obs", "V38_PREGNANCY_SEVERE_ABD_P2")

    # ---- Abdominal / appendicite / urgences chirurgicales ----
    if s["lower_right_abdominal_pain"] and (s["pain_intense"] or s["duration_days"] <= 2):
        return set_result(result, "P2",
            "Douleur abdominale forte en bas à droite : une appendicite est possible. Consultez rapidement dans un centre de santé ou un hôpital.",
            "V3.8 consolidé: douleur bas droit abdomen => appendicite possible => P2", "digestif", "V38_APPENDICITIS_SUSPECT_P2")

    if s["severe_abdominal_pain"]:
        return set_result(result, "P2",
            "Douleur abdominale intense détectée. Une évaluation médicale rapide est recommandée pour exclure une urgence abdominale.",
            "V3.8 consolidé: douleur abdominale intense => P2", "digestif", "V38_SEVERE_ABD_P2")

    # ---- Afrique + infectieux ----
    if s["malaria_severe"]:
        return set_result(result, "P1",
            "Paludisme grave possible avec signe de danger. Rendez-vous immédiatement à l’hôpital.",
            "V3.8 consolidé Afrique: paludisme grave possible => P1", "infectieux", "V38_MALARIA_SEVERE_P1")

    if s["malaria_suspect"]:
        return set_result(result, "P2",
            "Fièvre avec signes compatibles avec le paludisme. Faites rapidement un test (TDR ou goutte épaisse) et consultez pour une prise en charge adaptée.",
            "V3.8 consolidé Afrique: paludisme probable => P2", "infectieux", "V38_MALARIA_SUSPECT_P2")

    if s["cholera_suspect"]:
        return set_result(result, "P2",
            "Diarrhée/vomissements avec contexte de choléra ou déshydratation possible. Consultez rapidement et hydratez-vous avec une solution de réhydratation orale si possible.",
            "V3.8 consolidé Afrique: choléra/déshydratation possible => P2", "digestif", "V38_CHOLERA_SUSPECT_P2")

    if s["tb_suspect"]:
        return set_result(result, "P2",
            "Toux prolongée avec fatigue, perte de poids ou signes généraux : tuberculose possible. Consultez rapidement pour un test TB et limitez les contacts rapprochés en attendant l’avis médical.",
            "V3.8 consolidé Afrique/global: tuberculose possible => P2", "respiratoire", "V38_TB_SUSPECT_P2")

    if s["pneumonia_suspect"]:
        return set_result(result, "P2",
            "Toux avec fièvre depuis plusieurs jours : infection respiratoire ou pneumonie possible. Consultez rapidement. En zone palustre, un test paludisme peut aussi être nécessaire.",
            "V3.8 consolidé: respiratoire dominant, paludisme à éliminer", "respiratoire", "V38_RESP_FEVER_DOMINANT_P2")

    # ---- Urinaire / rénal ----
    if s["urinary_burning"] and (s["fever"] or s["flank_pain"] or s["hematuria"]):
        return set_result(result, "P2",
            "Brûlure urinaire avec fièvre, douleur du flanc ou sang dans les urines : infection urinaire compliquée possible. Consultez rapidement.",
            "V3.8 consolidé: syndrome urinaire compliqué => P2", "urinaire", "V38_URI_COMPLICATED_P2")

    if s["urinary_burning"]:
        return set_result(result, "P3",
            "Les brûlures urinaires évoquent une infection urinaire probable. Consultez rapidement pour confirmer la cause et éviter une complication.",
            "V3.8 consolidé: syndrome urinaire bas probable => P3", "urinaire", "V38_URI_SIMPLE_P3")

    if s["flank_pain"]:
        return set_result(result, "P3" if not s["fever"] else "P2",
            "Douleur sur le côté du dos/reins détectée. Consultez rapidement, surtout si fièvre, sang dans les urines ou douleur intense.",
            "V3.8 consolidé: douleur rénale/flanc à explorer", "urinaire", "V38_RENAL_FLANK_PAIN")

    # ---- Asthme / respiratoire ----
    if s["asthma"] and s["breathing_issue"]:
        return set_result(result, "P2",
            "Essoufflement sur terrain asthmatique : cela peut correspondre à une crise d’asthme. Utilisez votre traitement habituel si disponible et consultez rapidement. Urgence si difficulté à parler ou respiration très difficile.",
            "V3.8 consolidé: essoufflement sur asthme => P2", "respiratoire", "V38_ASTHMA_P2")

    if s["breathing_issue"]:
        return set_result(result, "P2",
            "Essoufflement détecté. Une évaluation médicale rapide est recommandée, surtout si cela s’aggrave ou s’accompagne de douleur thoracique/fièvre.",
            "V3.8 consolidé: essoufflement non banalisable => P2", "respiratoire", "V38_BREATHING_P2")

    # ---- Dentaire / dermatologie / ORL / psy / digestif simple ----
    if s["dental_pain"] and (s["dental_swelling"] or s["difficulty_swallowing"] or s["fever"]):
        return set_result(result, "P2",
            "Douleur dentaire avec gonflement ou signe d’infection : abcès possible. Consultez rapidement un dentiste ou un centre de santé. Urgence si difficulté à avaler ou respirer.",
            "V3.8 consolidé: douleur dentaire compliquée => P2", "dentaire", "V38_DENTAL_COMPLICATED_P2")

    if s["rash"] and s["fever"]:
        return set_result(result, "P2",
            "Éruption cutanée avec fièvre : une consultation rapide est recommandée.",
            "V3.8 consolidé: rash + fièvre => P2", "dermatologique", "V38_RASH_FEVER_P2")

    if s["rash"] and s["itching"] and not s["fever"]:
        return set_result(result, "P4",
            "Boutons ou éruption avec démangeaisons sans fièvre : réaction allergique ou irritation possible. Consultez si cela s’étend, si un gonflement apparaît ou si la fièvre survient.",
            "V3.8 consolidé: rash prurigineux sans fièvre => P4", "dermatologique", "V38_RASH_ITCH_P4", allow_downgrade=True)

    if s["anxiety"] or s["sleep_disorder"]:
        if s["persistent_sadness"] and (s["loss_of_interest"] or s["depression_history"]) and s["duration_days"] >= 14:
            return set_result(result, "P3",
                "Souffrance psychique persistante détectée. Une consultation avec un professionnel de santé est recommandée rapidement.",
                "V3.8 consolidé: souffrance psychique persistante => P3", "psychiatrique", "V38_PSY_PERSISTENT_P3")
        if s["duration_days"] < 7:
            return set_result(result, "P4",
                "Stress ou trouble du sommeil récent sans danger immédiat. Reposez-vous, réduisez les sources de stress et consultez si cela persiste ou impacte fortement votre quotidien.",
                "V3.8 consolidé: stress court sans danger => P4", "psychiatrique", "V38_PSY_ACUTE_STRESS_P4", allow_downgrade=True)

    if s["digestive"]:
        if s["can_drink"] and not s["fever"] and not s["dehydration"]:
            return set_result(result, "P4",
                "Vomissements ou diarrhée sans signe de gravité immédiate. Hydratez-vous régulièrement et consultez si cela persiste, s’aggrave ou si vous ne pouvez plus boire.",
                "V3.8 consolidé: digestif simple avec hydratation possible => P4", "digestif", "V38_DIGESTIVE_SIMPLE_SAFE_P4", allow_downgrade=True)
        return set_result(result, "P3",
            "Trouble digestif aigu sans signe de gravité immédiate. Consultez rapidement si cela persiste ou si l’état général se dégrade.",
            "V3.8 consolidé: digestif aigu simple => P3", "digestif", "V38_DIGESTIVE_SIMPLE_P3")

    if s["runny_nose"] or s["sore_throat"]:
        if not s["fever"] and not s["breathing_issue"]:
            return set_result(result, "P4",
                "Vos symptômes évoquent un rhume ou une infection virale ORL légère. Reposez-vous, buvez suffisamment et consultez si la fièvre apparaît, si les symptômes durent plus de 5 jours ou s’aggravent.",
                "V3.8 consolidé: ORL viral simple => P4", "orl", "V38_ORL_SIMPLE_P4", allow_downgrade=True)

    if s["back_pain"] and not s["flank_pain"] and not s["fever"] and s["duration_days"] < 14:
        return set_result(result, "P4",
            "Douleur du dos sans signe de gravité immédiate. Surveillez l’évolution, évitez les efforts importants et consultez si la douleur persiste, s’aggrave ou s’accompagne de fièvre/faiblesse.",
            "V3.8 consolidé: lombalgie simple courte => P4", "musculo", "V38_BACK_PAIN_SIMPLE_P4", allow_downgrade=True)

    # Douleur abdominale sans fièvre/vomissements : ne pas inventer fièvre/digestif.
    if s["abdominal_pain"] and not s["fever"] and not s["digestive"]:
        return set_result(result, "P3" if s["pain_intense"] else "P4",
            "Douleur abdominale sans fièvre ni vomissements. Consultez rapidement si la douleur est forte, localisée, augmente ou persiste.",
            "V3.8 consolidé: douleur abdominale isolée sans faux positif fièvre/vomissements", "digestif", "V38_ABD_PAIN_ISOLATED", allow_downgrade=True)

    # Si la décision reste P4 avec zéro explication, ajouter une explication minimale.
    if result.priority_code == "P4" and not result.reasons:
        result.reasons.append("Aucun signe de gravité immédiate détecté")

    enrich_dynamic_questions(result, s)
    return result

# -----------------------------------------------------------------------------
# API PUBLIQUE ET CLI
# -----------------------------------------------------------------------------

def load_kb(path: str = base.KB_DEFAULT_PATH) -> Dict[str, Any]:
    return v37.load_kb(path)


def run_triage_v3_8_production(payload: Dict[str, Any], kb: Dict[str, Any], dynamic_answers: Optional[Dict[str, Any]] = None):
    """Point d'entrée principal — V3.9 intégré nativement."""
    result = v37.run_triage_v3_7_africa(payload, kb, dynamic_answers=dynamic_answers or {})
    result = apply_v39_corrections(result, payload)  # [V3.9]
    s39 = extract_v39_signals(payload)               # [V3.9] signaux enrichis
    enrich_dynamic_questions(result, s39)
    return result

run_triage = run_triage_v3_8_production



def make_json_safe(obj):
    """Convertit récursivement les objets NumPy/PyTorch non sérialisables en types Python natifs."""
    try:
        import numpy as np
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except Exception:
        pass

    try:
        import torch
        if isinstance(obj, torch.Tensor):
            if obj.numel() == 1:
                return obj.item()
            return obj.detach().cpu().tolist()
    except Exception:
        pass

    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [make_json_safe(v) for v in obj]

    if isinstance(obj, tuple):
        return [make_json_safe(v) for v in obj]

    if isinstance(obj, set):
        return list(obj)

    return obj


def interactive_cli() -> None:
    kb = load_kb()
    print("=" * 80)
    print("SERVICE DE TRIAGE - MODE INTERACTIF (MOTEUR V3.8 PRODUCTION CONSOLIDÉ)")
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
        "date_of_birth": input("7. Date de naissance du patient consulté (JJ/MM/AAAA) : ").strip(),
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
    safe_result = make_json_safe(asdict(result))
    print(json.dumps(safe_result, ensure_ascii=False, indent=2))
if __name__ == "__main__":
    interactive_cli()
