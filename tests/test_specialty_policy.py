from clinical.specialty import DEFAULT_EMERGENCY, DEFAULT_GENERAL, sanitize_specialty
from domain.enums import Priority
from domain.models import LLMAssessment


def assessment(primary='Gastro-entérologie', alternatives=None):
    return LLMAssessment(
        chief_complaint='test',
        clinical_summary='test',
        facts=[],
        priority=Priority.P2,
        orientation='test',
        primary_specialty=primary,
        alternative_specialties=alternatives or [],
        reasons=[],
        what_to_do_now=[],
        worsening_signs=[],
        missing_information=[],
        uncertainty='low',
        requires_human_review=False,
    )


def test_p1_uses_adapted_specialist_and_emergency_destination():
    result = sanitize_specialty(assessment('Cardiologie'), Priority.P1, [])
    assert result.primary_specialty == 'Cardiologie'
    assert result.first_destination == "Urgences / hôpital le plus proche"
    assert result.emergency_first is True
    assert DEFAULT_EMERGENCY in result.alternative_specialties


def test_p1_defaults_to_emergency_medicine_for_invalid_specialty():
    result = sanitize_specialty(assessment('Spécialité inventée'), Priority.P1, [])
    assert result.primary_specialty == DEFAULT_EMERGENCY


def test_p2_keeps_valid_llm_specialty():
    result = sanitize_specialty(
        assessment('Gastro-entérologie'),
        Priority.P2,
        [],
    )
    assert result.primary_specialty == 'Gastro-entérologie'
    assert result.first_destination == 'Consultation médicale prioritaire'


def test_p3_keeps_valid_llm_specialty():
    result = sanitize_specialty(
        assessment('Dentisterie', ['Médecin généraliste']),
        Priority.P3,
        [],
    )
    assert result.primary_specialty == 'Dentisterie'
    assert result.first_destination == 'Consultation en Dentisterie'


def test_p4_keeps_valid_llm_specialty():
    result = sanitize_specialty(
        assessment('Dermatologie'),
        Priority.P4,
        [],
    )
    assert result.primary_specialty == 'Dermatologie'
    assert result.first_destination == 'Conseil / autosurveillance ; recours à Dermatologie si persistance, récidive ou aggravation'


def test_invalid_specialty_falls_back_to_generalist_for_p2_p3_p4():
    for priority in (Priority.P2, Priority.P3, Priority.P4):
        result = sanitize_specialty(
            assessment('Spécialité inventée'),
            priority,
            [],
        )
        assert result.primary_specialty == DEFAULT_GENERAL


def test_non_first_line_specialty_falls_back_to_generalist():
    result = sanitize_specialty(
        assessment('Radiologie'),
        Priority.P3,
        [],
    )
    assert result.primary_specialty == DEFAULT_GENERAL


def test_valid_alternatives_are_preserved_without_duplicates():
    result = sanitize_specialty(
        assessment(
            'Ophtalmologie',
            ['Médecin généraliste', 'Neurologie', 'Fausse spécialité'],
        ),
        Priority.P3,
        [],
    )
    assert result.primary_specialty == 'Ophtalmologie'
    assert 'Neurologie' in result.alternative_specialties
    assert all(x != 'Fausse spécialité' for x in result.alternative_specialties)
