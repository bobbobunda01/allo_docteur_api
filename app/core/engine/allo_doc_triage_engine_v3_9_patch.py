from __future__ import annotations

"""
allo_doc_triage_engine_v3_9_patch.py
-------------------------------------
PATCH V3.9 — Règles manquantes + corrections critiques

Ce fichier s'intègre dans le moteur V3.8 existant.
Il ajoute :

CORRECTIONS BUGS V3.8 :
  [FIX-1] Suppression print() de debug
  [FIX-2] Timer t0 local à chaque appel
  [FIX-3] respiratory_distress ne plus pollué par stroke_signs
  [FIX-4] cleanup_contradictions étendu à tous les domaines

NOUVELLES RÈGLES TRIAGE (13 lacunes identifiées) :
  [R01] Néonatal < 28 jours + fièvre/hypothermie → P1 absolu OMS
  [R02] Hémorragie digestive haute (hématémèse/méléna) → P1
  [R03] Morsure serpent / animal enragé → P1
  [R04] Ingestion toxique / empoisonnement → P1
  [R05] Traumatisme crânien avec perte de connaissance → P1
  [R06] Fièvre hémorragique virale (Ebola/Marburg RDC) → P1 isolement
  [R07] Crise drépanocytaire vasocclusive → P1/P2
  [R08] Grossesse extra-utérine suspectée → P1
  [R09] Brûlure grave → P1
  [R10] Éclampsie (convulsions + grossesse) → P1
  [R11] Acidocétose diabétique → P1
  [R12] Tirage sous-costal enfant / stridor → P1 (IMCI)
  [R13] Corps étranger voie aérienne enfant → P1

RÈGLES SUPPLÉMENTAIRES (au-delà des 13) :
  [R14] Perte de connaissance / syncope → P1
  [R15] Ictère (jaunisse) + fièvre → P1/P2
  [R16] Distension abdominale + arrêt matières → P1
  [R17] Fièvre post-partum (< 6 semaines) → P1/P2
  [R18] Rupture des membranes → P1
  [R19] Absence mouvements fœtaux → P1
  [R20] Anémie sévère (pâleur extrême) → P1/P2
  [R21] Rétention urinaire aiguë → P2
  [R22] Céphalée en coup de tonnerre → P1
  [R23] Hémorragie digestive basse → P2
  [R24] Psychose aiguë → P1/P2
  [R25] Sevrage alcool avec agitation/convulsions → P1
  [R26] Palpitations + malaise → P2
  [R27] Signe IMCI : enfant ne boit plus + pâleur → P1
  [R28] Paludisme grave (avec signe de danger) → P1 renforcé
  [R29] Malnutrition sévère avec complication → P1
  [R30] Signe méningite chez nourrisson → P1

MODE D'INTÉGRATION :
    Remplacer apply_v38_corrections() par apply_v39_corrections()
    dans run_triage_v3_8_production() :

    def run_triage_v3_8_production(payload, kb, dynamic_answers=None):
        result = v37.run_triage_v3_7_africa(payload, kb, dynamic_answers=dynamic_answers or {})
        result = apply_v39_corrections(result, payload)   # ← V3.9
        enrich_dynamic_questions(result, extract_v38_signals(payload))
        return result
"""

from typing import Any, Dict, List, Optional
import re
import time

# ============================================================
# UTILITAIRES (repris du moteur V3.8 pour cohérence)
# ============================================================

def _p(priority: str) -> int:
    return {"P1": 4, "P2": 3, "P3": 2, "P4": 1}.get(priority, 0)


def _set(result, priority, message, reason, domain=None, entry=None, allow_downgrade=False):
    """set_result local — même logique que V3.8."""
    from allo_doc_triage_engine_v3_8_production_CONSOLIDATED import set_result
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
    from allo_doc_triage_engine_v3_8_production_CONSOLIDATED import (
        extract_v38_signals, norm, detect_positive, has_any, _age_from_dob
    )

    t0_local = time.time()  # [FIX-2] timer local

    # Récupérer tous les signaux V3.8
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

    neonatal = (age_days is not None and age_days <= 28) or bool(nlp.get("neonatal_danger"))

    # ── Signaux spécifiques V3.9 ─────────────────────────────────────────

    # [R01] Néonatal
    s["neonatal"] = neonatal
    s["neonatal_fever"] = neonatal and (s.get("fever") or _has(text, [r"chaud", r"fievre"]))
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

    # Temps d'extraction V3.9
    s["v39_elapsed_seconds"] = round(time.time() - t0_local, 4)

    return s

# ============================================================
# [FIX-4] CLEANUP CONTRADICTIONS ÉTENDU
# ============================================================

def cleanup_contradictions_v39(result: Any, s: Dict[str, Any]) -> None:
    """
    Étend cleanup_contradictions() à tous les domaines.
    V3.8 ne nettoyait que fever, digestive, dental.
    """
    from allo_doc_triage_engine_v3_8_production_CONSOLIDATED import (
        cleanup_contradictions, remove_items_containing
    )

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
    from allo_doc_triage_engine_v3_8_production_CONSOLIDATED import (
        apply_v38_corrections, sync_result_fields, cleanup_contradictions
    )

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

def apply_v39_corrections(result: Any, payload: Dict[str, Any]) -> Any:
    """
    Point d'entrée principal V3.9.
    Remplace apply_v38_corrections() dans run_triage_v3_8_production().
    """
    return apply_v39_rules(result, payload)


# ============================================================
# INTÉGRATION : MONKEY-PATCH run_triage pour utiliser V3.9
# ============================================================

def patch_engine_v39() -> None:
    """
    Applique le patch V3.9 sur le moteur importé.
    Appeler une seule fois au démarrage de l'application.

    Usage :
        from allo_doc_triage_engine_v3_9_patch import patch_engine_v39
        patch_engine_v39()
        from allo_doc_triage_engine_v3_8_production_CONSOLIDATED import run_triage
        result = run_triage(payload, kb)
    """
    import allo_doc_triage_engine_v3_8_production_CONSOLIDATED as engine_v38

    original_run = engine_v38.run_triage_v3_8_production

    def run_triage_v39(payload, kb, dynamic_answers=None):
        import allo_doc_triage_engine_v3_7_africa as v37
        result = v37.run_triage_v3_7_africa(payload, kb, dynamic_answers=dynamic_answers or {})
        result = apply_v39_corrections(result, payload)
        from allo_doc_triage_engine_v3_8_production_CONSOLIDATED import enrich_dynamic_questions
        enrich_dynamic_questions(result, extract_v39_signals(payload))
        return result

    engine_v38.run_triage_v3_8_production = run_triage_v39
    engine_v38.run_triage = run_triage_v39
    print("[AlloDocteur] Moteur V3.9 activé — 30 nouvelles règles de triage opérationnelles.")
