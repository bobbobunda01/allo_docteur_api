from domain.models import IntakeAnswers, PatientProfile
from services.triage_service import TriageService


def test_critical_text_short_circuits_llm(monkeypatch):
    service = TriageService()

    def fail_if_called(*args, **kwargs):
        raise AssertionError('LLM should not be called for direct text P1')

    monkeypatch.setattr(service.assessor, 'assess', fail_if_called)
    intake = IntakeAnswers(
        complaint_text="J'ai un poids sur la poitrine et je respire difficilement",
        duration='Moins de 24 heures',
        associated_signs=['Essoufflement'],
        patient=PatientProfile(age_years=68, sex='male'),
        severity_answers={},
    )
    decision = service.triage(intake)
    assert decision.priority.value == 'P1'
    assert decision.metadata['text_safety_override'] is True
    assert decision.llm_used is False
