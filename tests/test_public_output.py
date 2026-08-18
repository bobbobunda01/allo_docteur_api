from domain.models import IntakeAnswers, LLMAssessment
from services.triage_service import TriageService


class FakeAssessor:
    def assess(self, intake):
        return LLMAssessment(
            chief_complaint='céphalée',
            clinical_summary='Maux de tête récents sans signe de sévérité déclaré.',
            facts=[],
            priority='P3',
            orientation='médecine générale',
            primary_specialty='Neurologie',
            alternative_specialties=['Médecine interne'],
            reasons=['Maux de tête récents'],
            what_to_do_now=['Consultez un médecin généraliste.'],
            worsening_signs=['Confusion ou perte de connaissance'],
            missing_information=['Température'],
            uncertainty='moderate',
            requires_human_review=False,
        ), 'llm', {'response_id': 'fake'}


def test_public_response_is_concise(tmp_path):
    service = TriageService()
    service.assessor = FakeAssessor()
    service.audit.directory = tmp_path
    response = service.triage_public(IntakeAnswers(complaint_text='mal à la tête'))
    payload = response.model_dump()
    assert set(payload) == {'patient_result', 'technical'}
    patient = payload['patient_result']
    assert 'clinical_facts' not in patient
    assert 'metadata' not in patient
    assert patient['specialty'] == 'Neurologie'


def test_age_is_derived_from_birth_date():
    intake = IntakeAnswers(
        complaint_text='douleur légère',
        patient={'date_of_birth': '12/09/1988', 'sex': 'female', 'pregnant': False},
    )
    assert intake.patient.age_years is not None
    assert 37 <= intake.patient.age_years <= 38
