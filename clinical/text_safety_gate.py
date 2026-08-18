from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class TextSafetyResult:
    emergency: bool
    code: str | None = None
    reason: str | None = None
    primary_specialty: str = 'Médecine d’urgence'
    contradictions: tuple[str, ...] = ()
    triggered_codes: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


def normalize_text(value: str) -> str:
    text = unicodedata.normalize('NFKD', value.lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "'").replace("'", ' ')
    text = re.sub(r"[^a-z0-9 ]+", ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


# Fenêtre de négation volontairement courte : elle doit nier le symptôme proche,
# sans annuler un signe positif situé plus loin dans la même phrase.
NEGATORS = ('pas', 'aucun', 'aucune', 'jamais', 'sans', 'ni')


def _is_locally_negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 55):start]
    words = prefix.split()
    recent = ' '.join(words[-6:])
    # "ne ... pas" est normalisé en deux mots, mais le "pas" suffit ici.
    return any(re.search(rf'\b{re.escape(n)}\b', recent) for n in NEGATORS)


def _pattern_hit(text: str, pattern: str) -> bool:
    for m in re.finditer(pattern, text):
        if _is_locally_negated(text, m.start()):
            continue
        return True
    return False


def _any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(_pattern_hit(text, p) for p in patterns)


def has_positive_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    """Helper partagé avec les garde-fous populationnels."""
    return _any(normalize_text(text), patterns)


