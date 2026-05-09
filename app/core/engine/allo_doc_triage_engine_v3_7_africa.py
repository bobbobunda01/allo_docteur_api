from __future__ import annotations

"""
ALLODOCTEUR - MOTEUR V3.7 AFRICA CONTEXT-AWARE

V3.7 = V3.6 Calibrated + couche santé publique Afrique/RDC.

Ce moteur ajoute une couche contextuelle au-dessus de V3.6 :
- paludisme probable / paludisme grave
- choléra / diarrhée aqueuse et déshydratation
- tuberculose suspecte
- rougeole / rash fébrile
- méningite
- typhoïde probable
- grossesse + fièvre/saignement
- enfant <5 ans + signes danger
- morsures/serpent/chien
- malnutrition/anémie
- fallback sécurisé Afrique

Il s'agit d'un outil d'orientation, pas d'un diagnostic.
"""

from dataclasses import asdict
from typing import Any, Dict, Optional, List
import re
import json

try:
    import allo_doc_triage_engine_v3_6_calibrated as v36
except ImportError:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parent))
    import allo_doc_triage_engine_v3_6_calibrated as v36

base = v36.base

DRC_PROVINCES = {
    "kinshasa", "kongo central", "kwango", "kwilu", "mai ndombe",
    "kasai", "kasai central", "kasai oriental", "lomami", "sankuru",
    "haut lomami", "haut katanga", "lualaba", "tanganyika",
    "sud kivu", "nord kivu", "maniema", "tshopo", "ituri",
    "bas uele", "haut uele", "mongala", "nord ubangi", "sud ubangi",
    "equateur", "tshuapa"
}

HIGH_WATERBORNE_RISK_PROVINCES = {
    "kinshasa", "kongo central", "kwilu", "mai ndombe", "equateur",
    "tshopo", "nord kivu", "sud kivu", "tanganyika", "haut lomami",
    "ituri", "sankuru"
}


def _norm(text: Any) -> str:
    try:
        return base.norm_text(str(text or ""))
    except Exception:
        return str(text or "").lower()


