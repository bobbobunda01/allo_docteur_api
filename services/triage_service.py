from __future__ import annotations

from audit.logger import AuditLogger
from clinical.severity_gate import evaluate_severity
from clinical.specialty import sanitize_specialty
from clinical.text_safety_gate import evaluate_text_safety
from clinical.population_safety_gate import evaluate_population_safety
from clinical.epidemiology_safety_gate import evaluate_epidemiology_safety
from domain.enums import PRIORITY_META, PRIORITY_RANK, Priority
from domain.models import IntakeAnswers, PublicTriageResponse, TriageDecision
from llm.fallback import fallback_assessment
from llm.triage_assessor import TriageAssessor

DEFAULT_WARNING_SIGNS = [
    'Difficulté importante à respirer ou sensation d’étouffement',
    'Perte de connaissance, confusion soudaine ou convulsions',
    'Douleur thoracique intense ou faiblesse soudaine d’un côté',
    'Saignement incontrôlable ou aggravation rapide',
]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _build_p1_message(evidence: list[str]) -> str:
    if evidence:
        return ('Des signes nécessitant une prise en charge immédiate ont été détectés : '
                f"{'; '.join(evidence[:3])}. Rendez-vous sans délai aux urgences ou à l’hôpital le plus proche.")
    return ('Un signe pouvant correspondre à une urgence immédiate a été signalé. '
            'Rendez-vous sans délai aux urgences ou à l’hôpital le plus proche.')


def _apply_priority_floor(priority: Priority, floor: str | None) -> Priority:
    if not floor:
        return priority
    floor_p = Priority(floor)
    return floor_p if PRIORITY_RANK[floor_p] > PRIORITY_RANK[priority] else priority


def _llm_p4_requires_current_consultation(assessment) -> bool:
    text = ' '.join(str(getattr(assessment, 'orientation', '') or '').casefold().split())
    if not text:
        return False
    conditional_markers = (
        'si persiste', 'si persistance', 'si récidive', 'si recidive',
        'si aggravation', "en cas d'aggravation", 'si besoin',
        'au besoin', 'si nécessaire', 'si necessaire',
    )
    if any(marker in text for marker in conditional_markers):
        return False
    current_consultation_markers = (
        'consultation', 'consulter', 'rendez-vous', 'rendez vous',
        'examen médical', 'examen medical', 'évaluation médicale',
        'evaluation medicale', 'suivi spécialisé', 'suivi specialise',
    )
    return any(marker in text for marker in current_consultation_markers)


