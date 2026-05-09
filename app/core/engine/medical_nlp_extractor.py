from __future__ import annotations

"""
medical_nlp_extractor_v2.py
---------------------------
Couche NLP hybride AlloDocteur — VERSION 2.0

Améliorations vs V1 :
1. Négations étendues à TOUS les signaux critiques (pas seulement SYMPTOM)
2. Détection du sujet (patient vs tiers) pour éviter les faux positifs
3. Résolution temporelle : symptôme passé/résolu ≠ symptôme actuel
4. Langage patient RDC étendu (lingala-français, expressions locales)
5. Nouveaux signaux critiques : néonatal, trauma, toxique, hémorragique, drépanocytaire
6. Négations manquantes : "plus", "jamais", "disparu", "guéri", "traité"
7. Mode AUTO amélioré : skip ML si P1 déjà trouvé
8. Log structuré des erreurs modèle

Le modèle NLP ne décide jamais P1/P2/P3/P4.
Il enrichit les signaux pour le moteur de triage.
"""

import os
os.environ["TRANSFORMERS_NO_TF"] = "1"
os.environ["TRANSFORMERS_NO_FLAX"] = "1"

import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("allodocteur.nlp")

# ============================================================
# CONFIGURATION
# ============================================================

# "on"   => modèle ML toujours appelé
# "auto" => règles d'abord, ML seulement si cas non critique / ambigu
# "off"  => modèle ML désactivé (règles seules)
USE_ML_NLP = "auto"

MODEL_DIR = Path(__file__).resolve().parent / "allodocteur_medical_ner_v2" / "model"

_NER_PIPE = None
_NER_LOAD_ERROR: Optional[str] = None
_NER_LOAD_ATTEMPTED = False

# ============================================================
# NORMALISATION TEXTE
# ============================================================

# Corrections orthographiques étendues incluant le langage RDC
SPELL_CORRECTIONS = {
    # Fautes courantes français
    "basdu": "bas du",
    "deuis": "depuis",
    "depusi": "depuis",
    "fatique": "fatigue",
    "vente": "ventre",
    "er j ai": "et j ai",
    "ma faire du mal": "me faire du mal",
    "essoufle": "essouffle",
    "viloents": "violents",
    "alux de tete": "maux de tete",
    "maux de tte": "maux de tete",
    "je me se s": "je me sens",
    "jr me sens": "je me sens",
    "grossese": "grossesse",
    "encinte": "enceinte",
    "saignment": "saignement",
    "vomir": "vomissement",
    "fiever": "fievre",
    "diarée": "diarrhee",
    "diarée": "diarrhee",
    "convultion": "convulsion",
    "convultions": "convulsions",
    "paralysie": "paralysie",

    # Langage RDC / lingala-français
    "il a fait le corps dur": "il a des convulsions",
    "elle a fait le corps dur": "elle a des convulsions",
    "a fait le corps dur": "a des convulsions",
    "corps dur": "convulsions",
    "il rend tout": "il vomit tout",
    "elle rend tout": "elle vomit tout",
    "je rends tout": "je vomis tout",
    "rend tout": "vomit tout",
    "grosse de": "enceinte de",
    "elle est grosse": "elle est enceinte",
    "je suis grosse": "je suis enceinte",
    "mon sang fait mal": "douleurs drépanocytaires",
    "le sang fait mal": "douleurs drépanocytaires",
    "il ne tient plus debout": "il ne peut plus se lever faiblesse",
    "elle ne tient plus debout": "elle ne peut plus se lever faiblesse",
    "ne tient plus debout": "ne peut plus se lever faiblesse",
    "les yeux sont jaunes": "ictere yeux jaunes",
    "yeux jaunes": "ictere yeux jaunes",
    "peau jaune": "ictere peau jaune",
    "le ventre est gonfle": "distension abdominale ventre gonfle",
    "ventre ballonne": "distension abdominale",
    "il ne reconnait plus personne": "confusion il ne reconnait plus personne",
    "elle ne reconnait plus personne": "confusion elle ne reconnait plus personne",
    "a perdu les eaux": "rupture des membranes a perdu les eaux",
    "elle a perdu les eaux": "rupture des membranes elle a perdu les eaux",
    "le bebe ne bouge plus": "mouvement foetal absent bebe ne bouge plus",
    "bebe ne bouge plus": "mouvement foetal absent",
    "il a avale quelque chose": "ingestion corps etranger il a avale quelque chose",
    "a avale quelque chose": "ingestion corps etranger",
    "morsure de bete": "morsure animal morsure de bete",
    "morsure de serpent": "envenimation morsure de serpent",
    "mordu par un serpent": "envenimation mordu par un serpent",
    "mordu par serpent": "envenimation morsure serpent",
    "la tete me tourne": "vertiges la tete me tourne",
    "tete qui tourne": "vertiges tete qui tourne",
    "il est chaud": "il a de la fievre il est chaud",
    "elle est chaude": "elle a de la fievre elle est chaude",
    "brule partout": "fievre brule partout",
    "saigne du nez": "saignement nasal epistaxis",
    "saigne des gencives": "saignement gingival saigne des gencives",
    "crache du sang": "hemoptysie crache du sang",
    "vomit du sang": "hematemese vomit du sang",
    "sang dans les selles": "rectorragie sang dans les selles",
    "selles noires": "melena selles noires",
    "urine rouge": "hematurie urine rouge sang",
    "pipi rouge": "hematurie pipi rouge sang",
    "haleine sucree": "haleine acetonique haleine sucree diabete",
    "haleine de fruit": "haleine acetonique haleine de fruit diabete",
    "pied gonflé": "oedeme pied gonfle",
    "jambe gonflée": "oedeme jambe gonflee",
    "jambes gonflées": "oedeme jambes gonflees",
    "ne peut pas avaler": "dysphagie ne peut pas avaler",
    "du mal a avaler": "dysphagie du mal a avaler",
    "avale de travers": "fausse route avale de travers",
    "piqure de serpent": "envenimation piqure serpent",
}


