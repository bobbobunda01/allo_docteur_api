from domain.enums import Priority
from domain.models import PatientResult


def test_possible_conditions_are_limited_to_three():
    patient = PatientResult(
        case_id='case-test',
        priority=Priority.P2,
        color='ORANGE',
        urgency_label='Consultation prioritaire',
        orientation='Consultation médicale prioritaire',
        specialty='Oto-rhino-laryngologie (ORL)',
        possible_conditions=['Pharyngite', 'Angine', 'Infection ORL'],
        summary='Douleur de gorge récente.',
    )
    assert len(patient.possible_conditions) == 3
    assert 'confirmées par un médecin' in patient.diagnostic_disclaimer


def test_p1_public_response_hides_possible_conditions():
    from domain.models import SpecialtyOrientation, TriageDecision

    decision = TriageDecision(
        status='emergency_stop',
        priority=Priority.P1,
        color='ROUGE',
        urgency_label='Urgence vitale',
        orientation='Urgences / hôpital le plus proche',
        message='Urgence immédiate.',
        reasons=['Signe critique'],
        specialty_orientation=SpecialtyOrientation(
            first_destination='Urgences / hôpital le plus proche',
            primary_specialty='Médecine d’urgence',
            alternative_specialties=[],
            emergency_first=True,
            rationale=['Urgence'],
        ),
        possible_conditions=['Infarctus possible'],
        what_to_do_now=['Urgences'],
        worsening_signs=[],
        extraction_mode='fallback',
    )
    public = decision.to_public_response()
    assert public.patient_result.possible_conditions == []