class TriageService:
    def __init__(self) -> None:
        self.assessor = TriageAssessor()
        self.audit = AuditLogger()

    def triage(self, intake: IntakeAnswers) -> TriageDecision:
        # 1) Garde-fous déterministes, sans modifier le questionnaire existant.
        severity = evaluate_severity(intake.severity_answers)
        text_safety = evaluate_text_safety(intake.complaint_text, intake.associated_signs)
        population = evaluate_population_safety(intake)
        epidemiology = evaluate_epidemiology_safety(intake)

        questionnaire_signs = set(severity.triggered_codes)
        local_text_signs = set(text_safety.triggered_codes)
        population_signs = set(population.triggered_codes)
        local_direct_p1 = severity.emergency or text_safety.emergency or population.emergency

        local_evidence = list(severity.triggered_labels)
        local_evidence += list(text_safety.evidence)
        local_evidence += list(population.evidence)

        if local_direct_p1:
            # Un danger déjà reconnu localement ne doit jamais attendre le réseau.
            assessment = fallback_assessment(intake)
            mode = 'fallback'
            trace = {'skipped': 'llm_not_called_for_direct_p1', 'elapsed_seconds': 0.0,
                     'text_safety_code': text_safety.code}
            llm_signs: set[str] = set()
            llm_evidence: list[str] = []
            contradictions: list[str] = list(text_safety.contradictions)
        else:
            # 2) Le LLM conserve le raisonnement clinique riche et la détection secondaire P1.
            assessment, mode, trace = self.assessor.assess(intake)
            llm_signs = set(assessment.detected_severity_signs)
            llm_evidence = list(assessment.severity_evidence)
            contradictions = list(assessment.contradictions)

        # 3) Fusion protectrice : toute source de danger peut imposer P1.
        merged_signs = questionnaire_signs | local_text_signs | population_signs | llm_signs
        severity_override = bool(merged_signs)
        sources: list[str] = []
        if questionnaire_signs: sources.append('questionnaire')
        if local_text_signs: sources.append('free_text_local_gate')
        if population_signs: sources.append('population_safety')
        if llm_signs: sources.append('free_text_llm')

        evidence = _unique(local_evidence + llm_evidence)
        triggered_codes = sorted(merged_signs)

        # V6.4.1.3 : le LLM n'est plus structurellement empêché de retourner P1.
        # Deux chemins indépendants peuvent donc imposer P1 :
        #   1) un signe de sévérité détecté par une source locale ou par le LLM ;
        #   2) une décision P1 explicite du LLM, même si aucun code de sévérité
        #      n'a été extrait (filet de sécurité contre une incohérence d'extraction).
        llm_direct_p1 = (mode == 'llm' and assessment.priority == Priority.P1)
        semantic_priority_adjustment = False

        if severity_override or llm_direct_p1:
            priority = Priority.P1
            status = 'emergency_stop'
            if llm_direct_p1 and not severity_override:
                sources.append('llm_priority')
            reasons = evidence[:5] or assessment.reasons[:5] or [
                'Le raisonnement clinique a identifié une situation nécessitant une évaluation immédiate.'
            ]
        else:
            priority = assessment.priority

            # V6.4.1.6 : cohérence stricte P3/P4.
            if (
                mode == 'llm'
                and priority == Priority.P4
                and _llm_p4_requires_current_consultation(assessment)
            ):
                priority = Priority.P3
                semantic_priority_adjustment = True

            # Population et épidémiologie peuvent relever le plancher, jamais abaisser la priorité LLM.
            priority = _apply_priority_floor(priority, population.priority_floor)
            priority = _apply_priority_floor(priority, epidemiology.priority_floor)
            reasons = _unique(assessment.reasons + list(population.evidence) + list(epidemiology.evidence))[:5]
            if semantic_priority_adjustment:
                reasons = _unique(reasons + [
                    'Alignement sémantique : une consultation actuellement recommandée correspond au minimum à P3.'
                ])[:5]
            if mode == 'fallback': status = 'technical_fallback'
            elif assessment.requires_human_review or population.requires_human_review or epidemiology.public_health_review:
                status = 'human_review'
            else: status = 'completed'

        color, urgency, _ = PRIORITY_META[priority]
        specialty = sanitize_specialty(
            assessment, priority, triggered_severity_codes=triggered_codes,
            llm_specialty_available=(mode == 'llm'),
        )

        if priority == Priority.P1:
            message = _build_p1_message(evidence)
            actions = [
                'Rendez-vous immédiatement aux urgences ou à l’hôpital le plus proche.',
                'Ne conduisez pas vous-même ; faites-vous accompagner ou appelez les secours.',
            ]
        else:
            message = assessment.clinical_summary.strip()
            actions = assessment.what_to_do_now[:3] or [f'Suivez l’orientation indiquée : {specialty.first_destination}.']
            if epidemiology.infection_control_alert:
                actions = _unique(actions + [
                    'Avant ou à l’arrivée, signalez au service de santé le contexte d’alerte sanitaire indiqué dans le questionnaire.'
                ])[:4]

        warnings = assessment.worsening_signs[:4] or DEFAULT_WARNING_SIGNS
        requires_review = (
            assessment.requires_human_review or mode == 'fallback' or bool(contradictions)
            or population.requires_human_review or epidemiology.public_health_review
        )

        decision = TriageDecision(
            status=status, priority=priority, color=color, urgency_label=urgency,
            orientation=specialty.first_destination, message=message, reasons=reasons,
            severity_signs_triggered=triggered_codes, severity_evidence=evidence,
            contradictions=contradictions, severity_sources=sources,
            severity_override_applied=severity_override, specialty_orientation=specialty,
            clinical_facts=[], possible_conditions=([] if priority == Priority.P1 else assessment.possible_conditions[:3]),
            diagnostic_disclaimer='Ces hypothèses sont indicatives et doivent être confirmées par un médecin.',
            what_to_do_now=actions, worsening_signs=warnings,
            missing_information=assessment.missing_information,
            requires_human_review=requires_review, llm_used=mode == 'llm', extraction_mode=mode,
            metadata={
                'llm_trace': trace,
                'llm_priority_before_safety_fusion': assessment.priority.value,
                'severity_override_applied': severity_override,
                'llm_direct_p1': llm_direct_p1,
                'semantic_priority_adjustment_p4_to_p3': semantic_priority_adjustment,
                'severity_question_override': severity.emergency,
                'text_safety_override': text_safety.emergency,
                'text_safety_code': text_safety.code,
                'population_safety': {
                    'priority_floor': population.priority_floor,
                    'triggered_codes': list(population.triggered_codes),
                    'evidence': list(population.evidence),
                },
                'epidemiology_safety': {
                    'priority_floor': epidemiology.priority_floor,
                    'matched_alerts': list(epidemiology.matched_alerts),
                    'infection_control_alert': epidemiology.infection_control_alert,
                    'public_health_review': epidemiology.public_health_review,
                    'stale_context': epidemiology.stale_context,
                    'llm_risk_notes': assessment.epidemiology_risk_notes,
                    'llm_infection_control_precautions': assessment.infection_control_precautions,
                },
                'llm_detected_severity_signs': sorted(llm_signs),
                'severity_sources': sources, 'contradictions': contradictions,
                'uncertainty': assessment.uncertainty,
                'architecture': ('questionnaire unchanged + deterministic clinical/population/epidemiology safety '
                                 '+ compact LLM clinical reasoning + fail-safe fusion + composite safety patterns'),
                'version': '6.4.1.6',
            },
        )
        decision.audit_id = self.audit.write(intake, decision)
        return decision

    def triage_public(self, intake: IntakeAnswers) -> PublicTriageResponse:
        return self.triage(intake).to_public_response()
