from __future__ import annotations

import json
from pathlib import Path

from domain.enums import Priority
from domain.models import LLMAssessment, SpecialtyOrientation

_DATA_FILE = Path(__file__).resolve().parent.parent / 'data' / 'specialties.json'
CATALOG = set(json.loads(_DATA_FILE.read_text(encoding='utf-8'))['specialties'])

DEFAULT_GENERAL = 'Médecin généraliste'
DEFAULT_EMERGENCY = 'Médecine d’urgence'

# Ces spécialités ne doivent pas être proposées comme destination clinique initiale
# au patient, même si le LLM les produit.
NON_FIRST_LINE_SPECIALTIES = {
    'Anatomie pathologie',
    'Anesthésiologie',
    'Médecine légale',
    'Radiologie',
}

# Pour P1 uniquement, le backend peut sécuriser la spécialité à partir d'un red flag
# déterministe. La destination reste dans tous les cas les urgences.
SEVERITY_SPECIALTY = {
    'severe_breathing': 'Pneumologie',
    'chest_pressure': 'Cardiologie',
    'severe_diarrhea_unable_to_drink': 'Gastro-entérologie',
    'severe_dehydration': 'Médecine d’urgence',
    'stroke_signs': 'Neurologie',
    'loss_of_consciousness': 'Médecine d’urgence',
    'sudden_confusion': 'Neurologie',
    'uncontrollable_bleeding': 'Chirurgie générale',
    'board_like_abdomen': 'Chirurgie générale',
    'fever_with_neck_stiffness': 'Infectiologie',
    'seizures': 'Neurologie',
    'rash_with_fever': 'Infectiologie',
    'poisoning': 'Médecine d’urgence',
    'severe_burn': 'Chirurgie plastique et reconstructive',
    'suicidal_or_extreme_psy': 'Psychiatrie',
    'open_fracture_or_major_accident': 'Chirurgie orthopédique',
    'head_trauma': 'Neurochirurgie',
}


def _valid_first_line(name: str | None) -> bool:
    return bool(name and name in CATALOG and name not in NON_FIRST_LINE_SPECIALTIES)


def _deduplicate(
    values: list[str],
    excluded: set[str] | None = None,
    limit: int = 3,
) -> list[str]:
    excluded = excluded or set()
    result: list[str] = []

    for value in values:
        if (
            value in CATALOG
            and value not in NON_FIRST_LINE_SPECIALTIES
            and value not in excluded
            and value not in result
        ):
            result.append(value)

        if len(result) >= limit:
            break

    return result


def _scheduled_destination(priority: Priority, primary: str) -> str:
    """
    Le niveau d'urgence et la spécialité sont deux décisions distinctes.
    La spécialité proposée par le LLM est conservée lorsqu'elle est valide.
    """
    if priority == Priority.P2:
        return 'Consultation médicale prioritaire'

    if priority == Priority.P3:
        if primary == DEFAULT_GENERAL:
            return 'Médecin généraliste'
        return f'Consultation en {primary}'

    # P4
    # V6.4.1.6 : aucune consultation n'est actuellement requise en P4.
    if primary == DEFAULT_GENERAL:
        return 'Conseil / autosurveillance avec recours au médecin généraliste si nécessaire'
    return f'Conseil / autosurveillance ; recours à {primary} si persistance, récidive ou aggravation'


def sanitize_specialty(
    assessment: LLMAssessment,
    priority: Priority,
    triggered_severity_codes: list[str] | None = None,
    llm_specialty_available: bool = False,
) -> SpecialtyOrientation:
    """
    Politique V6.4.1.2
    -----------------
    - La PRIORITÉ reste sécurisée par le backend.
    - Pour P2/P3/P4, la SPÉCIALITÉ vient du LLM lorsqu'elle appartient au catalogue.
    - Le backend valide/filtre la spécialité, mais ne la remplace plus par
      "Médecin généraliste" uniquement parce que le cas est P3 ou P4.
    - "Médecin généraliste" devient un fallback si la proposition LLM est absente,
      invalide ou non admissible en première ligne.
    - Pour P1, la destination reste toujours les urgences et un mapping déterministe
      peut sécuriser la spécialité liée au red flag.
    """
    triggered_severity_codes = triggered_severity_codes or []

    proposed = (
        assessment.primary_specialty
        if _valid_first_line(assessment.primary_specialty)
        else None
    )

    proposed_alternatives = _deduplicate(
        assessment.alternative_specialties,
        excluded={proposed} if proposed else set(),
    )

    # P1 : le niveau de sécurité prime.
    if priority == Priority.P1:
        deterministic = next(
            (
                SEVERITY_SPECIALTY[code]
                for code in triggered_severity_codes
                if code in SEVERITY_SPECIALTY
            ),
            None,
        )

        # V6.4.1.5 : séparer la détection de gravité du routage de spécialité.
        # Quand le LLM a réellement raisonné sur le cas, sa spécialité clinique
        # valide prime sur le mapping générique du red flag. Cela évite par
        # exemple de transformer automatiquement toute détresse respiratoire
        # obstétricale, toxique, ORL ou allergique en Pneumologie.
        # En mode fallback, le mapping déterministe reste le filet de sécurité.
        llm_proposed = proposed if proposed != DEFAULT_GENERAL else None
        if llm_specialty_available and llm_proposed:
            primary = llm_proposed
        else:
            primary = deterministic or llm_proposed or DEFAULT_EMERGENCY

        alternatives = _deduplicate(
            ([deterministic] if deterministic and deterministic != primary else [])
            + ([DEFAULT_EMERGENCY] if primary != DEFAULT_EMERGENCY else [])
            + ([proposed] if proposed and proposed != primary else [])
            + proposed_alternatives,
            excluded={primary},
        )

        return SpecialtyOrientation(
            first_destination='Urgences / hôpital le plus proche',
            primary_specialty=primary,
            alternative_specialties=alternatives,
            emergency_first=True,
            rationale=[
                'La présence d’un signe de sévérité impose une consultation immédiate.',
                'La gravité et la spécialité sont découplées : la spécialité clinique LLM valide est conservée ; le mapping de red flag reste un filet de sécurité en fallback.',
            ],
        )

    # P2 / P3 / P4 :
    # le LLM choisit la spécialité et le backend ne fait que la valider.
    primary = proposed or DEFAULT_GENERAL

    alternatives = _deduplicate(
        proposed_alternatives
        + ([DEFAULT_GENERAL] if primary != DEFAULT_GENERAL else []),
        excluded={primary},
    )

    if primary == DEFAULT_GENERAL:
        rationale = [
            'Aucune spécialité clinique valide et suffisamment spécifique n’a été retenue.',
            'Le médecin généraliste est utilisé comme orientation de recours.',
        ]
    else:
        rationale = [
            'La spécialité clinique proposée par le LLM a été validée dans le catalogue AlloDocteur.',
            'Le niveau de priorité ne remplace pas automatiquement cette spécialité par un médecin généraliste.',
        ]

    return SpecialtyOrientation(
        first_destination=_scheduled_destination(priority, primary),
        primary_specialty=primary,
        alternative_specialties=alternatives,
        emergency_first=False,
        rationale=rationale,
    )
