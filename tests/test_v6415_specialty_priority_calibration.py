from clinical.specialty import sanitize_specialty
from domain.enums import Priority
from domain.models import LLMAssessment
from llm.prompts import ASSESSOR_PROMPT


def assessment(primary: str, alternatives=None):
    return LLMAssessment(
        chief_complaint='test', clinical_summary='test', facts=[], priority=Priority.P1,
        orientation='Urgences', primary_specialty=primary,
        alternative_specialties=alternatives or [], possible_conditions=[], reasons=[],
        what_to_do_now=[], worsening_signs=[], missing_information=[], uncertainty='moderate',
        requires_human_review=False, detected_severity_signs=[], severity_evidence=[], contradictions=[]
    )


def test_p1_llm_specialty_wins_over_generic_respiratory_mapping():
    result = sanitize_specialty(
        assessment('Gynécologie-obstétrique'), Priority.P1,
        triggered_severity_codes=['severe_breathing'], llm_specialty_available=True,
    )
    assert result.primary_specialty == 'Gynécologie-obstétrique'
    assert 'Pneumologie' in result.alternative_specialties
    assert result.emergency_first is True


def test_p1_fallback_keeps_deterministic_safety_mapping():
    result = sanitize_specialty(
        assessment('Médecine d’urgence'), Priority.P1,
        triggered_severity_codes=['severe_breathing'], llm_specialty_available=False,
    )
    assert result.primary_specialty == 'Pneumologie'
    assert result.emergency_first is True


def test_prompt_decouples_severity_from_specialty():
    assert 'Séparez deux décisions' in ASSESSOR_PROMPT
    assert 'Grossesse/post-partum' in ASSESSOR_PROMPT
    assert 'P2 vs P3' in ASSESSOR_PROMPT
    assert 'P3 vs P4' in ASSESSOR_PROMPT
    assert 'oreille bouchée juste après baignade' in ASSESSOR_PROMPT
