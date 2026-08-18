from clinical.specialty import sanitize_specialty
from domain.enums import Priority
from domain.models import LLMAssessment


def test_dental_p3_is_not_overwritten_by_generalist():
    assessment = LLMAssessment(
        chief_complaint='douleur dentaire',
        clinical_summary='douleur dentaire gauche depuis quatre jours',
        facts=[],
        priority=Priority.P3,
        orientation='Consultation dentaire',
        primary_specialty='Dentisterie',
        alternative_specialties=['Médecin généraliste'],
        reasons=['plainte dentaire localisée'],
        what_to_do_now=['consultation dentaire'],
        worsening_signs=['gonflement du visage'],
        missing_information=[],
        uncertainty='low',
        requires_human_review=False,
    )

    result = sanitize_specialty(assessment, Priority.P3, [])

    assert result.primary_specialty == 'Dentisterie'
    assert result.first_destination == 'Consultation en Dentisterie'
