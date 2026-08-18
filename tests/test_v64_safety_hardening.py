from datetime import date

from clinical.text_safety_gate import evaluate_text_safety
from clinical.population_safety_gate import evaluate_population_safety
from clinical.epidemiology_safety_gate import evaluate_epidemiology_safety
from domain.models import EpidemiologicalContext, IntakeAnswers, PatientProfile


def test_negated_suicide_is_not_p1():
    r = evaluate_text_safety("Je ne veux pas mourir et je n'ai aucune envie de me suicider.", [])
    assert r.emergency is False


def test_poisoning_natural_language_is_p1():
    r = evaluate_text_safety("J'ai avalé du pesticide par accident.", [])
    assert 'poisoning' in r.triggered_codes


def test_severe_diarrhea_unable_to_drink_is_p1():
    r = evaluate_text_safety("J'ai une diarrhée très abondante et je n'arrive plus à boire ni garder de liquide.", [])
    assert 'severe_diarrhea_unable_to_drink' in r.triggered_codes


def test_pregnancy_neuro_danger_is_p1():
    intake = IntakeAnswers(
        complaint_text="Je suis enceinte, j'ai un mal de tête intense et je vois flou.",
        patient=PatientProfile(age_years=28, sex='female', pregnant=True, pregnancy_weeks=32),
    )
    r = evaluate_population_safety(intake)
    assert r.emergency is True
    assert 'obstetric_neurologic_danger' in r.triggered_codes


def test_child_fever_gets_prudence_floor():
    intake = IntakeAnswers(
        complaint_text="Il a de la fièvre depuis ce matin.",
        patient=PatientProfile(age_years=3, sex='male'),
    )
    r = evaluate_population_safety(intake)
    assert r.priority_floor == 'P2'


def test_active_cholera_alert_plus_diarrhea_sets_epi_floor():
    intake = IntakeAnswers(
        complaint_text='Diarrhée aqueuse depuis ce matin.',
        patient=PatientProfile(age_years=30),
        epidemiology=EpidemiologicalContext(
            country='RDC', active_health_alerts=['Choléra'], source_date=date.today().isoformat()
        ),
    )
    r = evaluate_epidemiology_safety(intake)
    assert r.priority_floor == 'P2'
    assert r.public_health_review is True


def test_stale_alert_does_not_raise_priority():
    intake = IntakeAnswers(
        complaint_text='Diarrhée aqueuse depuis ce matin.',
        patient=PatientProfile(age_years=30),
        epidemiology=EpidemiologicalContext(
            country='RDC', active_health_alerts=['Choléra'], source_date='2020-01-01'
        ),
    )
    r = evaluate_epidemiology_safety(intake)
    assert r.priority_floor is None
    assert r.stale_context is True
