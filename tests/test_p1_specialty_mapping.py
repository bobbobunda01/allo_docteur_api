import pytest

from domain.models import IntakeAnswers, LLMAssessment
from services.triage_service import TriageService


class FakeAssessor:
    def assess(self, intake):
        return LLMAssessment(
            chief_complaint='test', clinical_summary='test', facts=[], priority='P4',
            orientation='test', primary_specialty='Médecin généraliste', alternative_specialties=[],
            reasons=['test'], what_to_do_now=[], worsening_signs=[], missing_information=[],
            uncertainty='low', requires_human_review=False,
        ), 'llm', {'response_id': 'fake'}


@pytest.mark.parametrize(
    ('severity_code', 'expected_specialty'),
    [
        ('severe_breathing', 'Pneumologie'),
        ('chest_pressure', 'Cardiologie'),
        ('stroke_signs', 'Neurologie'),
        ('suicidal_or_extreme_psy', 'Psychiatrie'),
        ('open_fracture_or_major_accident', 'Chirurgie orthopédique'),
    ],
)
def test_p1_uses_deterministic_specialty(tmp_path, severity_code, expected_specialty):
    service = TriageService()
    service.assessor = FakeAssessor()
    service.audit.directory = tmp_path
    decision = service.triage(
        IntakeAnswers(complaint_text='test patient', severity_answers={severity_code: True})
    )
    assert decision.priority.value == 'P1'
    assert decision.specialty_orientation.primary_specialty == expected_specialty