def _has(text: str, patterns: List[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _negated(text: str, patterns: List[str], window: int = 7) -> bool:
    """Négation locale stricte : la négation doit précéder le concept.
    Évite : "un peu de fièvre mais pas de saignement" => fièvre faussement niée.
    """
    negs = ["sans", "pas de", "pas d", "aucun", "aucune", "ni"]
    words = text.split()
    for i, w in enumerate(words):
        for neg in negs:
            nw = neg.split()
            if words[i:i+len(nw)] == nw:
                zone = " ".join(words[i+len(nw): i+len(nw)+window])
                if any(re.search(p, zone) for p in patterns):
                    return True
    return False


def _positive(text: str, patterns: List[str]) -> bool:
    return _has(text, patterns) and not _negated(text, patterns)


def _rank(p: str) -> int:
    return {"P1": 4, "P2": 3, "P3": 2, "P4": 1}.get(p, 0)


def _age(payload: Dict[str, Any]) -> Optional[int]:
    dob = str(payload.get("date_of_birth") or "").strip()
    if not dob or "/" not in dob:
        return None
    try:
        return 2026 - int(dob.split("/")[-1])
    except Exception:
        return None


def extract_africa_signals(payload: Dict[str, Any]) -> Dict[str, Any]:
    text = _norm(payload.get("complaint_text", ""))
    province = _norm(payload.get("province", "")).strip()
    associated = [_norm(x) for x in (payload.get("associated_signs") or [])]
    history = [_norm(x) for x in (payload.get("medical_history") or [])]
    age = _age(payload)

    fever = _has(text, [r"\bfievre\b", r"temperature", r"frissons", r"chaud.*corps"]) or any("fievre" in x for x in associated)
    headache = _has(text, [r"maux de tete", r"mal a la tete", r"cephale"]) or any("maux de tete" in x for x in associated)
    fatigue = _has(text, [r"fatigue", r"fatique", r"faible", r"faiblesse", r"courbature", r"courbatures", r"abat", r"mou"]) or any("fatigue" in x for x in associated)
    appetite_loss = _has(text, [r"perte d appetit", r"pas d appetit", r"mange plus"]) or any("perte d appetit" in x for x in associated)
    chills = _has(text, [r"frissons", r"tremble.*froid", r"froid.*chaud"])
    mosquito = _has(text, [r"moustique", r"moustiques", r"piqure.*moustique", r"palud", r"malaria"])

    digestive = _has(text, [r"diarrh", r"vomis", r"vomissement", r"selles liquides", r"selles aqueuses", r"gastro"]) or any("vomissements" in x or "diarrhee" in x for x in associated)
    watery_diarrhea = _has(text, [r"diarrhee aqueuse", r"selles aqueuses", r"selles liquides abondantes", r"eau de riz", r"diarrhee liquide", r"diarrhee tres frequente"])
    dehydration = _has(text, [r"bouche seche", r"soif intense", r"yeux creux", r"urine presque plus", r"urine tres peu", r"ne garde pas les liquides", r"vomis tout ce que je bois", r"tres faible", r"tres mou"])

    cough = _has(text, [r"\btoux\b", r"tousse", r"crachat", r"crache"])
    prolonged = _has(text, [r"plusieurs semaines", r"trois semaines", r"3 semaines", r"un mois", r"plus d un mois", r"depuis longtemps"])
    weight_loss = _has(text, [r"perte de poids", r"maigri", r"amaigr", r"minci"])
    night_sweats = _has(text, [r"sueurs nocturnes", r"transpire.*nuit", r"sueur.*nuit"])
    hemoptysis = _has(text, [r"crache du sang", r"sang dans les crachats", r"toux.*sang"])

    rash = _has(text, [r"eruption", r"boutons", r"plaques", r"taches", r"cloques", r"rougeurs"])
    red_eyes = _has(text, [r"yeux rouges", r"conjonctivite"])
    runny_nose = _has(text, [r"nez qui coule", r"rhume"])
    measles_possible = fever and rash and (cough or red_eyes or runny_nose)

    stiff_neck = _has(text, [r"nuque raide", r"cou raide", r"raideur.*nuque", r"raideur.*cou"])
    confusion = _has(text, [r"confus", r"confusion", r"delire", r"parle n importe", r"comportement bizarre"])
    convulsion = _has(text, [r"convulsion", r"crise", r"secousses", r"tremblements incontr"])
    severe_breathing = _has(text, [r"respire tres mal", r"n arrive pas a respirer", r"cherche l air", r"etouffe"])
    jaundice = _positive(text, [r"yeux jaunes", r"peau jaune", r"jaunisse"])
    # Saignement réel : ne pas considérer le mot isolé "sang" comme hémorragie.
    # Corrige les faux positifs : "mon sang fait mal", "pas de saignement".
    bleeding = (
        _positive(text, [r"saigne", r"saignement", r"vomit du sang", r"selles noires", r"crache du sang", r"saigne.*nez", r"genciv.*saign", r"saigne.*genciv"])
        and not _negated(text, [r"saigne", r"saignement", r"sang", r"genciv", r"nez"])
    )
    severe_weakness = _has(text, [r"tres faible", r"ne tient pas debout", r"impossible de se lever", r"somnolent", r"letharg"])

    pregnant = bool(payload.get("pregnant")) or _has(text, [r"enceinte", r"grossesse"])
    child_under_5 = age is not None and age < 5
    unable_child = _has(text, [r"enfant.*ne boit", r"ne boit plus", r"ne tete pas", r"refuse de boire", r"vomit tout"])
    lethargic_child = _has(text, [r"enfant.*somnol", r"enfant.*mou", r"enfant.*inconscient", r"ne reagit pas"])

    animal_bite = _has(text, [r"morsure", r"chien", r"serpent", r"scorpion"])
    snakebite = _has(text, [r"serpent", r"mordu.*serpent", r"morsure.*serpent"])
    dogbite = _has(text, [r"chien", r"mordu.*chien", r"morsure.*chien"])
    swelling_after_bite = animal_bite and _has(text, [r"gonfl", r"douleur", r"saigne", r"noir", r"engourdi"])

    malnutrition = _has(text, [r"maigreur", r"tres maigre", r"ventre gonfle", r"pieds gonfles", r"oedeme", r"malnutrition"])
    anemia = _has(text, [r"tres pale", r"paume pale", r"essouffle.*effort", r"vertige.*fatigue"])

    in_drc = province in DRC_PROVINCES
    malaria_endemic = in_drc or mosquito or _has(text, [r"zone palustre", r"paludisme", r"malaria"])
    waterborne_risk = province in HIGH_WATERBORNE_RISK_PROVINCES or _has(text, [r"cholera", r"eau sale", r"epidemie.*diarrh", r"quartier.*diarrh", r"cas de cholera"])

    tb_risk = _has(text, [r"contact.*tubercul", r"contact.*tb", r"prison", r"mine", r"camp", r"deplace", r"vih", r"immunodeprim", r"malnutrition"]) or any("tuberculose" in x or "vih" in x for x in history)

    malaria_probable = fever and malaria_endemic and (chills or headache or fatigue or appetite_loss or mosquito)
    severe_malaria_possible = malaria_probable and (confusion or convulsion or severe_breathing or jaundice or bleeding or severe_weakness)
    cholera_possible = watery_diarrhea and (waterborne_risk or _has(text, [r"cholera", r"epidemie"]))
    severe_cholera_possible = cholera_possible and dehydration
    tb_possible = cough and (prolonged or weight_loss or night_sweats or hemoptysis or tb_risk)
    meningitis_possible = fever and (stiff_neck or (headache and confusion))
    typhoid_possible = fever and _has(text, [r"douleur.*ventre", r"mal.*ventre", r"constipation", r"diarrh"]) and _has(text, [r"eau sale", r"mange.*dehors", r"plusieurs jours", r"une semaine"])
    cluster_or_exposure = _has(text, [r"contact", r"voisin.*meme", r"voisine.*meme", r"memes symptomes", r"chauve souris", r"brousse", r"epidemie"])
    # Fièvre hémorragique : jamais sur fièvre seule ; exiger saignement réel ou ictère + exposition/cluster.
    viral_hemorrhagic_warning = fever and (bleeding or jaundice) and cluster_or_exposure

    return locals()


def _set_priority(result: Any, priority: str, message: str, reason: str, domain: str, entry: str) -> Any:
    if _rank(priority) >= _rank(result.priority_code):
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
            result.score_breakdown = ["V3.7 Africa context-aware : override P1"]
    return result


def apply_africa_context(result: Any, sig: Dict[str, Any]) -> Any:
    if result.priority_code == "P1":
        return result

    p1_rules = [
        ("severe_malaria_possible", "Paludisme grave possible : signes de gravité associés à une fièvre en zone à risque. Rendez-vous immédiatement aux urgences.", "V3.7 Afrique: paludisme grave possible => P1", "infectieux", "AFR_MALARIA_SEVERE_P1"),
        ("severe_cholera_possible", "Diarrhée aqueuse avec signes de déshydratation sévère : urgence. Rendez-vous immédiatement au centre de santé ou à l'hôpital.", "V3.7 Afrique: choléra/déshydratation sévère => P1", "digestif", "AFR_CHOLERA_SEVERE_P1"),
        ("meningitis_possible", "Fièvre avec raideur du cou ou confusion : méningite possible. Rendez-vous immédiatement aux urgences.", "V3.7 Afrique: méningite possible => P1", "infectieux", "AFR_MENINGITIS_P1"),
        ("viral_hemorrhagic_warning", "Fièvre avec saignement ou jaunisse en contexte à risque : urgence infectieuse. Rendez-vous immédiatement aux urgences.", "V3.7 Afrique: fièvre hémorragique/ictère à risque => P1", "infectieux", "AFR_HEMORRHAGIC_FEVER_WARNING_P1"),
    ]
    for key, msg, reason, domain, entry in p1_rules:
        if sig.get(key):
            return _set_priority(result, "P1", msg, reason, domain, entry)

    if sig.get("child_under_5") and (sig.get("unable_child") or sig.get("lethargic_child") or sig.get("convulsion")):
        return _set_priority(result, "P1", "Enfant avec signe général de danger. Rendez-vous immédiatement aux urgences.", "V3.7 Afrique: danger pédiatrique IMCI => P1", "pediatrie", "AFR_CHILD_DANGER_P1")

    if sig.get("snakebite") and (sig.get("severe_breathing") or sig.get("bleeding") or sig.get("severe_weakness")):
        return _set_priority(result, "P1", "Morsure de serpent avec signe de gravité possible. Rendez-vous immédiatement aux urgences.", "V3.7 Afrique: morsure serpent grave => P1", "toxicologie", "AFR_SNAKEBITE_SEVERE_P1")

    p2_rules = [
        ("malaria_probable", "Un paludisme est possible. Consultez rapidement pour un test de diagnostic rapide ou une goutte épaisse et une prise en charge adaptée.", "V3.7 Afrique: fièvre + contexte palustre/moustiques => P2", "infectieux", "AFR_MALARIA_PROBABLE_P2"),
        ("cholera_possible", "Diarrhée aiguë en contexte à risque hydrique/choléra : consultez rapidement et commencez la réhydratation orale si possible.", "V3.7 Afrique: diarrhée contexte hydrique/choléra => P2", "digestif", "AFR_CHOLERA_RISK_P2"),
        ("tb_possible", "Tuberculose possible devant la toux prolongée ou les signes généraux. Une évaluation médicale rapide et un test TB sont recommandés.", "V3.7 Afrique: tuberculose possible => P2", "respiratoire", "AFR_TB_SUSPECT_P2"),
        ("measles_possible", "Rougeole ou infection éruptive fébrile possible. Consultez rapidement, surtout chez l'enfant ou en contexte d'épidémie.", "V3.7 Afrique: rougeole/rash fébrile possible => P2", "dermatologique", "AFR_MEASLES_RASH_FEVER_P2"),
        ("typhoid_possible", "Fièvre typhoïde ou infection digestive systémique possible. Une évaluation médicale rapide est recommandée.", "V3.7 Afrique: typhoïde/infection digestive possible => P2", "infectieux", "AFR_TYPHOID_P2"),
    ]
    for key, msg, reason, domain, entry in p2_rules:
        if sig.get(key):
            return _set_priority(result, "P2", msg, reason, domain, entry)

    if sig.get("pregnant") and sig.get("fever"):
        return _set_priority(result, "P2", "Fièvre pendant la grossesse : une évaluation médicale rapide est recommandée.", "V3.7 Afrique: grossesse + fièvre => P2", "gyn_obs", "AFR_PREGNANCY_FEVER_P2")

    if sig.get("snakebite") or sig.get("dogbite") or (sig.get("animal_bite") and sig.get("swelling_after_bite")):
        return _set_priority(result, "P2", "Morsure ou piqûre potentiellement à risque : consultation rapide recommandée.", "V3.7 Afrique: morsure/piqûre à risque => P2", "toxicologie", "AFR_BITE_P2")

    if sig.get("child_under_5") and sig.get("fever"):
        return _set_priority(result, "P2", "Fièvre chez un enfant de moins de 5 ans en contexte africain : consultation rapide recommandée.", "V3.7 Afrique: enfant <5 ans + fièvre => P2", "pediatrie", "AFR_CHILD_FEVER_P2")

    if sig.get("malnutrition") or sig.get("anemia"):
        return _set_priority(result, "P2", "Signes possibles de malnutrition ou d'anémie significative. Une évaluation médicale rapide est recommandée.", "V3.7 Afrique: malnutrition/anémie possible => P2", "nutrition", "AFR_MALNUTRITION_ANEMIA_P2")

    if result.priority_code == "P4" and sig.get("fever") and sig.get("in_drc") and (sig.get("fatigue") or sig.get("headache") or sig.get("chills")):
        return _set_priority(result, "P3", "Fièvre en contexte africain : consultation recommandée si elle persiste, s'aggrave ou s'accompagne de nouveaux signes.", "V3.7 Afrique: fallback fièvre contexte africain => P3", "infectieux", "AFR_FEVER_CONTEXT_FALLBACK_P3")

    return result


def load_kb(path: str = base.KB_DEFAULT_PATH) -> Dict[str, Any]:
    return v36.load_kb(path)


def run_triage_v3_7_africa(payload: Dict[str, Any], kb: Dict[str, Any], dynamic_answers: Optional[Dict[str, Any]] = None):
    result = v36.run_triage_v3_6_calibrated(payload, kb, dynamic_answers=dynamic_answers)
    sig = extract_africa_signals(payload)
    return apply_africa_context(result, sig)


run_triage = run_triage_v3_7_africa


def interactive_cli() -> None:
    kb = load_kb()
    print("=" * 80)
    print("SERVICE DE TRIAGE - MODE INTERACTIF (MOTEUR V3.7 AFRICA CONTEXT-AWARE)")
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

    result = run_triage_v3_7_africa(payload, kb, dynamic_answers={})
    print("\n" + "=" * 80)
    print("RÉSULTAT FINAL")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    interactive_cli()