# Motifs génériques par concept. Ils sont volontairement orientés vers la
# sensibilité, mais les concepts composites (méningite, rash fébrile, etc.)
# sont validés plus bas avec plusieurs composantes afin de limiter le sur-triage.
CONCEPTS: dict[str, tuple[str, ...]] = {
    'severe_breathing': (
        r'respir(?:e|er) a peine', r'n arrive (?:plus |plu )?a respir', r'j arrive (?:plus |plu )a respir', r'impossible de respir',
        r'difficulte (?:tres |grave |importante |grosse )?(?:pour |a )?respir', r'du mal a respir',
        r'manque (?:tellement |beaucoup )?d air', r'air ne rentre plus', r'lutter pour chaque respiration',
        r'reprendre mon souffle', r'souffle tres court', r'soufle tres court', r'essoufflement (?:tres |important|severe)',
        r'suffoqu', r'(?:je |il |elle |on )?etouff(?:e|ement)', r'sensation d etouffement',
        r'levres? (?:qui |deviennent? )?bleu', r'cyanose',
        r'tirage respiratoire', r'respiration tres difficile', r'peine .* respir', r'ne peux presque plus parler .*air',
    ),
    'chest_pressure': (
        r'douleur (?:tres |forte |intense )?(?:a la |dans la )?poitrine', r'douleur thoracique',
        r'(?:serre|serrement|serree|serree).*poitrine', r'poitrine.*(?:serre|serree|comprimee|compression)',
        r'pression (?:enorme )?(?:sur|dans) .*poitrine', r'oppression (?:thoracique|dans la poitrine)',
        r'poids .*poitrine', r'etau .*poitrine', r'lourdeur .*thorax', r'thorax .*brul.*serr',
        r'douleur .*sternum', r'douleur .*bras gauche', r'poitrin .*serr', r'poitrine comprimee',
    ),
    'severe_diarrhea_unable_to_drink': (
        r'diarrh(?:ee|e) .*n arrive (?:plus )?a boire', r'diarrh(?:ee|e) .*incapable de (?:boire|garder)',
        r'diarrh(?:ee|e) .*impossib.*(?:boire|garder)', r'diarrh(?:ee|e) .*garder .*liquide',
        r'diarrh(?:ee|e) .*ne garde .*liquide', r'diarrh(?:ee|e) .*chaque gorgee .*vom',
        r'diarrh(?:ee|e) .*tout ce que .*bois .*ressort', r'diarrh(?:ee|e) (?:tres |massive|profuse|severe|abondante).*boire',
        r'selles .*continuellement .*ne peux .*liquide', r'selles liquides .*tout .*bois .*ressort',
        r'selles .*sans arret .*boire', r'selles eau .*impossible de boire', r'perds .*eau par les selles .*boire',
        r'diare .*garde pa .*eau',
    ),
    'severe_dehydration': (
        r'aucune urine .*bouche .*seche', r'absence d urines?.*(?:faiblesse|bouche|sec)',
        r'pas d urine .*faiblesse', r'presque pas d urines?', r'n urine presque plus', r'n urine plus normalement',
        r'pas urine .*journee', r'sans urine', r'deshydrat(?:ation|e) (?:grave|severe|extreme)',
        r'extremement deshydrate', r'tres desseche', r'bouche (?:tres |completement )?seche .*urine',
        r'bouche seche .*yeux? creu', r'yeux? (?:tres )?creux .*bouche .*seche', r'yeux? creux .*boire',
    ),
    'stroke_signs': (
        r'visage .*de travers', r'bouche .*de travers', r'bouche .*tombe .*cote', r'visage .*affaiss.*cote',
        r'visage .*devie', r'cote du visage .*ne repond plus', r'coin de la bouche .*tombe',
        r'bras .*paraly', r'jambe .*paraly', r'bras .*ne bouge plus', r'n arrive plus a lever .*bras',
        r'faiblesse (?:brutale|soudaine).*un cote', r'un cote du corps .*faible', r'perdu .*force .*bras',
        r'parole (?:incomprehensible|troublee)', r'parle (?:mal|difficilement|bizarrement)', r'bafouill',
        r'mots .*bizarre', r'trouble .*parole', r'n arrive plus a parler', r'attaque cerebrale', r'signes d avc',
    ),
    'loss_of_consciousness': (
        r'perdu connaissance', r'perte de connaissance', r'inconscient', r'absence de reponse', r'ne repond plus',
        r'evanoui', r'evanouie', r'evanouissement', r'blackout', r'tombe .*inconscient',
    ),
    'sudden_confusion': (
        r'confus.*(?:brutal|soudain|quelques minutes|d un coup)', r'(?:brutal|soudain).*confus',
        r'confusion (?:soudaine|brusque|aigue)', r'brusque confusion', r'desorient(?:e|ee|ation).*(?:brutal|soudain|aigue)',
        r'(?:brutal|soudain).*desorient', r'ne reconna(?:it|i) .*plus .*person', r'ne reconna.*plus .*famille',
        r'reconnai plu personne', r'ne sais plus ou .*suis', r'repond a cote .*perd',
        r'comportement .*bizarre .*d un coup', r'comportement .*bizarre .*confusion',
    ),
    'uncontrollable_bleeding': (
        r'saign(?:e|ement) .*enorm', r'saignement .*abondant', r'saignement .*incontrol',
        r'saignement .*ne s arrete pas', r'saigne .*s arrete pa', r'saigne .*sarrete pa', r'sang .*sans s arreter',
        r'sang .*impossible .*arreter', r'sang .*impossible .*stopper', r'perte de sang massive',
        r'perds? beaucoup de sang', r'perdre enormement de sang', r'compression .*ne suffit pas',
        r'hemorragie (?:importante|massive|abondante)',
    ),
    'board_like_abdomen': (
        r'ventre .*dur comme (?:une planche|du bois)', r'ventre .*rigide', r'rigidite abdominale',
        r'abdomen .*rigide', r'abdomen .*tres dur', r'ventre .*tres tendu', r'ventre en planche',
        r'ventre .*planche', r'ventre .*kom planche', r'ventre .*ne se laisse plus toucher .*dur',
    ),
    'seizures': (
        r'convuls', r'crise convulsive', r'crises convulsives', r'crise epileptique', r'crises epileptiques',
        r'secousses generalisees .*perte de contact', r'mouvements incontrol.*tout le corps',
    ),
    'poisoning': (
        r'(?:avale|ingere|ingestion|bu|boit) .*pesticid', r'(?:avale|ingere|ingestion|bu|boit) .*poison',
        r'(?:avale|ingere|ingestion|bu|boit) .*produit .*toxique', r'liquide toxique',
        r'produit de nettoyage dangereux', r'eau de javel', r'empoisonnement', r'intoxication',
        r'surdosage', r'trop de comprimes', r'trop de medicaments', r'quantite inconnue .*poison',
    ),
    'severe_burn': (
        r'brul(?:e|ure|ures) .*grav', r'brulure .*severe', r'brulure .*etendue', r'brulures? importantes',
        r'large partie .*brule', r'grande partie .*brule', r'grande surface .*brule', r'visage .*brule',
        r'brulure .*visage', r'brulure profonde .*visage', r'brulure .*poitrine .*bras', r'brulure .*explosion',
    ),
    'suicidal_or_extreme_psy': (
        r'veux me tuer', r'veux en finir', r'envie de mourir', r'me suicid', r'suicide',
        r'intention .*suicid', r'pense serieusement .*suicide', r'plan .*suicid', r'plan .*me tuer',
        r'prevu de me tuer', r'faire du mal maintenant', r'me faire du mal', r'disparaitre pour toujours',
        r'tuer quelqu un', r'agressivite extreme',
    ),
    'open_fracture_or_major_accident': (
        r'os .*sort .*plaie', r'os .*visible .*dehors', r'os sorti .*accident', r'fracture ouverte',
        r'accident (?:tres )?grave .*plusieurs blessures', r'accident majeur', r'grosse collision .*traumat',
        r'ecrase par .*vehicule', r'polytraumatis', r'deformation .*plaie profonde',
    ),
    'head_trauma': (
        r'choc (?:violent )?(?:a la )?tete', r'choc cranien', r'traumatisme cranien', r'traumatisme de la tete',
        r'impact cranien', r'coup violent .*tete', r'gros coup .*tete', r'chute .*tete .*vom',
        r'tete .*frappee .*vom', r'choc .*tete .*vom', r'choc .*tete .*somnol', r'tete .*rester eveill',
    ),
}

