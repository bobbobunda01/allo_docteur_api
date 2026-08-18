from __future__ import annotations

from dataclasses import dataclass
from clinical.text_safety_gate import normalize_text, _any
from domain.models import IntakeAnswers


@dataclass(frozen=True)
class PopulationSafetyResult:
    emergency: bool = False
    priority_floor: str | None = None
    triggered_codes: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    requires_human_review: bool = False


def evaluate_population_safety(intake: IntakeAnswers) -> PopulationSafetyResult:
    p = intake.patient
    text = normalize_text(intake.complaint_text + ' ' + ' '.join(intake.associated_signs))
    codes: list[str] = []
    evidence: list[str] = []
    emergency = False
    floor: str | None = None
    review = False

    if p.pregnant:
        obstetric_bleeding = _any(text, (
            r'saignement vaginal (?:tres )?abondant', r'saigne beaucoup .*vagin', r'hemorragie vaginale',
            r'perds beaucoup de sang .*vagin',
        ))
        severe_headache = _any(text, (r'mal de tete (?:intense|violent|tres fort)', r'cephalee (?:intense|violente)'))
        visual = _any(text, (r'vision trouble', r'vois flou', r'taches devant les yeux', r'eclairs devant les yeux'))
        convulsion = _any(text, (r'convuls', r'crise convulsive', r'crise epileptique'))
        if obstetric_bleeding:
            emergency = True
            codes.append('obstetric_major_bleeding')
            evidence.append('Grossesse avec saignement vaginal abondant')
        if (severe_headache and visual) or convulsion:
            emergency = True
            codes.append('obstetric_neurologic_danger')
            evidence.append('Grossesse avec signes neurologiques préoccupants')
        elif _any(text, (
            r'douleur abdominale (?:forte|intense|severe)', r'douleur pelvienne (?:forte|intense|severe)',
            r'perte de liquide',
        )):
            floor = 'P2'
            review = True
            evidence.append('Grossesse avec symptôme significatif nécessitant une évaluation prioritaire')

    age = p.age_years
    if age is not None and age < 12:
        pediatric_danger = _any(text, (
            r'ne boit plus', r'n arrive plus a boire', r'incapable de boire', r'tres somnolent',
            r'difficile a reveiller', r'levres? bleues?', r'convuls', r'respire a peine',
            r'tirage respiratoire', r'ne repond plus',
        ))
        if pediatric_danger:
            emergency = True
            codes.append('pediatric_danger_sign')
            evidence.append('Enfant avec signe général de danger')
        elif _any(text, (r'\bfievre\b', r'vomit', r'diarrh')):
            floor = floor or 'P2'
            review = True
            evidence.append('Enfant symptomatique : seuil de prudence abaissé')

    if age is not None and age >= 65 and _any(text, (
        r'confus', r'desorient', r'essouff', r'douleur thoracique', r'tres faible',
    )):
        floor = floor or 'P2'
        review = True
        evidence.append('Personne âgée avec symptôme potentiellement à risque')

    return PopulationSafetyResult(emergency, floor, tuple(codes), tuple(evidence), review)
