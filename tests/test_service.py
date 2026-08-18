from domain.enums import Priority
from domain.models import IntakeAnswers, LLMAssessment
from services.triage_service import TriageService

class FakeAssessor:
    def assess(self, intake):
        return LLMAssessment(
            chief_complaint='test', clinical_summary='cas non urgent', facts=[], priority='P4',
            orientation='Médecin généraliste / consultation standard',
            primary_specialty='Médecin généraliste', alternative_specialties=[],
            reasons=['test'], what_to_do_now=[], worsening_signs=[], missing_information=[],
            uncertainty='low', requires_human_review=False,
        ), 'llm', {'response_id':'fake'}

def test_severity_overrides_llm_p4_to_p1(tmp_path, monkeypatch):
    service = TriageService()
    service.assessor = FakeAssessor()
    service.audit.directory = tmp_path
    intake = IntakeAnswers(complaint_text='test patient', severity_answers={'seizures':True})
    decision = service.triage(intake)
    assert decision.priority == Priority.P1
    assert decision.status == 'emergency_stop'
    assert decision.specialty_orientation.primary_specialty == "Neurologie"

def test_no_questions_or_kb_in_output(tmp_path):
    service = TriageService(); service.assessor = FakeAssessor(); service.audit.directory = tmp_path
    decision = service.triage(IntakeAnswers(complaint_text='test patient'))
    payload = decision.model_dump()
    assert 'questions' not in payload
    assert 'triggered_rules' not in payload
    assert 'decisive_rule' not in payload
    assert 'kb_version' not in payload.get('metadata', {})