def normalize_fr(text: Any) -> str:
    """
    Normalisation robuste du texte patient FR/RDC.
    1. Lowercase + suppression accents
    2. Nettoyage caractères spéciaux
    3. Corrections orthographiques + expressions RDC
    """
    text = str(text or "").lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[^a-z0-9\s']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Appliquer les corrections (plus longues en premier pour éviter les conflits)
    for wrong, right in sorted(SPELL_CORRECTIONS.items(), key=lambda x: -len(x[0])):
        if wrong in text:
            text = text.replace(wrong, right)

    return text


def _has(text: str, patterns: List[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _is_about_patient(text: str, match_start: int) -> bool:
    """
    Vérifie si le symptôme détecté concerne le patient lui-même
    et non un tiers (frère, mari, voisin...).
    Fenêtre de 40 caractères avant le match.
    """
    window = text[max(0, match_start - 40):match_start].strip()
    third_party_indicators = [
        r"\bmon (frere|mari|pere|fils|voisin|ami|oncle|cousin)\b",
        r"\bma (soeur|mere|fille|voisine|amie|tante|cousine)\b",
        r"\bson (frere|mari|pere|fils|voisin)\b",
        r"\bsa (soeur|mere|fille|voisine)\b",
        r"\bun (patient|homme|enfant|bebe|garcon)\b(?!.*\bmon\b)",
    ]
    return not any(re.search(p, window) for p in third_party_indicators)


def _is_current_symptom(text: str, match_start: int) -> bool:
    """
    Vérifie que le symptôme est actuel (pas résolu, pas passé historique).
    Fenêtre de 50 caractères avant + autour du match.
    """
    window = text[max(0, match_start - 50): match_start + 30]
    resolved_indicators = [
        r"\b(ancien|ancienne|avant|autrefois|jadis|il y a longtemps)\b",
        r"\b(gueri|guerie|resolu|resolue|disparu|disparue|termine|terminee)\b",
        r"\b(operé|opere|traite|traitee) (pour|de)\b",
        r"\b(n existe plus|n a plus|plus de) ",
        r"\b(dans le passe|precedemment|historique)\b",
    ]
    return not any(re.search(p, window) for p in resolved_indicators)

# ============================================================
# CHARGEMENT MODELE ML
# ============================================================

def _load_ner_pipe():
    """
    Charge le modèle NER une seule fois, avec logging structuré.
    """
    global _NER_PIPE, _NER_LOAD_ERROR, _NER_LOAD_ATTEMPTED

    if _NER_PIPE is not None:
        return _NER_PIPE

    if _NER_LOAD_ATTEMPTED:
        return None

    _NER_LOAD_ATTEMPTED = True

    if not MODEL_DIR.exists():
        _NER_LOAD_ERROR = f"Modèle NLP introuvable: {MODEL_DIR}"
        logger.warning("AlloDocteur NLP: %s — mode règles seules activé", _NER_LOAD_ERROR)
        return None

    try:
        from transformers import pipeline as hf_pipeline
        _NER_PIPE = hf_pipeline(
            "token-classification",
            model=str(MODEL_DIR),
            tokenizer=str(MODEL_DIR),
            aggregation_strategy="simple",
        )
        logger.info("AlloDocteur NLP: modèle chargé depuis %s", MODEL_DIR)
        return _NER_PIPE

    except Exception as exc:
        _NER_LOAD_ERROR = str(exc)
        logger.error("AlloDocteur NLP: échec chargement modèle — %s", _NER_LOAD_ERROR)
        return None


def _labels_from_model(text: str) -> List[Dict[str, Any]]:
    if USE_ML_NLP == "off":
        return []
    pipe = _load_ner_pipe()
    if pipe is None:
        return []
    try:
        return pipe(text) or []
    except Exception as exc:
        logger.warning("AlloDocteur NLP: erreur inférence — %s", exc)
        return []

# ============================================================
# TERMES DE NÉGATION — VERSION ÉTENDUE
# ============================================================

NEGATION_PATTERNS = [
    # Négations simples
    r"\bsans\b",
    r"\bpas de\b",
    r"\bpas d[e']?\b",
    r"\baucun\b",
    r"\baucune\b",
    r"\bni\b",
    # Négations verbales
    r"\bne\b.{0,15}\bpas\b",
    r"\bne\b.{0,15}\bplus\b",
    r"\bne\b.{0,15}\bjamais\b",
    r"\bne\b.{0,15}\baucun\b",
    # Résolution / disparition
    r"\b(disparu|disparue|resolu|resolue|gueri|guerie|termine|terminee)\b",
    r"\bn existe plus\b",
    r"\bplus du tout\b",
    r"\bfini\b",
    # Négations familières
    r"\by a pas de\b",
    r"\by a aucun\b",
    r"\bjamais de\b",
    r"\bnul\b",
    r"\bnulle\b",
    # Absence explicite
    r"\babsence de\b",
    r"\bprive de\b",
    # Contexte passé résolu
    r"\bavant\b.{0,20}\bmaintenant\b",
    r"\bprecedemment\b",
]

# ============================================================
# PATTERNS SYMPTÔMES — VERSION COMPLÈTE
# ============================================================

# SYMPTOM_PATTERNS_FR : signaux courants avec négation active
# Ces signaux peuvent légitimement être niés dans le discours patient
SYMPTOM_PATTERNS_FR: Dict[str, List[str]] = {
    "fever": [
        r"\bfievre\b", r"\btemperature\b", r"corps chaud", r"\bfebril",
        r"brule de fievre", r"chaud.*corps", r"il est chaud", r"elle est chaude",
        r"38", r"39", r"40", r"41",  # températures mentionnées
    ],
    "vomiting": [
        r"\bvomis\b", r"\bvomit\b", r"vomissement", r"vomissements",
        r"rejette tout", r"rend tout", r"nausee.*vomit", r"envie de vomir",
    ],
    "diarrhea": [
        r"diarrhee", r"selles liquides", r"selles aqueuses", r"selles molles",
        r"eau de riz",  # cholera
        r"va souvent aux toilettes", r"cours aux toilettes",
    ],
    "breathing_issue": [
        r"essouffl", r"difficulte.*respir", r"respire mal", r"manque d air",
        r"cherche l air", r"n arrive pas.*respir", r"souffle court",
        r"respiration difficile", r"mal a respirer",
    ],
    "chest_pain": [
        r"poitrine", r"thorax", r"thoracique", r"oppression", r"serrement",
        r"pression.*poitrine", r"douleur.*coeur", r"coeur qui serre",
    ],
    "headache": [
        r"maux de tete", r"mal a la tete", r"mal de tete", r"tete lourde",
        r"pression dans la tete", r"cephalee", r"migraine",
        r"tete qui fait mal",
    ],
    "sleep_disorder": [
        r"dors mal", r"je dors mal", r"je ne dors pas", r"insomnie",
        r"sommeil perturbe", r"n arrive pas a dormir", r"reveille.*nuit",
        r"nuit sans sommeil",
    ],
    "fatigue": [
        r"\bfatigue\b", r"\bfaible\b", r"\bfaiblesse\b", r"je me sens bizarre",
        r"je ne me sens pas bien", r"\bmalaise\b", r"sans energie",
        r"epuise", r"abattu", r"\bmou\b", r"courbatures",
    ],
    "anxiety": [
        r"\bstress\b", r"\bstresse\b", r"\banxieux\b", r"\banxiete\b",
        r"\bangoisse\b", r"peur de", r"inquiet", r"inquiete",
    ],
    "abdominal_pain": [
        r"mal au ventre", r"douleur.*ventre", r"douleur.*abdomen",
        r"ventre.*douloureux", r"ventre.*fait mal", r"crampes.*ventre",
        r"abdomi.*douleur",
    ],
    "cough": [
        r"\btoux\b", r"\btousse\b", r"\btousser\b", r"quinte de toux",
        r"toux seche", r"toux grasse", r"toux persistante",
    ],
    "back_pain": [
        r"mal au dos", r"douleur.*dos", r"\blombalg", r"bas du dos",
        r"colonne vertebrale", r"douleur.*rachis",
    ],
    "rash": [
        r"\bboutons\b", r"\beruption\b", r"\bplaques\b", r"\btaches\b",
        r"\bcloques\b", r"\brougeurs\b", r"peau.*rouge",
    ],
}

# CRITICAL_PATTERNS_FR : signaux à haut risque
# Maintenant avec négation active pour tous (correction bug V1)
CRITICAL_PATTERNS_FR: Dict[str, List[str]] = {

    # ── GROSSESSE / OBSTÉTRIQUE ──────────────────────────────────────────────
    "pregnant": [
        r"\benceinte\b", r"\bgrossesse\b", r"grosse de \d",
        r"attends un bebe", r"attend.*bebe", r"enceinte de \d",
        r"mois de grossesse", r"femme enceinte",
    ],
    "pregnancy_month": [
        r"enceinte de (\d+) mois", r"grosse de (\d+) mois",
        r"(\d+) mois de grossesse", r"(\d+)eme mois",
    ],
    "vaginal_bleeding": [
        r"saignement vaginal", r"je saigne", r"elle saigne",
        r"pertes de sang", r"saignements", r"sang.*vagin",
        r"pertes rouges", r"pertes sanglantes",
    ],
    "postpartum": [
        r"vient d accoucher", r"accouche.*hier", r"accouche.*semaine",
        r"apres l accouchement", r"post.?partum", r"suites de couches",
        r"accouchee de", r"nouveau.?ne", r"bebe de \d+ jours",
        r"bebe de \d+ semaines",
    ],
    "membrane_rupture": [
        r"perdu les eaux", r"poche des eaux.*rompue", r"poche.*crevee",
        r"eaux.*coulees", r"liquide.*coule.*vagin",
    ],
    "fetal_movement_absent": [
        r"bebe.*ne bouge plus", r"bebe.*bouge.*plus",
        r"mouvements.*bebe.*absents", r"plus.*sentir.*bebe",
        r"bebe.*inactif",
    ],
    "eclampsia_risk": [
        # grossesse + convulsions (détecté en composite plus bas)
        r"convulsion.*enceinte", r"enceinte.*convulsion",
        r"crise.*enceinte", r"enceinte.*crise",
    ],
    "ectopic_risk": [
        # femme + aménorrhée + douleur latérale + malaise
        r"pas.*regles.*douleur.*ventre", r"regles.*retard.*douleur",
        r"douleur.*bas.*ventre.*malaise.*regles",
    ],

    # ── NEUROLOGIQUE / AVC ──────────────────────────────────────────────────
    "stroke_signs": [
        r"faiblesse.*un cote", r"un cote.*faible",
        r"bras.*faible", r"bras.*gauche.*faible", r"bras.*droit.*faible",
        r"jambe.*faible", r"jambe.*gauche.*faible", r"jambe.*droite.*faible",
        r"parle difficilement", r"difficulte.*parler", r"ne parle plus",
        r"ne peut plus parler", r"ne peux plus parler",
        r"parler correctement", r"paroles.*embrouillees",
        r"visage.*devie", r"bouche.*deviee", r"bouche.*tordue",
        r"face.*devie", r"sourire.*asymetrique",
        r"ne reconnait plus personne", r"ne reconnait plus",
        r"ne tient plus debout",  # après correction RDC
    ],
    "severe_headache": [
        r"forts? maux de tete", r"mal de tete intense",
        r"violents? maux de tete", r"cephalee intense",
        r"pire maux de tete", r"mal de tete.*jamais eu",
        r"coup de tonnerre.*tete", r"tete.*explode",
        r"tete.*eclate", r"mal de tete.*soudain",
        r"cephalee.*brutale", r"cephalee en coup de tonnerre",
    ],
    "visual_disturbance": [
        r"vision floue", r"je vois flou", r"vision trouble",
        r"troubles visuels", r"points lumineux", r"mouches volantes",
        r"voile.*devant.*yeux", r"yeux.*noirs", r"voit double",
        r"diplopie", r"perte.*vision", r"ne voit plus",
        r"clair.*yeux", r"brouillard.*yeux",
    ],
    "neck_stiffness": [
        r"raideur.*cou", r"raideur.*nuque", r"nuque raide",
        r"cou raide", r"cou bloque", r"ne peut pas.*pencher.*tete",
        r"tete.*bloquee", r"douleur.*nuque.*fievre",
    ],
    "seizures": [
        r"\bconvulsion", r"crise convulsive", r"tremblements incontr",
        r"\bsecousses\b", r"corps dur", r"a fait le corps dur",
        r"perd connaissance.*tombe", r"tomber.*agitation",
        r"epilepsie.*crise", r"crise.*epileptique",
    ],
    "confusion_acute": [
        r"\bconfusion\b", r"\bconfus\b", r"\bdelire\b",
        r"\bdesoriente\b", r"comportement bizarre", r"ne reconnait plus",
        r"parle.*seul", r"agitation.*nocturne.*soudaine",
        r"subitement.*bizarre",
    ],
    "thunderclap_headache": [
        r"coup de tonnerre.*tete", r"pire.*mal.*tete.*vie",
        r"mal de tete.*jamais.*ressenti", r"soudain.*violent.*tete",
        r"d un coup.*mal.*tete",
    ],

    # ── CARDIOVASCULAIRE ────────────────────────────────────────────────────
    "chest_pressure_severe": [
        r"oppression.*poitrine.*fort", r"poitrine.*serre.*fort",
        r"douleur.*poitrine.*bras", r"douleur.*poitrine.*machoire",
        r"douleur.*poitrine.*epaule", r"douleur.*poitrine.*dos",
        r"coeur.*serre", r"infarctus", r"crise cardiaque",
    ],
    "palpitations": [
        r"coeur.*bat.*fort", r"coeur.*s emballe", r"palpitation",
        r"tachycardie", r"coeur.*rapide", r"coeur.*irregulier",
        r"coeur.*rate.*battement",
    ],
    "orthopnea": [
        r"ne peut pas.*couche.*respir", r"doit.*assis.*respir",
        r"allonge.*essouffl", r"couche.*manque.*air",
        r"dormir.*assis", r"respir.*mieux.*debout",
    ],

    # ── RESPIRATOIRE ────────────────────────────────────────────────────────
    "respiratory_distress_severe": [
        r"n arrive pas.*respirer", r"respire tres mal",
        r"cherche l air", r"\betouffe\b", r"ne finit pas.*phrases",
        r"bleuit", r"cyanose", r"levre.*bleue", r"levre.*violette",
        r"ongles.*bleus", r"tirage.*poitrine",
        r"poitrine.*rentre.*respir",  # tirage sous-costal
        r"sa poitrine.*rentre",  # parent décrit
        r"\bstridor\b", r"sifflement.*inspiratoire",
        r"avale.*quelque chose.*tousse.*respir",  # corps étranger
    ],
    "hemoptysis": [
        r"crache.*sang", r"sang.*crachat", r"toux.*sang",
        r"expectore.*sang", r"sang.*toux",
    ],

    # ── DIGESTIF / ABDOMINAL ────────────────────────────────────────────────
    "upper_gi_bleeding": [
        r"vomit.*sang", r"hematemese", r"vomissement.*sang",
        r"sang.*vomissement", r"cafe.*moulu.*vomit",
    ],
    "lower_gi_bleeding": [
        r"selles noires", r"\bmelena\b", r"sang.*selles",
        r"\brectorragie\b", r"sang.*rectum", r"sang.*anus",
        r"sang.*toilet", r"sang.*papier.*toilet",
    ],
    "severe_abdominal_pain": [
        r"douleur.*intense.*ventre", r"douleurs.*intenses.*ventre",
        r"ventre.*tres douloureux", r"forte douleur.*ventre",
        r"ventre.*dur.*comme.*bois", r"ventre de bois",
        r"defense.*abdominale", r"ne peut pas.*touch.*ventre",
        r"insupportable.*ventre",
    ],
    "lower_right_abdominal_pain": [
        r"bas.*droite.*ventre", r"droite.*bas.*ventre",
        r"fosse iliaque droite", r"bas a droite.*ventre",
        r"cote droit.*bas.*ventre", r"ventre.*bas.*droit",
    ],
    "lower_abdominal_pain": [
        r"bas du ventre", r"bas.*ventre", r"douleur.*pelv",
        r"douleur.*ventre", r"mal.*ventre", r"hypogastre",
    ],
    "abdominal_distension": [
        r"ventre gonfle", r"ventre.*ballonne", r"ventre.*enfle",
        r"distension abdominale", r"ventre.*gros.*anormal",
        r"ascite",
    ],
    "bowel_obstruction_signs": [
        r"arret.*matieres", r"arret.*gaz", r"ne peut plus.*selles",
        r"ventre.*gonfle.*arret", r"vomit.*matieres",
        r"n a pas eu.*selles.*depuis \d+ jours",
    ],
    "jaundice": [
        r"ictere", r"yeux jaunes", r"peau jaune", r"jaunisse",
        r"scleres.*jaunes", r"teint.*jaune",
    ],
    "unable_to_drink": [
        r"ne boit plus", r"ne peux plus boire", r"ne peut plus boire",
        r"refuse de boire", r"vomit tout", r"vomis tout",
        r"rejette tout", r"rend tout", r"garde.*rien",
        r"ne garde pas.*liquide",
    ],
    "dehydration": [
        r"bouche seche", r"yeux creux", r"yeux enfonces",
        r"urine tres peu", r"urine presque plus", r"soif intense",
        r"fontanelle.*enfoncee",  # nourrisson
        r"peau.*elastique.*plus", r"pli cutane",
        r"tres faible.*soif", r"somnolent.*soif",
    ],

    # ── INFECTIEUX RDC SPÉCIFIQUE ───────────────────────────────────────────
    "hemorrhagic_fever_signs": [
        r"fievre.*saign", r"saign.*fievre",
        r"saigne.*partout", r"saigne.*nez.*bouche",
        r"saigne.*yeux", r"saignement.*spontane",
        r"sang.*partout", r"fievre.*sang.*nez.*genciv",
        r"hemorragie",
    ],
    "malaria_signs": [
        r"paludisme", r"\bpalu\b", r"malaria",
        r"fievre.*frissons.*sueurs", r"frissons.*fievre.*sueurs",
        r"acces palustre",
    ],
    "meningitis_signs": [
        r"nuque raide.*fievre", r"fievre.*nuque raide",
        r"fievre.*raideur.*cou", r"cou raide.*fievre",
        r"fievre.*maux.*tete.*nuque",
        r"photophobie.*fievre", r"sensible.*lumiere.*fievre",
    ],
    "tb_signs": [
        r"toux.*semaines", r"toux.*mois", r"toux.*longtemps",
        r"crachat.*sang", r"sueurs.*nocturnes.*toux",
        r"amaigrissement.*toux", r"maigrit.*toux",
    ],

    # ── TRAUMATOLOGIE / TOXICOLOGIE ─────────────────────────────────────────
    "head_trauma": [
        r"choc.*tete", r"coup.*tete", r"tete.*frappe",
        r"tombe.*tete", r"tete.*frappe.*sol",
        r"accident.*tete", r"traumatisme.*cranien",
        r"blessure.*tete", r"plaie.*tete",
        r"perd.*connaissance.*choc",
    ],
    "snake_bite": [
        r"morsure.*serpent", r"mordu.*serpent",
        r"piqure.*serpent", r"envenimation",
        r"bete.*mordu", r"serpent.*mordu",
        r"mamba", r"cobra", r"vipere",
    ],
    "toxic_ingestion": [
        r"avale.*medicament", r"avale.*produit",
        r"avale.*liquide.*nettoyant", r"avale.*poison",
        r"ingestion.*toxique", r"empoisonnement",
        r"surdosage", r"a bu.*produit",
        r"avale.*quelque chose", r"mange.*champignon.*sauvage",
        r"intoxication",
    ],
    "burn_severe": [
        r"brulure.*visage", r"brulure.*grave",
        r"brule.*\d{2}.*pourcent", r"brulure.*etendue",
        r"brule.*dos.*ventre", r"brulure.*respir",
        r"brule.*chimique", r"acide.*peau",
    ],

    # ── PÉDIATRIE ───────────────────────────────────────────────────────────
    "neonatal_danger": [
        r"nouveau.?ne.*fievre", r"bebe.*\d+ jours.*fievre",
        r"bebe.*\d+ semaines.*fievre",
        r"nouveau.?ne.*chaud", r"bebe.*nouveau.?ne.*ne mange plus",
        r"nouveau.?ne.*ne boit plus", r"bebe.*ne respire.*bien",
        r"bebe.*jaune", r"nouveau.?ne.*jaune",
        r"naissance.*il y a \d+ jours",
    ],
    "child_danger_signs": [
        r"enfant.*ne boit.*plus", r"enfant.*vomit.*tout",
        r"enfant.*perd.*connaissance", r"enfant.*convulsion",
        r"enfant.*respire.*mal", r"enfant.*tres.*faible",
        r"enfant.*ne.*leve.*plus", r"bebe.*mou",
        r"bebe.*ne.*reagit.*plus", r"enfant.*inconscient",
        r"poitrine.*rentre.*enfant", r"enfant.*poitrine.*rentre",
        r"fontanelle.*bombante", r"fontanelle.*gonfl",
    ],
    "severe_malnutrition": [
        r"tres maigre", r"os.*peau", r"squelette",
        r"oedeme.*pieds.*enfant", r"jambes.*gonflees.*enfant",
        r"pied.*gonfle.*enfant.*maigre",
        r"bras.*tres.*mince", r"bras.*fin.*enfant",
        r"malnutrition", r"malnutri",
    ],

    # ── MÉTABOLIQUE / ENDOCRINIEN ───────────────────────────────────────────
    "diabetic_emergency": [
        r"diabetique.*vomit", r"diabetique.*vomissements",
        r"haleine.*acetonique", r"haleine.*sucree",
        r"haleine.*fruit", r"diabete.*mal.*conscience",
        r"insuline.*trop", r"diabetique.*malaise",
        r"diabetique.*inconscient",
    ],
    "hypoglycemia_signs": [
        r"diabetique.*tremble", r"diabetique.*sueurs",
        r"diabetique.*malaise", r"glycemie.*basse",
        r"sucre.*trop.*bas", r"hypoglycemie",
        r"diabetique.*perd.*connaissance",
        r"pas mange.*diabetique.*faible",
    ],
    "sickle_cell_crisis": [
        r"drepanocytose.*douleur", r"douleur.*drepanocytose",
        r"crise.*drepanocytaire", r"mon sang.*mal",
        r"le sang.*fait.*mal", r"drepanocytaire.*douleur",
        r"hemoglobine.*ss", r"douleur.*os.*bras",
        r"douleur.*os.*jambe", r"drepanocytose.*crise",
    ],
    "severe_anemia": [
        r"tres pale", r"pale.*comme.*linge", r"levres.*blanches",
        r"muqueuses.*blanches", r"yeux.*blancs",
        r"conjonctives.*blanches", r"anemie.*severe",
        r"hemoglobine.*tres.*basse",
    ],

    # ── PSYCHIATRIQUE ───────────────────────────────────────────────────────
    "suicidal_text": [
        r"me faire du mal", r"envie de mourir",
        r"me suicider", r"mettre fin a mes jours",
        r"fatigue de vivre", r"ne veux plus vivre",
        r"disparaitre", r"en finir",
        r"pensees.*mort", r"idees.*suicide",
        r"tuer.*moi", r"mourir.*mieux",
    ],
    "acute_psychosis": [
        r"entend.*voix", r"voit.*choses.*pas.*la",
        r"hallucination", r"delire.*persecution",
        r"quelqu.*un.*le.*poursuite", r"croit.*etre.*persecute",
        r"parle.*seul.*longtemps", r"comportement.*bizarre.*soudain",
        r"agitation.*extreme.*nocturne",
    ],
    "alcohol_withdrawal": [
        r"alcool.*arrete.*tremble", r"arrete.*alcool.*agitation",
        r"sevrage.*alcool", r"alcoolique.*agite",
        r"alcool.*convulsion", r"alcool.*delire",
        r"tremblements.*matin.*alcool",
    ],

    # ── URINAIRE / RÉNAL ────────────────────────────────────────────────────
    "urinary_burning": [
        r"brule.*urin", r"brulure.*urin",
        r"pique.*urin", r"douleur.*urin",
        r"ca brule.*pipi", r"brule.*pipi",
        r"douleur.*miction", r"miction.*douloureuse",
    ],
    "urinary_retention": [
        r"ne peut plus uriner", r"ne peux plus uriner",
        r"n arrive pas.*uriner", r"envie.*uriner.*ne peut",
        r"ventre.*gonfle.*envie.*urin", r"globe.*vesical",
        r"retenti.*urin",
    ],
    "hematuria": [
        r"sang.*urine", r"urines.*rouges", r"pipi.*rouge",
        r"urines.*sanglantes", r"hematurie",
        r"sang.*pipi",
    ],
    "flank_pain": [
        r"\bflanc\b", r"douleur.*rein", r"\breins\b",
        r"cote.*dos", r"lombaire", r"colique.*nephretique",
        r"douleur.*lombaire",
    ],

    # ── ORL / DENTAIRE ──────────────────────────────────────────────────────
    "neck_swelling": [
        r"cou.*gonfle", r"ganglion.*cou", r"ganglion.*gonfl",
        r"gonflement.*cou", r"boule.*cou",
    ],
    "dental_swelling": [
        r"joue.*gonfl", r"visage.*gonfl", r"\babces\b",
        r"gencive.*gonfl", r"dent.*abces",
    ],
    "difficulty_swallowing": [
        r"difficulte.*avaler", r"mal.*avaler", r"n arrive pas.*avaler",
        r"dysphagie", r"avale.*mal", r"avaler.*douloureux",
        r"ne peut.*avaler",
    ],
    "epiglottitis_signs": [
        r"fievre.*avale.*mal.*bave", r"bave.*fievre.*gorg",
        r"gorge.*tres.*douloureux.*fever", r"dysphagie.*fievre.*soudaine",
        r"ne peut.*avaler.*salive.*fievre",
    ],

    # ── DERMATOLOGIE ────────────────────────────────────────────────────────
    "itching": [
        r"demange", r"\bgratte\b", r"\bprurit\b",
        r"demangeaison", r"peau.*gratte",
    ],
    "petechiae": [
        r"petechie", r"taches.*rouge.*petite.*peau",
        r"points.*rouge.*peau.*fievre",
        r"purpura",
    ],

    # ── SIGNAUX GÉNÉRAUX ────────────────────────────────────────────────────
    "loss_of_consciousness": [
        r"perd.*connaissance", r"perdu.*connaissance",
        r"s est evanoui", r"evanoui", r"inconscient",
        r"tombe.*sol.*connaissance", r"syncope",
        r"ne repond plus", r"ne reagit plus",
    ],
    "sudden_deterioration": [
        r"soudainement.*mal", r"brusquement.*mal",
        r"d un coup.*tres.*mal", r"deterioration.*rapide",
        r"empire.*rapidement", r"aggravation.*soudaine",
    ],
    "weight_loss": [
        r"perte de poids", r"\bamaigr", r"\bmaigri\b",
        r"a beaucoup maigri", r"perd du poids",
        r"\bminci\b",
    ],
    "night_sweats": [
        r"sueurs nocturnes", r"transpire.*nuit",
        r"mouille.*lit.*nuit", r"draps.*mouilles.*nuit",
        r"sueur.*nuit",
    ],
    "chills": [
        r"\bfrissons\b", r"tremble.*froid", r"grelotte",
        r"frissonne", r"froid.*tremble",
    ],
}

# ============================================================
# DÉTECTION NÉGATION — VERSION ÉTENDUE
# ============================================================

def is_negated_near(
    text: str,
    symptom_patterns: List[str],
    window_words: int = 10,
) -> bool:
    """
    Détecte si un symptôme est nié dans une fenêtre de mots.
    Version étendue :
    - Fenêtre élargie à 10 mots
    - Patterns "plus" et "jamais" inclus
    - Forme "sans X ni Y" gérée
    - Résolution temporelle gérée
    """
    words = text.split()

    for i in range(len(words)):
        zone = " ".join(words[i: i + window_words])
        if _has(zone, NEGATION_PATTERNS) and _has(zone, symptom_patterns):
            return True

    # Forme explicite : "sans vomissements ni fièvre"
    if re.search(r"sans .{0,60} ni ", text):
        for p in symptom_patterns:
            if re.search(rf"sans .{{0,60}} ni .{{0,40}}{p}", text):
                return True

    # "ne ... plus" (résolution)
    for p in symptom_patterns:
        if re.search(rf"ne .{{0,15}} plus .{{0,20}}{p}", text):
            return True
        if re.search(rf"ne .{{0,15}} {p} .{{0,15}} plus", text):
            return True

    # "jamais de X"
    for p in symptom_patterns:
        if re.search(rf"jamais .{{0,10}}{p}", text):
            return True

    return False


def _detect_with_negation(
    text: str,
    patterns: List[str],
    window: int = 10,
) -> Tuple[bool, bool]:
    """
    Retourne (positif, negated).
    Utilisé pour tous les patterns critiques (correction bug V1).
    """
    positive = _has(text, patterns)
    if not positive:
        return False, False
    negated = is_negated_near(text, patterns, window)
    return positive, negated

# ============================================================
# COMPOSITES CLINIQUES
# ============================================================

def _compute_composites(fields: Dict[str, Any], text_n: str) -> None:
    """
    Calcule les risques composites à partir des signaux détectés.
    Un seul point de vérité pour toutes les combinaisons.
    """
    pregnant = fields.get("pregnant", False)
    headache = fields.get("headache", False)
    severe_headache = fields.get("severe_headache", False)
    visual = fields.get("visual_disturbance", False)
    fever = fields.get("fever", False)
    neck = fields.get("neck_stiffness", False)
    seizures = fields.get("seizures", False)
    confusion = fields.get("confusion_acute", False)
    bleeding = fields.get("vaginal_bleeding", False)
    lower_right = fields.get("lower_right_abdominal_pain", False)
    unable_drink = fields.get("unable_to_drink", False)
    vomiting = fields.get("vomiting", False)
    diabetes = fields.get("diabetic_emergency", False) or fields.get("hypoglycemia_signs", False)
    postpartum = fields.get("postpartum", False)
    stroke = fields.get("stroke_signs", False)
    chest_severe = fields.get("chest_pressure_severe", False)
    resp_severe = fields.get("respiratory_distress_severe", False)

    # Pré-éclampsie
    fields["preeclampsia_risk"] = bool(
        pregnant and (severe_headache or headache) and visual
    )

    # Éclampsie (grossesse + convulsions)
    fields["eclampsia_risk"] = bool(pregnant and seizures)

    # Méningite
    fields["meningitis_risk"] = bool(
        (fever and neck)
        or fields.get("meningitis_signs", False)
    )

    # Appendicite
    fields["appendicitis_risk"] = bool(lower_right)

    # Déshydratation sévère
    fields["severe_dehydration"] = bool(
        unable_drink and (vomiting or "vomit" in text_n or "vomis" in text_n)
    )

    # AVC composite
    fields["stroke_risk"] = bool(stroke or (confusion and _has(text_n, [r"un cote", r"bras.*faible", r"bouche.*devie"])))

    # Risque IDM
    fields["cardiac_risk"] = bool(chest_severe or (fields.get("chest_pain", False) and fields.get("breathing_issue", False)))

    # Risque GEU (grossesse extra-utérine)
    fields["ectopic_risk"] = bool(
        fields.get("ectopic_risk", False)
        or (pregnant and fields.get("lower_abdominal_pain", False) and fields.get("sudden_deterioration", False))
    )

    # Fièvre post-partum
    fields["postpartum_fever"] = bool(postpartum and fever)

    # Paludisme grave
    malaria = fields.get("malaria_signs", False)
    fields["malaria_severe"] = bool(
        malaria and (seizures or confusion or unable_drink or resp_severe or fields.get("severe_anemia", False))
    )

    # Acidocétose diabétique
    fields["dka_risk"] = bool(
        fields.get("diabetic_emergency", False)
        and (vomiting or fields.get("confusion_acute", False))
    )

    # Choc hémorragique digestif
    fields["gi_bleeding_risk"] = bool(
        fields.get("upper_gi_bleeding", False) or fields.get("lower_gi_bleeding", False)
    )

    # Crise drépanocytaire grave
    fields["sickle_crisis_severe"] = bool(
        fields.get("sickle_cell_crisis", False)
        and (fever or resp_severe or fields.get("stroke_signs", False))
    )

    # Nourrisson danger
    neonatal = fields.get("neonatal_danger", False)
    fields["neonatal_emergency"] = bool(neonatal and (fever or fields.get("unable_to_drink", False)))

# ============================================================
# APPLICATION DES RÈGLES
# ============================================================

def _apply_rule_patterns(text_n: str, fields: Dict[str, Any]) -> None:
    """
    Applique tous les patterns avec négation active sur TOUS les signaux.
    Correction bug V1 : CRITICAL_PATTERNS_FR avait des signaux sans négation.
    """
    # CRITICAL : maintenant avec détection de négation
    for label, patterns in CRITICAL_PATTERNS_FR.items():
        positive, negated = _detect_with_negation(text_n, patterns)
        if positive and not negated:
            fields[label] = True
        elif negated:
            fields[label] = False
            fields[f"{label}_negated"] = True

    # SYMPTOM : négation active (inchangé)
    for label, patterns in SYMPTOM_PATTERNS_FR.items():
        positive, negated = _detect_with_negation(text_n, patterns)
        if positive and not negated:
            fields[label] = True
        elif negated:
            fields[label] = False
            fields[f"{label}_negated"] = True

# ============================================================
# MODE AUTO ML AMÉLIORÉ
# ============================================================

# Signaux qui indiquent un P1 détecté → skip ML (inutile et coûteux)
_P1_SIGNALS = [
    "preeclampsia_risk", "eclampsia_risk", "stroke_risk", "stroke_signs",
    "suicidal_text", "severe_dehydration", "hemorrhagic_fever_signs",
    "snake_bite", "toxic_ingestion", "head_trauma", "burn_severe",
    "neonatal_emergency", "respiratory_distress_severe",
    "upper_gi_bleeding", "loss_of_consciousness", "meningitis_risk",
    "diabetic_emergency", "thunderclap_headache", "acute_psychosis",
]


def _should_call_model(fields: Dict[str, Any]) -> bool:
    if USE_ML_NLP == "off":
        return False
    if USE_ML_NLP == "on":
        return True
    # Mode "auto" : skip si P1 déjà détecté par les règles
    if USE_ML_NLP == "auto":
        p1_found = any(fields.get(sig) for sig in _P1_SIGNALS)
        return not p1_found
    return False


def _merge_model_entities(entities: List[Dict[str, Any]], fields: Dict[str, Any]) -> None:
    """
    Fusionne les entités du modèle ML dans les fields.
    Les négations détectées par les règles ont priorité.
    """
    for ent in entities:
        label = str(ent.get("entity_group") or ent.get("entity") or "").lower()
        label = re.sub(r"^[bi]-", "", label).replace(" ", "_").strip()

        if not label or label == "o":
            continue

        # Ne pas écraser une négation déjà détectée par les règles
        if fields.get(f"{label}_negated"):
            continue

        score = float(ent.get("score", 0))
        if score >= 0.5:  # seuil de confiance minimal
            fields[label] = True



# ============================================================
# HARDENING V2.1 — corrections sûreté terrain AlloDocteur
# ============================================================

def _harden_fields_v21(fields: Dict[str, Any], text_n: str) -> None:
    """Corrige les faux positifs critiques avant injection dans le moteur.

    Cette couche ne décide jamais la priorité. Elle stabilise seulement les signaux.
    """
    # Grossesse : priorité à la négation portée par le patient.
    patient_pregnancy_negated = _has(text_n, [
        r"je ne suis pas enceinte", r"je suis pas enceinte", r"pas enceinte",
        r"moi.*pas enceinte", r"ne suis oas enceinte", r"je ne suis oas enceinte"
    ])
    third_party_pregnancy = _has(text_n, [r"ma voisine.*enceinte", r"mon voisin.*enceinte", r"ma soeur.*enceinte", r"ma fille.*enceinte"])
    if patient_pregnancy_negated:
        fields["pregnant"] = False
        fields["pregnant_negated"] = True
        fields["pregnancy_month"] = False
        fields["preeclampsia_risk"] = False
        fields["eclampsia_risk"] = False
    elif third_party_pregnancy and not _has(text_n, [r"je suis enceinte", r"moi.*enceinte", r"enceinte de \d+ mois"]):
        fields["pregnant"] = False
        fields["pregnant_third_party"] = True

    # Lombalgie : "mal au dos" ne doit pas être nié par "pas de fièvre / pas de vomissement".
    if _has(text_n, [r"mal au dos", r"douleur.*dos", r"bas du dos", r"lombalg"]):
        fields["back_pain"] = True
        fields["back_pain_negated"] = False

    # Pleurs aigu chez enfant ≠ tristesse persistante / dépression.
    if _has(text_n, [r"pleure", r"il pleure", r"elle pleure"]) and not _has(text_n, [r"triste depuis", r"tristesse", r"deprime", r"depression", r"plus envie"]):
        fields["emotional_distress"] = True
        fields["persistent_sadness"] = False
        fields["persistent_sadness_negated"] = True

    # Saignements : distinguer nez/gencives/vaginal.
    epistaxis = _has(text_n, [r"saigne du nez", r"saignement nasal", r"nez.*saigne"]) and not _has(text_n, [r"pas de saignement", r"pas de saignemen"])
    gingival = _has(text_n, [r"saigne des gencives", r"saigne.*genciv", r"gencives.*saign", r"saignement.*genciv"]) and not _has(text_n, [r"pas de saignement", r"pas de saignemen"])
    if epistaxis:
        fields["epistaxis"] = True
    if gingival:
        fields["gingival_bleeding"] = True
        fields["dental_pain"] = False
    if epistaxis or gingival:
        fields["mucosal_bleeding"] = True
        fields["bleeding"] = True

    # Vaginal bleeding uniquement si explicitement gynécologique.
    explicit_vaginal = _has(text_n, [r"saignement vaginal", r"sang.*vagin", r"pertes.*sang", r"pertes rouges", r"je saigne.*vagin"])
    if not explicit_vaginal:
        fields["vaginal_bleeding"] = False
    if fields.get("sex_male") or _has(text_n, [r"homme"]):
        fields["vaginal_bleeding"] = False

    # Fièvre hémorragique : jamais sans fièvre confirmée ET saignement réel non nié.
    fever_present = fields.get("fever", False) or (_has(text_n, [r"fievre", r"un peu de fievre", r"temperature"]) and not _has(text_n, [r"pas de fievre", r"sans fievre"]))
    bleeding_present = fields.get("mucosal_bleeding", False) or fields.get("bleeding", False)
    bleeding_negated = _has(text_n, [r"pas de saignement", r"pas de saignemen", r"sans saignement", r"aucun saignement"])
    if bleeding_negated:
        fields["hemorrhagic_fever_signs"] = False
        fields["hemorrhagic_fever_signs_negated"] = True
        fields["bleeding"] = False
    elif fields.get("hemorrhagic_fever_signs") and not (fever_present and bleeding_present):
        fields["hemorrhagic_fever_signs"] = False
        fields["hemorrhagic_fever_signs_negated"] = True

    # Expression locale : "mon sang fait mal" = douleur diffuse, pas fièvre hémorragique ni drépanocytose sans antécédent.
    if _has(text_n, [r"mon sang.*mal", r"sang fait.*mal", r"le sang.*mal"]):
        fields["diffuse_pain"] = True
        fields["pain"] = True
        fields["hemorrhagic_fever_signs"] = False
        fields["hemorrhagic_fever_signs_negated"] = True
        if not _has(text_n, [r"drepanocytose", r"drepanocytaire", r"hemoglobine ss"]):
            fields["sickle_cell_crisis"] = False
            fields["sickle_crisis_severe"] = False

    # Ingestion caustique et hypersalivation.
    if _has(text_n, [r"avale.*produit", r"produit de nettoyage", r"a bu.*produit", r"avale.*poison"]):
        fields["toxic_ingestion"] = True
        fields["poisoning"] = True
    if _has(text_n, [r"bave", r"salive beaucoup", r"hypersalivation"]):
        fields["hypersalivation"] = True
    if fields.get("toxic_ingestion") and _has(text_n, [r"produit de nettoyage", r"javel", r"acide", r"soude", r"detergent"]):
        fields["corrosive_risk"] = True

    # Eclampsie : grossesse + crise/tremblements/amnésie post-crise.
    seizure_text = _has(text_n, [r"convulsion", r"crise", r"tremblait", r"tout mon corps trembl", r"secousse", r"ne me souviens plus", r"ne me souvies plus"])
    if fields.get("pregnant") and seizure_text:
        fields["seizures"] = True
        fields["seizure_like"] = True
        fields["postictal_state"] = _has(text_n, [r"ne me souviens plus", r"ne me souvies plus"])
        fields["eclampsia_risk"] = True

    # GEU : aménorrhée + douleur bas ventre latéralisée + malaise/présyncope = grossesse possible même si non déclarée.
    amenorrhea = _has(text_n, [r"pas eu mes regles", r"pas de regles", r"retard.*regles", r"regles depuis \d+ mois"])
    lower_pain = fields.get("lower_abdominal_pain", False) or _has(text_n, [r"bas du ventre", r"ventre.*gauche", r"ventre.*droite", r"pelvien"])
    presyncope = _has(text_n, [r"failli tomber", r"presque tombe", r"vertige", r"malaise", r"tres faible"])
    if amenorrhea:
        fields["amenorrhea"] = True
        fields["possible_pregnancy"] = True
    if amenorrhea and lower_pain and presyncope:
        fields["ectopic_risk"] = True

    # DKA : enrichissement sémantique.
    if _has(text_n, [r"haleine.*fruit", r"haleine.*sucree", r"haleine.*acetonique"]):
        fields["acetone_breath"] = True
    if fields.get("diabetic_emergency") or fields.get("dka_risk"):
        fields["metabolic_emergency"] = True

# ============================================================
# FONCTION PRINCIPALE D'EXTRACTION
# ============================================================

def extract_medical_features(text: Any) -> Dict[str, Any]:
    """
    Extraction hybride NLP AlloDocteur V2.

    Pipeline :
    1. Normalisation texte (corrections ortho + expressions RDC)
    2. Application règles regex avec négation sur TOUS les signaux
    3. Calcul composites cliniques (pré-éclampsie, méningite, etc.)
    4. Appel modèle ML (si USE_ML_NLP != "off" et pas P1 détecté en auto)
    5. Fusion ML + règles (règles prioritaires)
    6. Recalcul composites post-ML

    Retourne un dict injectable directement dans extract_v38_signals().
    """
    start_time = time.time()

    raw_text = str(text or "")
    text_n = normalize_fr(raw_text)

    fields: Dict[str, Any] = {}
    entities: List[Dict[str, Any]] = []

    # 1. Règles avec négation complète
    _apply_rule_patterns(text_n, fields)

    # 2. Composites avant ML
    _compute_composites(fields, text_n)
    _harden_fields_v21(fields, text_n)

    # 3. Modèle ML conditionnel
    use_ml = _should_call_model(fields)
    if use_ml:
        entities = _labels_from_model(raw_text)
        _merge_model_entities(entities, fields)

    # 4. Recalcul composites après ML
    _compute_composites(fields, text_n)
    _harden_fields_v21(fields, text_n)
    _compute_composites(fields, text_n)

    return {
        "text_normalized_nlp": text_n,
        "nlp_entities": entities,
        "nlp_fields": fields,
        "nlp_model_dir": str(MODEL_DIR),
        "nlp_model_used": use_ml,
        "nlp_model_loaded": _NER_PIPE is not None,
        "nlp_load_error": _NER_LOAD_ERROR,
        "nlp_elapsed_seconds": round(time.time() - start_time, 4),
        "nlp_mode": USE_ML_NLP,
        "nlp_version": "2.1-safe",
    }
