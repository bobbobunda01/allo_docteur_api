from __future__ import annotations

"""
ALLODOCTEUR - MOTEUR V3.5 MEDICAL SAFE
======================================
Refactor safety-first au-dessus de V3.4.

Objectif : réduire les faux négatifs critiques P1 avant mise en production.
Cette version ajoute :
1. Une couche Safety NLP indépendante de la KB.
2. Une correction des négations fréquentes : sans fièvre, sans gonflement, sans vomissement...
3. Des overrides P1 médicaux avant/après moteur : thorax, méningite, intoxication, trauma, brûlure, fracture ouverte,
   déshydratation sévère, grossesse + saignement, confusion brutale.
4. Des upgrades P2 sur terrains à risque : fièvre + diabète/grossesse/immunodépression, dentaire + fièvre.
5. Des downgrades contrôlés pour éviter les faux positifs P2/P3 sur cas bénins avec négation explicite.

Ce moteur reste un outil d'orientation de triage, pas un diagnostic.
"""

from dataclasses import asdict
from typing import Any, Dict, Optional, List, Tuple
import copy
import re
import json

try:
    import allo_doc_triage_engine_v3_4_final_corrected as v34
except ImportError:
    import allo_doc_triage_engine_v3_4_final as v34

base = v34.base


def _norm(text: str) -> str:
    return base.norm_text(text or "")


