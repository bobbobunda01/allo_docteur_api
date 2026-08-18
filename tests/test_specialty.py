from domain.models import LLMAssessment
from clinical.specialty import sanitize_specialty, CATALOG
from domain.enums import Priority

def assessment(primary):
    return LLMAssessment(
        chief_complaint='x',clinical_summary='x',facts=[],priority='P3',orientation='Centre de santé',
        primary_specialty=primary,alternative_specialties=['Neurologie','Fausse spécialité'],
        reasons=[],what_to_do_now=[],worsening_signs=[],missing_information=[],uncertainty='low',requires_human_review=False,
    )

def test_unknown_specialty_is_rejected_to_default():
    result = sanitize_specialty(assessment('Fausse spécialité'), Priority.P3, 'Centre de santé')
    assert result.primary_specialty == 'Médecin généraliste'
    assert all(item in CATALOG for item in result.alternative_specialties)
