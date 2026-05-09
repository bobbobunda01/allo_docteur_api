from __future__ import annotations

"""
ALLODOCTEUR - MOTEUR V3.4 FINAL
================================
Cette version corrige les dernières failles critiques détectées en phase de test :

1. AVC suspect en texte libre : parole anormale + faiblesse d'un bras/côté => P1.
2. Douleur thoracique / pression thoracique : douleur poitrine ou chest_pressure => P2 minimum, P1 si red flag formulaire explicite.
3. Abcès dentaire probable : douleur dentaire + joue/visage gonflé => P2.
4. Rash + fièvre : P2 avec message prioritaire adapté.
5. Psychiatrie chronique sans danger suicidaire : verrouillée en P3, pas surclassée en P2 par la durée seule.
6. Correction NLP : dental_swelling, stroke_signs, chest_pain, urinary_burning plus strict.
7. Respect des required_fields avant activation d'une règle.

IMPORTANT :
- Cette version s'appuie sur le fichier V3.3 existant.
- Elle patch le module V3.3 au chargement pour éviter de recopier tout le moteur.
- Utilise cette fonction dans ton harness : run_triage_v3_4_final(...)
"""

from dataclasses import asdict
from typing import Any, Dict, Optional, List
import re
import json

import allo_doc_triage_engine_v3_3_production as base

# Sauvegarde des fonctions originales AVANT tout patch.
# C'est indispensable pour éviter une récursion infinie lorsque V3.4 remplace
# les fonctions runtime du module V3.3.
_ORIGINAL_ENSURE_RUNTIME_MESSAGES = base.ensure_runtime_messages
_ORIGINAL_ENSURE_RUNTIME_ENTRIES = base.ensure_runtime_entries
_ORIGINAL_NORMALIZE_INPUT = base.normalize_input
_ORIGINAL_BUILD_CASE_FIELDS = base.build_case_fields


# -----------------------------------------------------------------------------
# 1. PATCH NLP : nouveaux signaux critiques
# -----------------------------------------------------------------------------

base.TEXT_PATTERNS.update({
    "dental_swelling": [
        r"joue.*gonfl",
        r"joue.*enfl",
        r"visage.*gonfl",
        r"visage.*enfl",
        r"gonfl(e|er|ee|ement)",
        r"enfl(e|er|ee|ure)",
        r"abces",
        r"abc[eè]s"
    ],
    "stroke_signs": [
        r"parle bizarre",
        r"parle bizarrement",
        r"difficulte a parler",
        r"difficile de parler",
        r"ne parle plus",
        r"parole.*bizarre",
        r"parole.*trouble",
        r"bras.*ne bouge",
        r"bras.*bouge presque plus",
        r"bras.*faible",
        r"jambe.*ne bouge",
        r"jambe.*faible",
        r"faiblesse.*cote",
        r"un cote.*faible",
        r"visage.*deforme",
        r"bouche.*tordue",
        r"visage.*devi"
    ],
    "chest_pain": [
        r"douleur.*poitrine",
        r"mal.*poitrine",
        r"pression.*poitrine",
        r"poitrine.*serre",
        r"poitrine.*fait mal",
        r"douleur.*thorac",
        r"mal.*thorac"
    ],
    "pleuritic_chest_pain": [
        r"poitrine.*respire profond",
        r"douleur.*respire profond",
        r"quand je respire",
        r"respire profondement",
        r"respire profondément"
    ],
    "itching": [
        r"demange",
        r"d[eé]mange",
        r"gratte",
        r"prurit"
    ]
})


# -----------------------------------------------------------------------------
# 2. PATCH KB RUNTIME : nouvelles règles critiques
# -----------------------------------------------------------------------------