def _has(text: str, patterns: List[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _negated(text: str, concept: str) -> bool:
    """Détecte quelques négations cliniques courantes en français normalisé."""
    negs = {
        "fever": [r"sans fievre", r"pas de fievre", r"aucune fievre", r"non febrile"],
        "swelling": [r"sans gonflement", r"pas de gonflement", r"aucun gonflement", r"sans joue gonfl", r"pas de joue gonfl"],
        "vomiting": [r"pas de vomissement", r"sans vomissement", r"ne vomit pas", r"aucun vomissement"],
        "diarrhea": [r"pas de diarrhee", r"sans diarrhee", r"aucune diarrhee"],
        "rash": [r"sans eruption", r"pas d eruption", r"pas de boutons", r"sans boutons"],
        "breathing": [r"sans essoufflement", r"pas d essoufflement", r"respire normalement", r"sans difficulte respiratoire"],
        "dehydration": [r"sans bouche seche", r"pas de bouche seche", r"urine normalement", r"je bois normalement"],
    }
    return _has(text, negs.get(concept, []))


def extract_safety_signals(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extraction clinique prioritaire, indépendante du routage KB."""
    text = _norm(payload.get("complaint_text", ""))
    rf = payload.get("immediate_red_flags") or {}
    associated = [_norm(x) for x in (payload.get("associated_signs") or [])]
    history = [_norm(x) for x in (payload.get("medical_history") or [])]
    sex = _norm(payload.get("sex", ""))
    pregnant = bool(payload.get("pregnant")) or "enceinte" in text

    fever_text = _has(text, [r"\bfievre\b", r"forte fievre", r"temperature", r"frissons"])
    fever = (fever_text or any("fievre" in x for x in associated)) and not _negated(text, "fever")

    digestive = (
        _has(text, [r"diarrh", r"vomis", r"vomissement", r"selles liquides", r"gastro"])
        or any("vomissements diarrhee" in x or "vomissements" in x or "diarrhee" in x for x in associated)
    )
    if _negated(text, "vomiting") and _negated(text, "diarrhea"):
        digestive = False

    chest_pain = _has(text, [
        r"douleur.*poitrine", r"mal.*poitrine", r"pression.*poitrine", r"poitrine.*serre",
        r"serrement.*poitrine", r"douleur.*thorac", r"oppression", r"ca serre.*poitrine"
    ])
    exertional_or_pressure = _has(text, [r"pression", r"serre", r"oppression", r"quand je marche", r"a l effort", r"effort"])
    pleuritic = _has(text, [r"respire profond", r"quand je respire", r"inspiration"])
    breath = (_has(text, [r"essouffle", r"respire", r"manque d air", r"cherche l air", r"etouffe"]) or any("essoufflement" in x for x in associated)) and not _negated(text, "breathing")

    urine_low = _has(text, [
        r"j urine presque plus", r"je n urine presque plus", r"n urine presque plus", r"urine presque plus",
        r"urine tres peu", r"j urine tres peu", r"plus d urine", r"n a presque pas urine", r"urine diminuee",
        r"je fais tres peu pipi", r"pipi tres peu"
    ])
    dehydration = _has(text, [r"bouche seche", r"ma bouche est seche", r"bouche tres seche", r"soif intense", r"yeux creux", r"tres faible", r"tres mou", r"abattu", r"somnolent"])
    unable_to_drink = _has(text, [r"ne peut plus boire", r"n arrive pas a boire", r"incapable de boire", r"ne garde pas les liquides", r"vomis tout ce que je bois", r"vomit tout ce que .* boit"])
    if _negated(text, "dehydration"):
        dehydration = False

    confusion = bool(rf.get("sudden_confusion")) or _has(text, [r"confus", r"confuse", r"confusion", r"parle n importe", r"comportement bizarre", r"delire", r"desoriente"])
    meningitis = (fever and _has(text, [r"raideur.*nuque", r"nuque raide", r"cou raide", r"raideur.*cou", r"violents maux de tete"])) or bool(rf.get("fever_with_neck_stiffness"))
    poisoning = bool(rf.get("poisoning")) or _has(text, [r"produit toxique", r"poison", r"a bu.*toxique", r"surdosage", r"medicament.*trop", r"ingestion"])
    severe_burn = bool(rf.get("severe_burn")) or _has(text, [r"brulure grave", r"brulure profonde", r"brule.*torse", r"brulure.*visage", r"brulure.*etendue"])
    head_trauma = bool(rf.get("head_trauma")) or _has(text, [r"choc violent.*tete", r"coup.*tete", r"traumatisme cranien", r"apres moto", r"accident moto.*tete"])
    open_fracture = bool(rf.get("open_fracture_or_major_accident")) or _has(text, [r"fracture ouverte", r"os visible", r"os qui sort", r"jambe cassee.*os"])
    abdomen_hard = bool(rf.get("board_like_abdomen")) or _has(text, [r"ventre dur", r"abdomen dur", r"ventre.*dur"])
    severe_abdomen = _has(text, [r"douleur tres forte.*ventre", r"ventre tres douloureux", r"douleur intense.*ventre"])
    pregnancy_bleeding = pregnant and _has(text, [r"je saigne", r"saignement", r"pertes de sang", r"saigne du vagin"])

    dental = _has(text, [r"\bdent\b", r"dentaire", r"abces"])
    dental_swelling = _has(text, [r"joue.*gonfl", r"visage.*gonfl", r"gonfl", r"enfl", r"abces"])
    if _negated(text, "swelling"):
        dental_swelling = False
    dental_fever = dental and fever

    rash = (_has(text, [r"bouton", r"eruption", r"plaques", r"taches", r"cloques", r"demange", r"gratte"]) or any("eruption" in x for x in associated)) and not _negated(text, "rash")
    urinary_burning = _has(text, [r"brule.*urin", r"brulure.*urin", r"douleur.*urin", r"miction.*douloureuse", r"ca brule.*urine"])

    diabetes = any("diabete" in x for x in history)
    hypertension = any("hypertension" in x for x in history)
    asthma = any("asthme" in x for x in history)

    return {
        "text": text,
        "fever": fever,
        "digestive": digestive,
        "chest_pain": chest_pain,
        "chest_pressure_like": chest_pain and exertional_or_pressure,
        "pleuritic_chest_pain": chest_pain and pleuritic,
        "breathing_issue": breath,
        "urine_output_low": urine_low,
        "dehydration_signs": dehydration,
        "unable_to_drink": unable_to_drink,
        "severe_dehydration_combo": digestive and (urine_low or unable_to_drink) and (dehydration or unable_to_drink or urine_low),
        "confusion": confusion,
        "meningitis": meningitis,
        "poisoning": poisoning,
        "severe_burn": severe_burn,
        "head_trauma": head_trauma,
        "open_fracture": open_fracture,
        "abdomen_hard": abdomen_hard,
        "severe_abdomen": severe_abdomen,
        "pregnancy_bleeding": pregnancy_bleeding,
        "pregnant": pregnant,
        "dental": dental,
        "dental_swelling": dental_swelling,
        "dental_fever": dental_fever,
        "rash": rash,
        "rash_with_fever": rash and fever,
        "urinary_burning": urinary_burning,
        "diabetes": diabetes,
        "hypertension": hypertension,
        "asthma": asthma,
        "neg_fever": _negated(text, "fever"),
        "neg_swelling": _negated(text, "swelling"),
        "neg_vomiting": _negated(text, "vomiting"),
        "neg_breathing": _negated(text, "breathing"),
    }


def preprocess_payload_v35(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    p = copy.deepcopy(payload)
    sig = extract_safety_signals(p)
    r = p.setdefault("immediate_red_flags", {})

    # On injecte les red flags vitaux détectés dans le texte libre.
    if sig["chest_pressure_like"]:
        r["chest_pressure"] = True
    if sig["severe_dehydration_combo"]:
        r["severe_diarrhea_unable_to_drink"] = True
    if sig["confusion"]:
        r["sudden_confusion"] = True
    if sig["meningitis"]:
        r["fever_with_neck_stiffness"] = True
    if sig["poisoning"]:
        r["poisoning"] = True
    if sig["severe_burn"]:
        r["severe_burn"] = True
    if sig["head_trauma"]:
        r["head_trauma"] = True
    if sig["open_fracture"]:
        r["open_fracture_or_major_accident"] = True
    if sig["abdomen_hard"] and sig["severe_abdomen"]:
        r["board_like_abdomen"] = True
    if sig["pregnancy_bleeding"]:
        r["uncontrollable_bleeding"] = True
    if sig["rash_with_fever"]:
        r["rash_with_fever"] = True

    return p, sig


_ORIG_V34_NORMALIZE = v34.normalize_input_v34
_ORIG_V34_BUILD = v34.build_case_fields_v34


def normalize_input_v35(payload: Dict[str, Any]) -> Dict[str, Any]:
    profile = _ORIG_V34_NORMALIZE(payload)
    sig = extract_safety_signals(payload)
    flags = profile.setdefault("normalized_flags", {})
    ts = profile.setdefault("text_signals", {})
    rf = profile.setdefault("immediate_red_flags", {})

    # Correction des négations et enrichissement signaux.
    if sig["neg_fever"]:
        flags["fever"] = False
    else:
        flags["fever"] = bool(flags.get("fever")) or sig["fever"]

    flags["digestive_symptom"] = sig["digestive"]
    flags["breathing_issue"] = (bool(flags.get("breathing_issue")) or sig["breathing_issue"]) and not sig["neg_breathing"]
    flags["rash"] = sig["rash"]
    flags["urinary_burning"] = sig["urinary_burning"]
    flags["dental_pain"] = bool(flags.get("dental_pain")) or sig["dental"]

    ts["urine_output_low"] = sig["urine_output_low"]
    ts["dehydration_signs"] = sig["dehydration_signs"]
    ts["unable_to_drink"] = sig["unable_to_drink"]
    ts["dental_swelling"] = sig["dental_swelling"]
    ts["chest_pain"] = sig["chest_pain"]
    ts["pleuritic_chest_pain"] = sig["pleuritic_chest_pain"]
    ts["respiratory_distress"] = bool(ts.get("respiratory_distress")) or (sig["breathing_issue"] and _has(sig["text"], [r"respire tres mal", r"cherche l air", r"etouffe"]))
    ts["vaginal_bleeding"] = sig["pregnancy_bleeding"]

    rf["chest_pressure"] = bool(rf.get("chest_pressure")) or sig["chest_pressure_like"]
    rf["sudden_confusion"] = bool(rf.get("sudden_confusion")) or sig["confusion"]
    rf["fever_with_neck_stiffness"] = bool(rf.get("fever_with_neck_stiffness")) or sig["meningitis"]
    rf["poisoning"] = bool(rf.get("poisoning")) or sig["poisoning"]
    rf["severe_burn"] = bool(rf.get("severe_burn")) or sig["severe_burn"]
    rf["head_trauma"] = bool(rf.get("head_trauma")) or sig["head_trauma"]
    rf["open_fracture_or_major_accident"] = bool(rf.get("open_fracture_or_major_accident")) or sig["open_fracture"]
    rf["board_like_abdomen"] = bool(rf.get("board_like_abdomen")) or (sig["abdomen_hard"] and sig["severe_abdomen"])
    rf["severe_diarrhea_unable_to_drink"] = bool(rf.get("severe_diarrhea_unable_to_drink")) or sig["severe_dehydration_combo"]
    rf["uncontrollable_bleeding"] = bool(rf.get("uncontrollable_bleeding")) or sig["pregnancy_bleeding"]
    rf["rash_with_fever"] = bool(rf.get("rash_with_fever")) or sig["rash_with_fever"]

    return profile


def build_case_fields_v35(profile: Dict[str, Any], dynamic_answers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    fields = _ORIG_V34_BUILD(profile, dynamic_answers)
    text_payload = {"complaint_text": profile.get("complaint_text", ""), "associated_signs": profile.get("associated_signs_raw", []), "medical_history": profile.get("medical_history_raw", []), "sex": profile.get("sex"), "pregnant": profile.get("pregnant"), "immediate_red_flags": profile.get("immediate_red_flags", {})}
    sig = extract_safety_signals(text_payload)

    fields["fever"] = sig["fever"]
    fields["digestive_symptom"] = sig["digestive"]
    fields["urine_output_low"] = sig["urine_output_low"]
    fields["dehydration_signs"] = sig["dehydration_signs"]
    fields["unable_to_drink"] = sig["unable_to_drink"] or fields.get("unable_to_drink", False)
    fields["dental_swelling"] = sig["dental_swelling"]
    fields["dental_fever"] = sig["dental_fever"]
    fields["rash"] = sig["rash"]
    fields["urinary_burning"] = sig["urinary_burning"]
    fields["chest_pain"] = sig["chest_pain"]
    fields["pleuritic_chest_pain"] = sig["pleuritic_chest_pain"]
    fields["chest_pressure"] = sig["chest_pressure_like"] or fields.get("chest_pressure", False)
    fields["sudden_confusion"] = sig["confusion"]
    fields["mental_status_change"] = sig["confusion"] or fields.get("mental_status_change", False)
    fields["neck_stiffness"] = sig["meningitis"] or fields.get("neck_stiffness", False)
    fields["severe_dehydration"] = sig["severe_dehydration_combo"]
    fields["vaginal_bleeding"] = sig["pregnancy_bleeding"] or fields.get("vaginal_bleeding", False)
    if sig["chest_pain"]:
        fields["pain"] = True
        fields["pain_location"] = "chest"
    if sig["severe_abdomen"]:
        fields["severe_abdominal_pain"] = True
        fields["pain"] = True
        fields["pain_location"] = "abdomen"
    return fields


def _patch_v34_runtime_v35() -> None:
    # Patch les fonctions utilisées par v34._patch_base_runtime.
    v34.normalize_input_v34 = normalize_input_v35
    v34.build_case_fields_v34 = build_case_fields_v35


def _force_priority(result: Any, priority: str, message: str, reason: str, domain: str = "transversal", entry: str = "V35_SAFETY_OVERRIDE") -> Any:
    result.priority_code = priority
    result.color = base.PRIORITY_META[priority]["color"]
    result.urgency_label = base.PRIORITY_META[priority]["urgency_label"]
    result.orientation = base.PRIORITY_META[priority]["orientation_default"]
    result.message = message
    if domain and domain not in (result.activated_domains or []):
        result.activated_domains.append(domain)
    if entry and entry not in (result.activated_entries or []):
        result.activated_entries.append(entry)
    result.reasons.append(reason)
    if priority == "P1":
        result.asked_questions = []
        result.score_breakdown = ["V3.5 safety-first : override P1"]
    return result


def _rank(p: str) -> int:
    return {"P1": 4, "P2": 3, "P3": 2, "P4": 1}.get(p, 0)


def postprocess_v35(result: Any, sig: Dict[str, Any]) -> Any:
    # P1 vitaux absolus.
    p1_rules = [
        (sig["chest_pressure_like"], "Douleur/pression thoracique à risque détectée. Rendez-vous immédiatement aux urgences.", "V3.5: thorax pression/effort => P1", "cardio"),
        (sig["severe_dehydration_combo"], "Des signes de déshydratation sévère ont été détectés. Rendez-vous immédiatement aux urgences.", "V3.5: diarrhée/vomissements + oligurie/incapacité hydratation => P1", "digestif"),
        (sig["confusion"], "Une confusion brutale ou un comportement neurologique anormal a été détecté. Rendez-vous immédiatement aux urgences.", "V3.5: confusion brutale => P1", "neurologique"),
        (sig["meningitis"], "Fièvre avec raideur de la nuque ou violents maux de tête : suspicion de méningite. Rendez-vous immédiatement aux urgences.", "V3.5: méningite suspecte => P1", "infectieux"),
        (sig["poisoning"], "Ingestion de produit toxique ou surdosage suspecté. Rendez-vous immédiatement aux urgences.", "V3.5: intoxication => P1", "toxicologie"),
        (sig["severe_burn"], "Brûlure grave ou profonde détectée. Rendez-vous immédiatement aux urgences.", "V3.5: brûlure grave => P1", "trauma"),
        (sig["head_trauma"], "Traumatisme crânien ou choc violent à la tête détecté. Rendez-vous immédiatement aux urgences.", "V3.5: traumatisme crânien => P1", "trauma"),
        (sig["open_fracture"], "Fracture ouverte ou os visible détecté. Rendez-vous immédiatement aux urgences.", "V3.5: fracture ouverte => P1", "trauma"),
        (sig["abdomen_hard"] and sig["severe_abdomen"], "Douleur abdominale intense avec ventre dur : urgence abdominale possible. Rendez-vous immédiatement aux urgences.", "V3.5: abdomen aigu => P1", "digestif"),
        (sig["pregnancy_bleeding"], "Saignement pendant la grossesse détecté. Rendez-vous immédiatement aux urgences.", "V3.5: grossesse + saignement => P1", "gyn_obs"),
    ]
    for cond, msg, reason, dom in p1_rules:
        if cond and result.priority_code != "P1":
            return _force_priority(result, "P1", msg, reason, dom)

    # P2 safety upgrades.
    p2_rules = [
        (sig["chest_pain"], "Une douleur thoracique nécessite une évaluation médicale urgente.", "V3.5: douleur thoracique => P2", "cardio"),
        (sig["digestive"] and (sig["dehydration_signs"] or sig["urine_output_low"]), "Des signes de déshydratation ont été détectés. Une évaluation médicale rapide est recommandée.", "V3.5: digestif + déshydratation => P2", "digestif"),
        (sig["dental"] and (sig["dental_swelling"] or sig["dental_fever"]), "Une douleur dentaire avec fièvre ou gonflement peut évoquer une infection. Une consultation rapide est recommandée.", "V3.5: dentaire compliqué => P2", "dentaire"),
        (sig["pregnant"] and sig["fever"], "Fièvre pendant la grossesse : une évaluation médicale rapide est recommandée.", "V3.5: grossesse + fièvre => P2", "gyn_obs"),
        (sig["fever"] and (sig["diabetes"]), "Fièvre sur terrain diabétique : une évaluation médicale rapide est recommandée.", "V3.5: fièvre + diabète => P2", "infectieux"),
        (sig["rash_with_fever"], "Une éruption cutanée associée à la fièvre nécessite une consultation rapide.", "V3.5: rash + fièvre => P2", "dermatologique"),
        (sig["severe_abdomen"], "Douleur abdominale intense : une évaluation médicale rapide est recommandée.", "V3.5: douleur abdominale intense => P2", "digestif"),
    ]
    for cond, msg, reason, dom in p2_rules:
        if cond and _rank(result.priority_code) < _rank("P2"):
            return _force_priority(result, "P2", msg, reason, dom, "V35_SAFETY_UPGRADE")

    # Downgrades contrôlés sur cas bénins clairement niés.
    text = sig["text"]
    entries = set(result.activated_entries or [])
    if result.priority_code == "P2":
        if sig["rash"] and not sig["fever"] and sig["neg_fever"]:
            result.priority_code = "P4"
            result.color = base.PRIORITY_META["P4"]["color"]
            result.urgency_label = base.PRIORITY_META["P4"]["urgency_label"]
            result.orientation = "Médecin généraliste / dermatologue"
            result.message = "Une éruption ou démangeaison sans fièvre évoque souvent un problème cutané simple. Consultez si cela s'étend, persiste ou s'aggrave."
            result.reasons.append("V3.5: correction négation fièvre sur rash simple => P4")
        if sig["dental"] and sig["neg_swelling"] and not sig["fever"]:
            result.priority_code = "P4"
            result.color = base.PRIORITY_META["P4"]["color"]
            result.urgency_label = base.PRIORITY_META["P4"]["urgency_label"]
            result.orientation = "Dentiste"
            result.message = "Une douleur dentaire sans fièvre ni gonflement nécessite une consultation chez le dentiste, sans signe d'urgence immédiate."
            result.reasons.append("V3.5: correction négation gonflement dentaire => P4")

    if result.priority_code == "P3":
        if _has(text, [r"un peu stresse", r"stress[e]? depuis hier"]) and not _has(text, [r"tristesse", r"suicid", r"disparaitre", r"plus envie de vivre"]):
            result.priority_code = "P4"
            result.color = base.PRIORITY_META["P4"]["color"]
            result.urgency_label = base.PRIORITY_META["P4"]["urgency_label"]
            result.orientation = "Conseils / consultation standard si persistance"
            result.message = "Stress léger récent sans signe de danger immédiat. Consultez si cela persiste, s'aggrave ou retentit sur votre vie quotidienne."
            result.reasons.append("V3.5: stress léger récent => P4")
        if _has(text, [r"pas bien dormi cette nuit", r"mal dormi cette nuit"]) and not _has(text, [r"depuis plusieurs", r"depuis plus d une semaine", r"tristesse"]):
            result.priority_code = "P4"
            result.color = base.PRIORITY_META["P4"]["color"]
            result.urgency_label = base.PRIORITY_META["P4"]["urgency_label"]
            result.orientation = "Conseils / consultation standard si persistance"
            result.message = "Insomnie ponctuelle sans signe de gravité immédiate. Consultez si elle persiste ou s'aggrave."
            result.reasons.append("V3.5: insomnie ponctuelle => P4")
        if _has(text, [r"nez qui coule", r"petite toux", r"mal de gorge leger"]) and sig["neg_fever"]:
            result.priority_code = "P4"
            result.color = base.PRIORITY_META["P4"]["color"]
            result.urgency_label = base.PRIORITY_META["P4"]["urgency_label"]
            result.orientation = "Conseils / consultation standard si persistance"
            result.message = "Symptôme ORL/respiratoire léger sans fièvre ni signe de gravité. Consultez si cela persiste ou s'aggrave."
            result.reasons.append("V3.5: rhume/toux légère sans fièvre => P4")

    # Message dentaire simple persistant plus spécifique.
    if sig["dental"] and result.priority_code in {"P3", "P4"} and not sig["dental_swelling"] and not sig["fever"]:
        result.orientation = "Dentiste"
        if result.priority_code == "P3":
            result.message = "Une douleur dentaire persistante nécessite une consultation chez un dentiste afin d'éviter une complication."
        else:
            result.message = "Une douleur dentaire sans signe de complication immédiate nécessite une consultation chez le dentiste."

    return result


def load_kb(path: str = base.KB_DEFAULT_PATH) -> Dict[str, Any]:
    return v34.load_kb(path)


def run_triage_v3_5_medical_safe(payload: Dict[str, Any], kb: Dict[str, Any], dynamic_answers: Optional[Dict[str, Any]] = None):
    _patch_v34_runtime_v35()
    safe_payload, sig = preprocess_payload_v35(payload)
    result = v34.run_triage_v3_4_final(safe_payload, kb, dynamic_answers=dynamic_answers)
    return postprocess_v35(result, sig)


# Alias pratique
run_triage = run_triage_v3_5_medical_safe


def interactive_cli() -> None:
    _patch_v34_runtime_v35()
    kb = load_kb()
    print("=" * 80)
    print("SERVICE DE TRIAGE - MODE INTERACTIF (MOTEUR V3.5 MEDICAL SAFE)")
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

    result = run_triage_v3_5_medical_safe(payload, kb, dynamic_answers={})
    print("\n" + "=" * 80)
    print("RÉSULTAT FINAL")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    interactive_cli()