LABELS = {
    'severe_breathing': 'Difficulté respiratoire sévère',
    'chest_pressure': 'Douleur ou pression thoracique préoccupante',
    'severe_diarrhea_unable_to_drink': 'Diarrhée sévère avec incapacité à boire',
    'severe_dehydration': 'Signes de déshydratation sévère',
    'stroke_signs': 'Signes neurologiques soudains compatibles avec une urgence',
    'loss_of_consciousness': 'Perte de connaissance ou absence de réponse',
    'sudden_confusion': 'Confusion aiguë ou désorientation soudaine',
    'uncontrollable_bleeding': 'Saignement abondant ou incontrôlable',
    'board_like_abdomen': 'Abdomen très dur avec douleur intense',
    'fever_with_neck_stiffness': 'Fièvre associée à une raideur de nuque ou céphalée violente',
    'seizures': 'Convulsions ou crises répétées',
    'rash_with_fever': 'Fièvre avec éruption préoccupante',
    'poisoning': 'Ingestion ou exposition toxique / surdosage',
    'severe_burn': 'Brûlure grave ou étendue',
    'suicidal_or_extreme_psy': 'Danger psychique immédiat',
    'open_fracture_or_major_accident': 'Traumatisme majeur ou fracture ouverte',
    'head_trauma': 'Traumatisme crânien préoccupant',
}

LEGACY_CODES = {
    'chest_pressure': 'TEXT_CHEST_PRESSURE_WITH_DYSPNEA',
    'stroke_signs': 'TEXT_STROKE_WARNING',
    'loss_of_consciousness': 'TEXT_LOSS_OF_CONSCIOUSNESS',
    'suicidal_or_extreme_psy': 'TEXT_SUICIDAL_DANGER',
}

SPECIALTIES = {
    'stroke_signs': 'Neurologie', 'seizures': 'Neurologie', 'sudden_confusion': 'Neurologie',
    'suicidal_or_extreme_psy': 'Psychiatrie', 'chest_pressure': 'Cardiologie',
    'severe_breathing': 'Pneumologie', 'fever_with_neck_stiffness': 'Infectiologie',
}

FEVER = (r'\bfievre\b', r'temperature (?:tres |forte |elevee|haute)', r'forte temperature', r'grosse fievre', r'haute fievre')
NECK_STIFFNESS = (
    r'nuque (?:tres )?raide', r'raideur (?:de la )?nuque', r'cou (?:tres )?raide', r'cou .*devenu (?:tres )?raide', r'nuque bloquee',
    r'difficulte a bouger .*nuque', r'n arrive .*plier .*cou',
)
SEVERE_HEADACHE = (r'mal de tete (?:violent|terrible|intense)', r'cephalee (?:intense|violente)')
RASH = (r'eruption', r'boutons?', r'taches? (?:rouges? )?', r'vesicules?', r'cloques?', r'lesions cutanees')
RASH_HIGH_RISK_QUALIFIER = (
    r'generalisee?', r'partout .*corps', r'sur tout le corps', r'diffus', r'nombreu', r'se multipl',
    r'forte fievre', r'grosse fievre', r'fievre elevee', r'fievre importante', r'haute fievre', r'temperature forte',
)
ABDOMINAL_SEVERE_PAIN = (r'douleur (?:abdominale )?(?:tres forte|violente|intense|extreme|atroce|insupportable)', r'tres douloureux', r'dur et douloureux')


