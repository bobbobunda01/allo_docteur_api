from __future__ import annotations

from domain.enums import Priority
from domain.models import IntakeAnswers, LLMAssessment
from clinical.text_safety_gate import evaluate_text_safety
from clinical.population_safety_gate import evaluate_population_safety
from clinical.epidemiology_safety_gate import evaluate_epidemiology_safety


def fallback_assessment(intake: IntakeAnswers) -> LLMAssessment:
    """Mode dégradé conservateur : ne prétend pas remplacer le raisonnement LLM."""
    text_gate = evaluate_text_safety(intake.complaint_text, intake.associated_signs)
    pop_gate = evaluate_population_safety(intake)
    epi_gate = evaluate_epidemiology_safety(intake)

    detected = list(text_gate.triggered_codes) + list(pop_gate.triggered_codes)
    evidence = list(text_gate.evidence) + list(pop_gate.evidence) + list(epi_gate.evidence)
    if detected or pop_gate.emergency:
        priority = Priority.P1
        orientation = "Urgences / hôpital le plus proche"
        reasons = evidence[:5] or ['Un signe de danger a été reconnu localement.']
    else:
        # Sans LLM, ne pas rassurer excessivement : P2 par défaut pour un cas symptomatique.
        priority = Priority.P2
        orientation = 'Consultation médicale prioritaire'
        reasons = ['Le moteur intelligent est indisponible ; une orientation prudente est appliquée.']
        if epi_gate.evidence:
            reasons.extend(epi_gate.evidence[:2])

    return LLMAssessment(
        chief_complaint=intake.complaint_text,
        clinical_summary='Évaluation limitée : le LLM est indisponible. La couche locale de sécurité a appliqué une orientation conservatrice.',
        facts=[], priority=priority, orientation=orientation,
        primary_specialty='Médecine d’urgence' if priority == Priority.P1 else 'Médecin généraliste',
        alternative_specialties=['Médecine interne'], possible_conditions=[], reasons=reasons[:5],
        what_to_do_now=['Consultez selon l’orientation indiquée.'], worsening_signs=[],
        missing_information=['Raisonnement clinique LLM indisponible'], uncertainty='high', requires_human_review=True,
        detected_severity_signs=detected[:17], severity_evidence=evidence[:6], contradictions=[],
    )
