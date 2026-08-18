from __future__ import annotations

DURATION_OPTIONS = [
    'Moins de 24 heures', '1 à 3 jours', '4 à 7 jours',
    "Plus d'une semaine", "Plus d'un mois", "Plus d'une année",
]
ASSOCIATED_OPTIONS = [
    'Fièvre', 'Douleurs intenses', 'Essoufflement', 'Vomissements / diarrhée',
    'Éruption cutanée', 'Fatigue', 'Maux de tête', "Perte d'appétit", 'Aucun',
]
CONSULT_OPTIONS = [
    'Oui, dans les 30 derniers jours', "Oui, il y a plus d'un mois",
    "Oui, il y a plus d'une année", 'Non', 'Je ne sais pas',
]
HISTORY_OPTIONS = [
    'Diabète', 'Obésité', 'Hypertension', 'AVC', 'Tuberculose',
    'Migraine chronique', 'Épilepsie', 'Césarienne', 'Dépression', 'Asthme',
    'Maladie cardiaque', 'Allergies', 'Interventions chirurgicales',
    'Avortements', 'Aucun antécédent',
]

IMMEDIATE_SEVERITY_SIGNS = {
    'severe_breathing': 'Difficulté grave à respirer, étouffement ou sifflement respiratoire',
    'chest_pressure': 'Douleur ou forte pression dans la poitrine',
    'severe_diarrhea_unable_to_drink': 'Diarrhée sévère très fréquente avec incapacité de garder les liquides',
    'severe_dehydration': 'Signes de déshydratation grave',
    'stroke_signs': "Faiblesse d'un côté, difficulté à parler, visage dévié",
    'loss_of_consciousness': 'Perte de connaissance / inconscient / ne répond plus',
    'sudden_confusion': 'Confusion soudaine ou comportement bizarre',
    'uncontrollable_bleeding': 'Saignements abondants impossibles à arrêter',
    'board_like_abdomen': 'Ventre très dur et douleur insupportable',
    'fever_with_neck_stiffness': 'Fièvre élevée avec raideur au cou ou violents maux de tête',
    'seizures': 'Convulsions ou tremblements incontrôlables',
    'rash_with_fever': 'Boutons, cloques ou taches suspectes avec forte fièvre',
    'poisoning': 'Ingestion de produit toxique, poison ou surdosage médicamenteux',
    'severe_burn': 'Brûlure grave',
    'suicidal_or_extreme_psy': 'Pensées suicidaires, agressivité extrême ou peur immédiate',
    'open_fracture_or_major_accident': 'Fracture ouverte ou accident grave',
    'head_trauma': 'Choc violent à la tête après chute ou accident',
}

def normalize_sex(value: str) -> str:
    value = value.strip().lower()
    if value in {'f', 'femme', 'féminin', 'feminin', 'female', 'patiente'}:
        return 'female'
    if value in {'m', 'homme', 'masculin', 'male', 'patient'}:
        return 'male'
    return 'unknown'
