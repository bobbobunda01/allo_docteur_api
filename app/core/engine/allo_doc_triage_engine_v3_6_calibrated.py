from __future__ import annotations

"""
ALLODOCTEUR - MOTEUR V3.6 CALIBRATED
=====================================
V3.6 = V3.5 Medical Safe + calibration fine P3/P4.

Objectif : conserver la sécurité vitale V3.5 (0 faux négatif P1 sur les 100 cas)
et corriger les sous/sur-triages P3/P4 sans affaiblir P1/P2.
"""

from dataclasses import asdict
from typing import Any, Dict, Optional, List
import re
import json

try:
    import allo_doc_triage_engine_v3_5_medical_safe as v35
except ImportError:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parent))
    import allo_doc_triage_engine_v3_5_medical_safe as v35

base = v35.base


def _has(text: str, patterns: List[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _rank(p: str) -> int:
    return {"P1": 4, "P2": 3, "P3": 2, "P4": 1}.get(p, 0)


def _set_priority(result: Any, priority: str, message: str, reason: str, orientation: Optional[str] = None, domain: Optional[str] = None) -> Any:
    result.priority_code = priority
    result.color = base.PRIORITY_META[priority]["color"]
    result.urgency_label = base.PRIORITY_META[priority]["urgency_label"]
    result.orientation = orientation or base.PRIORITY_META[priority]["orientation_default"]
    result.message = message
    if domain and domain not in (result.activated_domains or []):
        result.activated_domains.append(domain)
    result.reasons.append(reason)
    return result


def _has_redflag_context(sig: Dict[str, Any]) -> bool:
    return any([
        sig.get("chest_pain"), sig.get("chest_pressure_like"), sig.get("severe_dehydration_combo"),
        sig.get("confusion"), sig.get("meningitis"), sig.get("poisoning"), sig.get("severe_burn"),
        sig.get("head_trauma"), sig.get("open_fracture"), sig.get("pregnancy_bleeding"),
        sig.get("abdomen_hard") and sig.get("severe_abdomen"),
    ])


def calibrate_p3_p4(result: Any, sig: Dict[str, Any]) -> Any:
    """Calibration clinique fine. Ne dégrade jamais P1 et n'abaisse pas les P2 safety-critical."""
    if result.priority_code == "P1":
        return result

    text = sig.get("text", "")
    fields = result.case_fields or {}
    age = (result.normalized_profile or {}).get("age_years")

    # Préserver les P2 vraiment justifiés que la calibration ne doit jamais rabaisser.
    if result.priority_code == "P2":
        if sig.get("dental_fever") or (sig.get("dental") and sig.get("fever")):
            result.message = "Une douleur dentaire avec fièvre peut évoquer une infection. Une consultation rapide est recommandée."
            return result
        if sig.get("urinary_burning") and sig.get("fever"):
            result.message = "Brûlure urinaire avec fièvre : une consultation rapide est recommandée."
            return result
        if sig.get("fever") and _has(text, [r"fatigue", r"perte d appetit", r"sueurs", r"frissons"]) and (fields.get("duration_days") is not None and fields.get("duration_days") >= 5):
            result.message = "Fièvre prolongée avec signes généraux : une évaluation médicale rapide est recommandée."
            return result
        if sig.get("fever") and _has(text, [r"enfant"]) and _has(text, [r"forte fievre", r"frissons", r"fatigue"]):
            result.message = "Fièvre importante chez l'enfant avec signes généraux : une évaluation médicale rapide est recommandée."
            return result
        if _has(text, [r"s aggrave", r"aggrav", r"rapidement"]):
            result.message = "Une aggravation rapide des symptômes nécessite une évaluation médicale rapide."
            return result

    # ------------------------------------------------------------------
    # A. Downgrade P2 -> P3 quand la V3.5 surclasse une fièvre simple.
    # ------------------------------------------------------------------
    if result.priority_code == "P2" and not _has_redflag_context(sig):
        # Fièvre isolée courte adulte, sans terrain à risque explicite.
        fever_is_truly_simple = (
            sig.get("fever")
            and not sig.get("rash")
            and not sig.get("digestive")
            and not sig.get("chest_pain")
            and not sig.get("breathing_issue")
            and not sig.get("urinary_burning")
            and not sig.get("dental")
            and not _has(text, [r"fatigue", r"perte d appetit", r"frissons", r"sueurs", r"toux", r"enfant", r"s aggrave", r"aggrav"])
            and not ("epidemiologie" in (result.activated_domains or []))
            and not (fields.get("duration_days") is not None and fields.get("duration_days") >= 5)
        )
        if fever_is_truly_simple:
            if not sig.get("diabetes") and not sig.get("pregnant") and not fields.get("immunocompromised"):
                return _set_priority(
                    result,
                    "P3",
                    "Une fièvre sans signe critique immédiat nécessite une consultation rapide si elle persiste, s'aggrave ou s'accompagne de nouveaux signes.",
                    "V3.6 calibration: fièvre simple sans terrain critique => P3",
                    "Médecin généraliste / centre de santé",
                    "fievre",
                )

        # Toux + fièvre courte sans essoufflement.
        if sig.get("fever") and _has(text, [r"\btoux\b"]) and not sig.get("breathing_issue") and sig.get("neg_breathing"):
            return _set_priority(
                result,
                "P3",
                "Toux avec fièvre sans essoufflement ni signe critique immédiat : une consultation rapide est recommandée si les symptômes persistent ou s'aggravent.",
                "V3.6 calibration: toux + fièvre sans dyspnée => P3",
                "Médecin généraliste / centre de santé",
                "respiratoire",
            )

        # Fièvre enfant qui boit, pas de red flag.
        if sig.get("fever") and _has(text, [r"enfant"]) and _has(text, [r"il boit", r"elle boit", r"boit"]):
            return _set_priority(
                result,
                "P3",
                "Fièvre chez l'enfant sans signe critique immédiat : consultation rapide recommandée, surtout si la fièvre persiste ou si l'enfant boit moins.",
                "V3.6 calibration: enfant fébrile qui boit => P3",
                "Médecin généraliste / centre de santé",
                "pediatrie",
            )

        # Diarrhée persistante explicitement sans déshydratation.
        if sig.get("digestive") and _has(text, [r"depuis quatre jours", r"4 jours"]) and _has(text, [r"sans bouche seche", r"pas de bouche seche", r"je bois normalement"]):
            return _set_priority(
                result,
                "P3",
                "Diarrhée persistante sans signe de déshydratation : consultation rapide recommandée, avec surveillance de l'hydratation.",
                "V3.6 calibration: diarrhée persistante sans déshydratation => P3",
                "Médecin généraliste / centre de santé",
                "digestif",
            )

        # Fièvre + maux de tête sans raideur de nuque ni confusion.
        if sig.get("fever") and _has(text, [r"maux de tete", r"mal a la tete"]) and not sig.get("meningitis") and not sig.get("confusion"):
            return _set_priority(
                result,
                "P3",
                "Fièvre avec maux de tête sans signe neurologique critique immédiat : consultation rapide recommandée si persistance ou aggravation.",
                "V3.6 calibration: fièvre + céphalée sans signe méningé => P3",
                "Médecin généraliste / centre de santé",
                "fievre",
            )

    # ------------------------------------------------------------------
    # B. Upgrade P4 -> P3 pour symptômes persistants ou nécessitant avis.
    # ------------------------------------------------------------------
    if result.priority_code == "P4":
        # Toux depuis >=4 jours ou toux + fatigue depuis une semaine.
        if _has(text, [r"\btoux\b", r"tousse"]) and (_has(text, [r"depuis quatre jours", r"4 jours", r"depuis une semaine", r"plus d une semaine"]) or sig.get("fever")):
            return _set_priority(
                result,
                "P3",
                "Toux persistante sans signe critique immédiat : une consultation rapide est recommandée si elle dure, s'aggrave ou s'accompagne de fièvre.",
                "V3.6 calibration: toux persistante => P3",
                "Médecin généraliste / centre de santé",
                "respiratoire",
            )

        # Urinaire simple : brûlure urinaire vraie = P3, même sans fièvre.
        if sig.get("urinary_burning"):
            return _set_priority(
                result,
                "P3",
                "Brûlure urinaire sans signe de complication immédiate : consultation rapide recommandée pour confirmer et traiter.",
                "V3.6 calibration: brûlure urinaire simple => P3",
                "Médecin généraliste / centre de santé",
                "urinaire",
            )

        # Céphalées persistantes ou céphalée + fatigue >=5 jours.
        if _has(text, [r"maux de tete", r"mal a la tete"]) and (_has(text, [r"depuis une semaine", r"depuis cinq jours", r"5 jours"]) or sig.get("fever")):
            return _set_priority(
                result,
                "P3",
                "Maux de tête persistants sans red flag immédiat : consultation rapide recommandée si cela dure ou s'aggrave.",
                "V3.6 calibration: céphalée persistante => P3",
                "Médecin généraliste / centre de santé",
                "neurologique",
            )

        # Douleur de dos persistante.
        if _has(text, [r"douleur au dos", r"mal au dos"]) and _has(text, [r"depuis une semaine", r"plus d une semaine"]):
            return _set_priority(
                result,
                "P3",
                "Douleur du dos persistante : consultation rapide recommandée si elle dure, s'intensifie ou limite les mouvements.",
                "V3.6 calibration: douleur dos persistante => P3",
                "Médecin généraliste / centre de santé",
                "musculo",
            )

        # Fatigue prolongée isolée.
        if sig.get("text") and _has(text, [r"fatigue", r"fatiguee", r"fatigue depuis"]) and _has(text, [r"plus d une semaine", r"depuis une semaine"]):
            return _set_priority(
                result,
                "P3",
                "Fatigue persistante : consultation rapide recommandée pour rechercher une cause et éviter une aggravation.",
                "V3.6 calibration: fatigue persistante => P3",
                "Médecin généraliste / centre de santé",
                "transversal",
            )

        # Anxiété + sommeil depuis deux semaines.
        if (_has(text, [r"anxieux", r"anxiete", r"angoisse"]) and _has(text, [r"dors mal", r"sommeil"]) and _has(text, [r"deux semaines", r"2 semaines"])):
            return _set_priority(
                result,
                "P3",
                "Anxiété avec troubles du sommeil persistants : consultation rapide recommandée avec un professionnel de santé.",
                "V3.6 calibration: anxiété + sommeil persistant => P3",
                "Médecin généraliste / professionnel de santé mentale",
                "psychiatrique",
            )

        # Douleur pelvienne non enceinte persistante.
        if _has(text, [r"bas du ventre", r"douleur pelvienne"]) and not sig.get("pregnant"):
            return _set_priority(
                result,
                "P3",
                "Douleur pelvienne sans signe critique immédiat : consultation rapide recommandée si elle persiste ou s'intensifie.",
                "V3.6 calibration: douleur pelvienne non enceinte => P3",
                "Médecin généraliste / centre de santé",
                "gyn_obs",
            )

        # HTA + fatigue + maux de tête.
        if sig.get("hypertension") and _has(text, [r"fatigue"]) and _has(text, [r"maux de tete", r"mal a la tete"]):
            return _set_priority(
                result,
                "P3",
                "Fatigue et maux de tête sur terrain hypertendu : consultation rapide recommandée pour contrôle clinique.",
                "V3.6 calibration: HTA + céphalée/fatigue => P3",
                "Médecin généraliste / centre de santé",
                "general",
            )

        # Sommeil perturbé > 1 semaine.
        if _has(text, [r"dors tres mal", r"troubles du sommeil", r"sommeil"]) and _has(text, [r"plus d une semaine", r"depuis une semaine"]):
            return _set_priority(
                result,
                "P3",
                "Trouble du sommeil persistant : consultation rapide recommandée si cela retentit sur la journée ou persiste.",
                "V3.6 calibration: sommeil perturbé persistant => P3",
                "Médecin généraliste / professionnel de santé mentale",
                "psychiatrique",
            )

    # ------------------------------------------------------------------
    # C. Downgrade P3 -> P4 pour cas très bénins digestifs.
    # ------------------------------------------------------------------
    if result.priority_code == "P3":
        if _has(text, [r"un peu nause", r"nauseeux", r"nausee"]) and _has(text, [r"pas de vomissement", r"sans vomissement", r"ne vomit pas"]):
            return _set_priority(
                result,
                "P4",
                "Nausée légère sans vomissement ni signe de gravité immédiate : surveillez l'évolution et consultez si cela persiste ou s'aggrave.",
                "V3.6 calibration: nausée légère sans vomissement => P4",
                "Conseils / consultation standard si persistance",
                "digestif",
            )

    return result


def load_kb(path: str = base.KB_DEFAULT_PATH) -> Dict[str, Any]:
    return v35.load_kb(path)


def run_triage_v3_6_calibrated(payload: Dict[str, Any], kb: Dict[str, Any], dynamic_answers: Optional[Dict[str, Any]] = None):
    result = v35.run_triage_v3_5_medical_safe(payload, kb, dynamic_answers=dynamic_answers)
    sig = v35.extract_safety_signals(payload)
    return calibrate_p3_p4(result, sig)


run_triage = run_triage_v3_6_calibrated


def interactive_cli() -> None:
    kb = load_kb()
    print("=" * 80)
    print("SERVICE DE TRIAGE - MODE INTERACTIF (MOTEUR V3.6 CALIBRATED)")
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

    result = run_triage_v3_6_calibrated(payload, kb, dynamic_answers={})
    print("\n" + "=" * 80)
    print("RÉSULTAT FINAL")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    interactive_cli()