# V6.4.1.4 — Composite Safety Patterns
# -------------------------------------
# Ces motifs ne déclenchent jamais P1 sur un seul mot isolé. Ils exigent une
# combinaison clinique spécifique et respectent la négation locale via _any().
AIRWAY_NOISY_INSPIRATION = (
    r'bruit aigu .*inspir', r'bruit aigu .*respir', r'stridor', r'respiration bruyante',
    r'bruit .*quand .*inspire',
)
AIRWAY_SWALLOWING_DANGER = (
    r'\bbave\b', r'bave beaucoup', r'salive .*sans pouvoir avaler', r'refuse d avaler',
    r'n arrive (?:plus )?a avaler', r'impossible d avaler', r'difficulte importante .*avaler',
)
RESPIRATORY_AT_REST = (
    r'essouffl.*(?:au repos|sans bouger|assis|allonge)', r'manque d air .*au repos',
    r'respire difficilement .*au repos', r'dyspnee .*au repos',
)
SPEECH_LIMITATION_BY_BREATHING = (
    r'ne peux (?:dire|parler) que quelques mots', r'quelques mots .*a la fois',
    r'n arrive pas a finir .*phrase', r'ne peut pas finir .*phrase',
    r'parle mot par mot', r'parler .*reprendre .*souffle',
)
ASTHMA_CONTEXT = (r'\basthm', r'asthmatique')
RESCUE_TREATMENT_FAILURE = (
    r'inhalateur .*ne (?:marche|fonctionne) (?:presque )?plus', r'inhalateur .*ne soulage (?:presque )?plus',
    r'traitement de secours .*ne .*plus', r'bronchodilatateur .*ne .*plus',
)
BREATHING_STRUGGLE = (
    r'lutte pour respirer', r'lutter pour respirer', r'peine beaucoup a respirer',
    r'respiration tres difficile', r'j etouffe', r'il etouffe', r'elle etouffe',
)
PESTICIDE_EXPOSURE = (
    r'exposition .*pesticid', r'pulverisation .*pesticid', r'contact .*pesticid',
    r'insecticide', r'organophosph', r'carbamate',
)
CHOLINERGIC_SIGNS = (
    r'salive beaucoup', r'hypersaliv', r'transpir', r'sueurs? abond', r'vom', r'diarrh',
    r'pupilles? .*serre', r'myosis', r'larmoi',
)
RESPIRATORY_OR_NEURO_DANGER = (
    r'respire difficilement', r'difficulte .*respir', r'manque d air', r'etouff',
    r'confus', r'convuls', r'perte de connaissance', r'inconscient',
)
EXPLICIT_NORMAL_BREATHING = (
    r'respiration normale', r'respire normalement', r'aucune difficulte .*respir',
    r'pas de difficulte .*respir', r'sans difficulte .*respir', r'pas essouffle',
)


def _count_positive_groups(text: str, groups: tuple[tuple[str, ...], ...]) -> int:
    return sum(1 for group in groups if _any(text, group))


def _v6414_composite_hits(text: str) -> list[str]:
    hits: list[str] = []

    # 1) Menace des voies aériennes supérieures : bruit inspiratoire/stridor
    # + incapacité à gérer les sécrétions ou à avaler.
    if _any(text, AIRWAY_NOISY_INSPIRATION) and _any(text, AIRWAY_SWALLOWING_DANGER):
        hits.append('severe_breathing')

    # 2) Détresse respiratoire : dyspnée au repos + limitation de la parole.
    if (_any(text, RESPIRATORY_AT_REST)
            and _any(text, SPEECH_LIMITATION_BY_BREATHING)
            and not _any(text, EXPLICIT_NORMAL_BREATHING)):
        hits.append('severe_breathing')

    # 3) Asthme sévère : contexte d'asthme + échec du traitement de secours
    # + lutte respiratoire explicite.
    if (_any(text, ASTHMA_CONTEXT)
            and _any(text, RESCUE_TREATMENT_FAILURE)
            and _any(text, BREATHING_STRUGGLE)
            and not _any(text, EXPLICIT_NORMAL_BREATHING)):
        hits.append('severe_breathing')

    # 4) Syndrome cholinergique après pesticide : exposition + au moins deux
    # familles de signes cholinergiques + atteinte respiratoire/neurologique.
    # Le comptage se fait par familles afin d'éviter qu'un seul mot déclenche P1.
    cholinergic_families = (
        (r'salive beaucoup', r'hypersaliv'),
        (r'transpir', r'sueurs? abond'),
        (r'vom', r'diarrh'),
        (r'pupilles? .*serre', r'myosis'),
        (r'larmoi',),
    )
    if (_any(text, PESTICIDE_EXPOSURE)
            and _count_positive_groups(text, cholinergic_families) >= 2
            and _any(text, RESPIRATORY_OR_NEURO_DANGER)
            and not _any(text, EXPLICIT_NORMAL_BREATHING)):
        hits.extend(['poisoning', 'severe_breathing'])

    return list(dict.fromkeys(hits))


