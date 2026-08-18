from domain.models import EpidemiologicalContext, IntakeAnswers, PatientProfile
from llm.triage_assessor import TriageAssessor


def test_compact_payload_includes_structured_epidemiology():
    intake = IntakeAnswers(
        complaint_text='Fièvre, courbatures et mal de tête',
        duration='Moins de 24 heures',
        associated_signs=['Fièvre', 'Maux de tête'],
        patient=PatientProfile(age_years=30, sex='male', province='Kinshasa'),
        epidemiology=EpidemiologicalContext(
            country='RDC',
            administrative_region='Kinshasa',
            health_zone='Gombe',
            environment='Urbain',
        ),
    )
    payload = TriageAssessor._compact_payload(intake)
    context = payload['epidemiological_context']
    assert context['country'] == 'RDC'
    assert context['african_subregion'] == 'Afrique centrale'
    assert context['health_zone'] == 'Gombe'
    assert context['endemic_conditions'] == []