def ensure_v34_runtime_messages(kb: Dict[str, Any]) -> None:
    _ORIGINAL_ENSURE_RUNTIME_MESSAGES(kb)
    messages = kb.setdefault("messages", {})
    messages.setdefault(
        "MSG_CHEST_PAIN_P2",
        "Une douleur ou pression dans la poitrine nécessite une évaluation médicale urgente. Rendez-vous rapidement dans un centre de santé ou un service d'urgence."
    )
    messages.setdefault(
        "MSG_CHEST_PAIN_P1",
        "Une douleur ou forte pression dans la poitrine a été signalée. Rendez-vous immédiatement aux urgences ou à l'hôpital le plus proche."
    )
    messages.setdefault(
        "MSG_STROKE_P1",
        "Des signes évocateurs d'un AVC ont été détectés. Rendez-vous immédiatement aux urgences. Chaque minute compte."
    )
    messages.setdefault(
        "MSG_DENTAL_COMPLICATED_P2",
        "Une douleur dentaire avec gonflement de la joue ou du visage peut évoquer une infection. Une consultation rapide est recommandée."
    )
    messages.setdefault(
        "MSG_RASH_FEVER_P2",
        "Une éruption cutanée associée à la fièvre a été détectée. Une consultation médicale rapide est nécessaire."
    )
    messages.setdefault(
        "MSG_PSY_PERSISTENT_P3",
        "Vos symptômes évoquent une souffrance psychique persistante. Une consultation avec un professionnel de santé mentale est recommandée rapidement."
    )


def ensure_v34_runtime_entries(kb: Dict[str, Any]) -> None:
    _ORIGINAL_ENSURE_RUNTIME_ENTRIES(kb)
    entries = kb.setdefault("entries", [])
    ids = {e.get("kb_id") for e in entries}

    if "RF_STROKE_TEXT_CRITICAL" not in ids:
        entries.append({
            "kb_id": "RF_STROKE_TEXT_CRITICAL",
            "entry_class": "red_flag_entry",
            "domain": "neurologique",
            "title": "AVC suspect détecté dans le texte libre",
            "rules": [{
                "id": "RULE_STROKE_TEXT_P1",
                "priority": 1000,
                "required_fields": ["stroke_signs"],
                "logic": {"field": "stroke_signs", "op": "==", "value": True},
                "decision": {
                    "priority_level": "P1",
                    "orientation": "Urgences / hôpital le plus proche",
                    "message_key": "MSG_STROKE_P1",
                    "score_override": True
                }
            }]
        })

    if "RF_CHEST_PRESSURE_CRITICAL" not in ids:
        entries.append({
            "kb_id": "RF_CHEST_PRESSURE_CRITICAL",
            "entry_class": "red_flag_entry",
            "domain": "cardio",
            "title": "Douleur ou forte pression thoracique",
            "rules": [{
                "id": "RULE_CHEST_PRESSURE_P1",
                "priority": 1000,
                "required_fields": ["chest_pressure"],
                "logic": {"field": "chest_pressure", "op": "==", "value": True},
                "decision": {
                    "priority_level": "P1",
                    "orientation": "Urgences / hôpital le plus proche",
                    "message_key": "MSG_CHEST_PAIN_P1",
                    "score_override": True
                }
            }]
        })

    if "SYN_CHEST_PAIN" not in ids:
        entries.append({
            "kb_id": "SYN_CHEST_PAIN",
            "entry_class": "syndrome_entry",
            "domain": "cardio",
            "title": "Douleur thoracique non banalisable",
            "rules": [{
                "id": "RULE_CHEST_PAIN_P2",
                "priority": 700,
                "required_fields": ["chest_pain"],
                "logic": {
                    "all": [
                        {"field": "chest_pain", "op": "==", "value": True}
                    ]
                },
                "decision": {
                    "priority_level": "P2",
                    "orientation": "Centre de santé / service d'urgence",
                    "message_key": "MSG_CHEST_PAIN_P2",
                    "base_score": 4
                }
            }]
        })

    if "RF_RASH_FEVER_ALERT" not in ids:
        entries.append({
            "kb_id": "RF_RASH_FEVER_ALERT",
            "entry_class": "red_flag_entry",
            "domain": "dermatologique",
            "title": "Éruption cutanée avec fièvre",
            "rules": [{
                "id": "RULE_RASH_FEVER_P2_ALERT",
                "priority": 650,
                "required_fields": ["rash", "fever"],
                "logic": {
                    "all": [
                        {"field": "rash", "op": "==", "value": True},
                        {"field": "fever", "op": "==", "value": True}
                    ]
                },
                "decision": {
                    "priority_level": "P2",
                    "orientation": "Médecin généraliste / centre de santé",
                    "message_key": "MSG_RASH_FEVER_P2",
                    "score_override": False,
                    "base_score": 4
                }
            }]
        })

    # Renforcer ou ajouter le dentaire compliqué
    if "SYN_DENTAL_COMPLICATED" not in ids:
        entries.append({
            "kb_id": "SYN_DENTAL_COMPLICATED",
            "entry_class": "syndrome_entry",
            "domain": "dentaire",
            "title": "Douleur dentaire compliquée",
            "rules": [{
                "id": "RULE_DENTAL_COMPLICATED_P2",
                "priority": 600,
                "required_fields": ["dental_pain"],
                "logic": {
                    "all": [
                        {"field": "dental_pain", "op": "==", "value": True},
                        {"any": [
                            {"field": "dental_swelling", "op": "==", "value": True},
                            {"field": "dental_fever", "op": "==", "value": True},
                            {"field": "difficulty_swallowing", "op": "==", "value": True}
                        ]}
                    ]
                },
                "decision": {
                    "priority_level": "P2",
                    "orientation": "Centre de santé / dentiste",
                    "message_key": "MSG_DENTAL_COMPLICATED_P2",
                    "base_score": 4
                }
            }]
        })