def _composite_hits(text: str) -> list[str]:
    hits: list[str] = _v6414_composite_hits(text)

    # Méningite / syndrome méningé : nécessite une fièvre positive ET un signe
    # méningé positif. "sans raideur de nuque" ne peut donc pas déclencher P1.
    if _any(text, FEVER) and (_any(text, NECK_STIFFNESS) or _any(text, SEVERE_HEADACHE)):
        hits.append('fever_with_neck_stiffness')

    # Rash fébrile : l'éruption seule ou quelques boutons avec état conservé ne
    # constituent pas automatiquement un P1. On exige un caractère étendu / marqué
    # ou une fièvre explicitement forte, conformément au contrat de sécurité V6.4.
    if _any(text, FEVER) and _any(text, RASH) and _any(text, RASH_HIGH_RISK_QUALIFIER):
        if not _any(text, (r'quelques boutons?', r'etat general conserve', r'eruption legere', r'petite eruption')):
            hits.append('rash_with_fever')

    # Abdomen en planche : rigidité + douleur sévère, pour éviter de classer P1
    # un simple ballonnement/tension abdominale.
    if _any(text, CONCEPTS['board_like_abdomen']) and _any(text, ABDOMINAL_SEVERE_PAIN):
        hits.append('board_like_abdomen')

    return hits


def evaluate_text_safety(complaint_text: str, associated_signs: list[str]) -> TextSafetyResult:
    text = normalize_text(complaint_text + ' ' + ' '.join(associated_signs))

    composite = set(_composite_hits(text))
    skip_direct = {'fever_with_neck_stiffness', 'rash_with_fever', 'board_like_abdomen'}
    hits = []
    for code, patterns in CONCEPTS.items():
        if code in skip_direct:
            continue
        if code == 'severe_breathing' and _any(text, EXPLICIT_NORMAL_BREATHING):
            continue
        if _any(text, patterns):
            hits.append(code)
    hits.extend(code for code in composite if code not in hits)

    # Négation suicidaire explicite. Le moteur garde toutefois une intention
    # positive située après une opposition ("... mais je veux me tuer").
    if 'suicidal_or_extreme_psy' in hits:
        suicidal_negations = (
            r'ne veux pas mourir', r'pas envie de mourir', r'aucune envie de .*suicid',
            r'ne veux pas me suicid', r'jamais voulu me suicid', r'ne pense pas .*suicide',
        )
        negated = any(re.search(p, text) for p in suicidal_negations)
        positive_override = any(re.search(p, text) for p in (
            r'mais .*veux .*mourir', r'mais .*veux .*suicid', r'plan .*me tuer',
            r'intention .*suicid', r'prevu .*me tuer',
        ))
        if negated and not positive_override:
            hits.remove('suicidal_or_extreme_psy')

    # Ordre stable selon la définition des concepts, utile pour les traces/audits.
    order = list(CONCEPTS) + ['fever_with_neck_stiffness', 'rash_with_fever']
    hits = sorted(set(hits), key=lambda x: order.index(x) if x in order else 999)

    if not hits:
        return TextSafetyResult(False)

    evidence = tuple(LABELS[c] for c in hits)
    primary = SPECIALTIES.get(hits[0], 'Médecine d’urgence')
    return TextSafetyResult(
        True,
        code=LEGACY_CODES.get(hits[0], hits[0]),
        reason='; '.join(evidence[:3]),
        primary_specialty=primary,
        triggered_codes=tuple(hits),
        evidence=evidence,
    )
