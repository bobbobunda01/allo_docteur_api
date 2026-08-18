from clinical.specialty import sanitize_specialty
from domain.enums import Priority
from domain.models import LLMAssessment
from services.triage_service import _llm_p4_requires_current_consultation

def assessment(priority=Priority.P4, orientation='Conseil et autosurveillance', primary='Ophtalmologie'):
    return LLMAssessment(chief_complaint='test',clinical_summary='test',facts=[],priority=priority,
        orientation=orientation,primary_specialty=primary,alternative_specialties=[],possible_conditions=[],
        reasons=[],what_to_do_now=[],worsening_signs=[],missing_information=[],uncertainty='low',
        requires_human_review=False,detected_severity_signs=[],severity_evidence=[],contradictions=[],
        epidemiology_risk_notes=[],infection_control_precautions=[])

def test_p4_current_consultation_is_contradictory():
    assert _llm_p4_requires_current_consultation(assessment(orientation='Consultation programmée en Ophtalmologie')) is True

def test_conditional_consultation_does_not_force_p3():
    assert _llm_p4_requires_current_consultation(assessment(orientation='Autosurveillance ; consulter si persistance ou aggravation')) is False

def test_p4_specialty_does_not_create_scheduled_consultation():
    result=sanitize_specialty(assessment(primary='Ophtalmologie'),Priority.P4,[],llm_specialty_available=True)
    assert 'Consultation programmée' not in result.first_destination
    assert 'autosurveillance' in result.first_destination.casefold()

def test_p3_keeps_consultation_destination():
    result=sanitize_specialty(assessment(priority=Priority.P3,primary='Ophtalmologie'),Priority.P3,[],llm_specialty_available=True)
    assert result.first_destination == 'Consultation en Ophtalmologie'