# -----------------------------------------------------------------------------
# 3. REQUIRED_FIELDS : validation avant acceptation des règles
# -----------------------------------------------------------------------------

def required_fields_ok(rule_or_entry: Dict[str, Any], case_fields: Dict[str, Any]) -> bool:
    required = rule_or_entry.get("required_fields") or []
    if not required:
        return True
    return any(bool(case_fields.get(f)) for f in required)


# -----------------------------------------------------------------------------
# 4. PATCH normalize_input : corriger signaux texte et flags
# -----------------------------------------------------------------------------

def normalize_input_v34(payload: Dict[str, Any]) -> Dict[str, Any]:
    profile = _ORIGINAL_NORMALIZE_INPUT(payload)
    text = profile.get("complaint_norm", "")
    ts = profile.setdefault("text_signals", {})
    flags = profile.setdefault("normalized_flags", {})
    rf = profile.setdefault("immediate_red_flags", {})

    # Recalcule les patterns ajoutés après normalisation.
    for key in ["dental_swelling", "stroke_signs", "chest_pain", "pleuritic_chest_pain", "itching"]:
        ts[key] = any(re.search(p, text) for p in base.TEXT_PATTERNS.get(key, []))

    # AVC : le texte libre doit primer sur le formulaire.
    if ts.get("stroke_signs"):
        rf["stroke_signs"] = True

    # Douleur thoracique : détecter même si l'utilisateur n'a pas coché le red flag.
    if ts.get("chest_pain"):
        flags["pain"] = True

    # Urinaire : ne plus considérer le mot "urine" seul comme brûlure urinaire.
    strict_urinary_patterns = [
        r"brule.*urin",
        r"brulure.*urin",
        r"douleur.*urin",
        r"mal.*urin",
        r"miction.*douloureuse"
    ]
    flags["urinary_burning"] = any(re.search(p, text) for p in strict_urinary_patterns)

    # Dentaire : douleur + gonflement doit être capté comme complication.
    if ts.get("dental_swelling"):
        flags["dental_pain"] = flags.get("dental_pain", False) or ("dent" in text or "dentaire" in text)

    return profile


# -----------------------------------------------------------------------------
# 5. PATCH build_case_fields : injecter les nouveaux champs
# -----------------------------------------------------------------------------

