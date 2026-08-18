from domain.enums import Priority
from domain.models import IntakeAnswers, LLMAssessment, PatientProfile
from services.triage_service import TriageService


def _assessment(**overrides):
    data = dict(
        chief_complaint='plainte',
        clinical_summary='Résumé clinique.',
        facts=[],
        priority='P2',
        orientation='',
        primary_specialty='Neurologie',
        alternative_specialties=[],
        possible_conditions=['AVC possible'],
        reasons=['Début brutal'],
        what_to_do_now=['Consulter rapidement'],
        worsening_signs=['Aggravation'],
        missing_information=[],
        uncertainty='moderate',
        requires_human_review=False,
        detected_severity_signs=['stroke_signs'],
        severity_evidence=['Bouche déviée', 'Bras gauche faible', 'Difficulté à parler'],
        contradictions=['Le texte est positif alors que la réponse fermée est négative.'],
    )
    data.update(overrides)
    return LLMAssessment(**data)


def test_llm_detected_stroke_overrides_p2(monkeypatch, tmp_path):
    service = TriageService()
    monkeypatch.setattr(service.assessor, 'assess', lambda intake: (_assessment(), 'llm', {}))
    monkeypatch.setattr(service.audit, 'write', lambda intake, decision: 'audit-test')

    intake = IntakeAnswers(
        complaint_text='Ma bouche est de travers, mon bras gauche est faible et je parle mal.',
        duration='Moins de 24 heures',
        patient=PatientProfile(age_years=69, sex='male'),
        severity_answers={'stroke_signs': False},
    )
    decision = service.triage(intake)

    assert decision.priority == Priority.P1
    assert 'stroke_signs' in decision.severity_signs_triggered
    assert decision.severity_override_applied is True
    assert 'free_text_llm' in decision.severity_sources or 'free_text_local_gate' in decision.severity_sources
    assert decision.possible_conditions == []


def test_no_severity_keeps_llm_priority(monkeypatch):
    service = TriageService()
    clean = _assessment(
        priority='P3',
        primary_specialty='Médecin généraliste',
        detected_severity_signs=[],
        severity_evidence=[],
        contradictions=[],
    )
    monkeypatch.setattr(service.assessor, 'assess', lambda intake: (clean, 'llm', {}))
    monkeypatch.setattr(service.audit, 'write', lambda intake, decision: 'audit-test')

    intake = IntakeAnswers(
        complaint_text='J ai un rhume léger depuis deux jours.',
        duration='1 à 3 jours',
        severity_answers={},
    )
    decision = service.triage(intake)
    assert decision.priority == Priority.P3
    assert decision.severity_override_applied is False
