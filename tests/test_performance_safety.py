from domain.models import IntakeAnswers, PatientProfile
from services.triage_service import TriageService
from llm.triage_assessor import TriageAssessor


def make_intake(severity=None):
    return IntakeAnswers(
        complaint_text='J ai mal à la tête depuis ce matin',
        duration='Moins de 24 heures',
        associated_signs=['Maux de tête'],
        medical_history=['Aucun antécédent'],
        patient=PatientProfile(age_years=30, sex='female', pregnant=False),
        severity_answers=severity or {},
    )


def test_direct_p1_never_calls_llm(monkeypatch):
    service = TriageService()

    def fail_if_called(_):
        raise AssertionError('Le LLM ne doit pas être appelé pour un P1 direct')

    monkeypatch.setattr(service.assessor, 'assess', fail_if_called)
    result = service.triage(make_intake({'severe_breathing': True}))
    assert result.priority.value == 'P1'
    assert result.llm_used is False
    assert result.metadata['llm_trace']['skipped'] == 'llm_not_called_for_direct_p1'


def test_compact_payload_excludes_nonessential_fields():
    intake = make_intake({'severe_breathing': False, 'head_trauma': False})
    payload = TriageAssessor._compact_payload(intake)
    assert payload['severity_answers'] == {'severe_breathing': False, 'head_trauma': False}
    assert 'attachment_present' not in payload
    assert 'province' not in payload['patient']
    assert 'weight_kg' not in payload['patient']
    assert set(payload['patient']) == {
        'age_years', 'sex', 'pregnant', 'pregnancy_weeks', 'temperature_c'
    }