def build_case_fields_v34(profile: Dict[str, Any], dynamic_answers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    fields = _ORIGINAL_BUILD_CASE_FIELDS(profile, dynamic_answers)
    ts = profile.get("text_signals", {})
    rf = profile.get("immediate_red_flags", {})
    flags = profile.get("normalized_flags", {})

    fields["dental_swelling"] = bool(ts.get("dental_swelling")) or bool(fields.get("dental_swelling"))
    fields["stroke_signs"] = bool(ts.get("stroke_signs")) or bool(rf.get("stroke_signs")) or bool(fields.get("stroke_signs"))
    fields["chest_pain"] = bool(ts.get("chest_pain"))
    fields["pleuritic_chest_pain"] = bool(ts.get("pleuritic_chest_pain"))
    fields["chest_pressure"] = bool(rf.get("chest_pressure"))
    fields["itching"] = bool(ts.get("itching"))

    # Corriger urinary_burning strictement.
    fields["urinary_burning"] = bool(flags.get("urinary_burning"))

    # Douleur thoracique = douleur + localisation poitrine.
    if fields["chest_pain"]:
        fields["pain"] = True
        fields["pain_location"] = "chest"

    return fields


# -----------------------------------------------------------------------------
# 6. Direct P1 : ajouter stroke et chest_pressure
# -----------------------------------------------------------------------------

base.DIRECT_P1_RULES = [
    r for r in base.DIRECT_P1_RULES
    if r.get("id") not in {"DIRECT_RF_STROKE_TEXT", "DIRECT_RF_CHEST_PRESSURE"}
] + [
    {
        "id": "DIRECT_RF_STROKE_TEXT",
        "field": "stroke_signs",
        "reason": "AVC suspect",
        "message": "Des signes évocateurs d'un AVC ont été détectés. Rendez-vous immédiatement aux urgences. Chaque minute compte."
    },
    {
        "id": "DIRECT_RF_CHEST_PRESSURE",
        "field": "chest_pressure",
        "reason": "Douleur ou forte pression dans la poitrine",
        "message": "Une douleur ou forte pression dans la poitrine a été signalée. Rendez-vous immédiatement aux urgences ou à l'hôpital le plus proche."
    }
]


# -----------------------------------------------------------------------------
# 7. Moteur V3.4 : patch puis délégation au moteur V3.3
# -----------------------------------------------------------------------------

def load_kb(path: str = base.KB_DEFAULT_PATH) -> Dict[str, Any]:
    # Chargement direct de la KB pour éviter que base.load_kb() n'appelle
    # des fonctions déjà patchées par V3.4.
    with open(path, "r", encoding="utf-8") as f:
        kb = json.load(f)
    ensure_v34_runtime_messages(kb)
    ensure_v34_runtime_entries(kb)
    return kb


def _patch_base_runtime() -> None:
    # Patch idempotent : les fonctions V3.4 appellent toujours les fonctions
    # originales sauvegardées plus haut, jamais les versions déjà patchées.
    base.ensure_runtime_messages = ensure_v34_runtime_messages
    base.ensure_runtime_entries = ensure_v34_runtime_entries
    base.normalize_input = normalize_input_v34
    base.build_case_fields = build_case_fields_v34


def _postprocess_psych_and_messages(result: Any) -> Any:
    """Corrige deux comportements : psy chronique surclassée et message de niveau incorrect."""
    domains = set(result.activated_domains or [])
    entries = set(result.activated_entries or [])
    fields = result.case_fields or {}

    def has_entry(fragment: str) -> bool:
        return any(fragment in e for e in entries)

    # Psychiatrie chronique sans danger immédiat : P3, pas P2.
    # Compatible avec les IDs KB V3 ("PSY_SYN_PERSISTENT") et V4 ("SYN_PSY_PERSISTENT").
    if "psychiatrique" in domains and not fields.get("danger_to_self"):
        if result.priority_code == "P2" and (has_entry("PSY_SYN_PERSISTENT") or has_entry("SYN_PSY_PERSISTENT")):
            result.priority_code = "P3"
            result.color = base.PRIORITY_META["P3"]["color"]
            result.urgency_label = base.PRIORITY_META["P3"]["urgency_label"]
            result.orientation = "Médecin généraliste / professionnel de santé mentale"
            result.message = "Vos symptômes évoquent une souffrance psychique persistante. Une consultation avec un professionnel de santé mentale est recommandée rapidement."

    # Message prioritaire selon syndrome dominant, compatible avec plusieurs conventions d'IDs.
    if has_entry("DENTAL_SYN_COMPLICATED") or has_entry("SYN_DENTAL_COMPLICATED"):
        result.message = "Une douleur dentaire avec gonflement de la joue ou du visage peut évoquer une infection. Une consultation rapide est recommandée."
    elif has_entry("SYN_CHEST_PAIN"):
        result.message = "Une douleur ou pression dans la poitrine nécessite une évaluation médicale urgente. Rendez-vous rapidement dans un centre de santé ou un service d'urgence."
    elif has_entry("RASH_FEVER") or has_entry("RF_RASH_FEVER_ALERT"):
        result.message = "Une éruption cutanée associée à la fièvre a été détectée. Une consultation médicale rapide est nécessaire."
    elif (has_entry("PSY_SYN_PERSISTENT") or has_entry("SYN_PSY_PERSISTENT")) and result.priority_code == "P3":
        result.message = "Vos symptômes évoquent une souffrance psychique persistante. Une consultation avec un professionnel de santé mentale est recommandée rapidement."

    return result


def run_triage_v3_4_final(payload: Dict[str, Any], kb: Dict[str, Any], dynamic_answers: Optional[Dict[str, Any]] = None):
    _patch_base_runtime()
    ensure_v34_runtime_messages(kb)
    ensure_v34_runtime_entries(kb)

    result = base.run_triage_v3_3_production(payload, kb, dynamic_answers=dynamic_answers)

    # Correction spécifique : si dental_swelling est vrai, forcer la réévaluation en P2 si le moteur V3.3 a gardé le simple.
    fields = result.case_fields or {}
    entries = set(result.activated_entries or [])
    domains = set(result.activated_domains or [])

    if fields.get("dental_pain") and fields.get("dental_swelling") and result.priority_code in {"P3", "P4"}:
        result.priority_code = "P2"
        result.color = base.PRIORITY_META["P2"]["color"]
        result.urgency_label = base.PRIORITY_META["P2"]["urgency_label"]
        result.orientation = "Centre de santé / dentiste"
        result.message = "Une douleur dentaire avec gonflement de la joue ou du visage peut évoquer une infection. Une consultation rapide est recommandée."
        if "SYN_DENTAL_COMPLICATED" not in entries:
            result.activated_entries.append("SYN_DENTAL_COMPLICATED")
        if "dentaire" not in domains:
            result.activated_domains.append("dentaire")
        result.reasons.append("Correction V3.4: douleur dentaire avec gonflement => P2")

    if fields.get("chest_pain") and result.priority_code in {"P3", "P4"}:
        result.priority_code = "P2"
        result.color = base.PRIORITY_META["P2"]["color"]
        result.urgency_label = base.PRIORITY_META["P2"]["urgency_label"]
        result.orientation = "Centre de santé / service d'urgence"
        result.message = "Une douleur ou pression dans la poitrine nécessite une évaluation médicale urgente. Rendez-vous rapidement dans un centre de santé ou un service d'urgence."
        if "SYN_CHEST_PAIN" not in entries:
            result.activated_entries.append("SYN_CHEST_PAIN")
        if "cardio" not in domains:
            result.activated_domains.append("cardio")
        result.reasons.append("Correction V3.4: douleur thoracique non banalisable => P2")

    result = _postprocess_psych_and_messages(result)
    return result


# -----------------------------------------------------------------------------
# CLI compatible
# -----------------------------------------------------------------------------

def interactive_cli() -> None:
    _patch_base_runtime()
    kb = load_kb()
    print("=" * 80)
    print("SERVICE DE TRIAGE - MODE INTERACTIF (MOTEUR V3.4 FINAL)")
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

    preview = run_triage_v3_4_final(payload, kb, dynamic_answers={})
    print("\n[DEBUG V3.4] Domaines activés :", preview.activated_domains)
    print("[DEBUG V3.4] Entrées activées :", preview.activated_entries)
    print("[DEBUG V3.4] Score initial :", preview.score_total)

    dynamic_answers: Dict[str, Any] = {}
    if preview.priority_code != "P1" and preview.asked_questions:
        print("\n" + "=" * 80)
        print("QUESTIONS COMPLÉMENTAIRES")
        for q in preview.asked_questions:
            qid = q.get("id")
            qlabel = q.get("label")
            qtype = q.get("type")
            if qtype == "boolean":
                dynamic_answers[qid] = base.ask_bool(qlabel)
            elif qtype == "single_select":
                dynamic_answers[qid] = base.choose_one(f"\n{qlabel}", q.get("options", []))
            else:
                dynamic_answers[qid] = input(f"{qlabel} : ").strip()

    result = run_triage_v3_4_final(payload, kb, dynamic_answers=dynamic_answers)
    print("\n" + "=" * 80)
    print("RÉSULTAT FINAL")
    print(base.json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    interactive_cli()
