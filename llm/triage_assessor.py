from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

from app.settings import settings
from clinical.specialty import CATALOG
from domain.models import IntakeAnswers, LLMAssessment
from geography.africa_context import build_africa_context

from .fallback import fallback_assessment
from .prompts import ASSESSOR_PROMPT
from .schemas import V64_ASSESSMENT_SCHEMA

logger = logging.getLogger(__name__)


class TriageAssessor:
    def __init__(self) -> None:
        self.enabled = (
            settings.allodocteur_llm_enabled
            and bool(settings.openai_api_key)
            and OpenAI is not None
        )
        timeout = httpx.Timeout(
            connect=settings.openai_connect_timeout_seconds,
            read=settings.openai_read_timeout_seconds,
            write=settings.openai_write_timeout_seconds,
            pool=settings.openai_pool_timeout_seconds,
        )
        self.client = (
            OpenAI(
                api_key=settings.openai_api_key,
                timeout=timeout,
                max_retries=settings.openai_max_retries,
            )
            if self.enabled
            else None
        )

    @staticmethod
    def _compact_payload(intake: IntakeAnswers) -> dict[str, Any]:
        patient = intake.patient
        return {
            'complaint_text': intake.complaint_text,
            'duration': intake.duration,
            'associated_signs': intake.associated_signs,
            'medical_history': intake.medical_history,
            'patient': {
                'age_years': patient.age_years,
                'sex': patient.sex,
                'pregnant': patient.pregnant,
                'pregnancy_weeks': patient.pregnancy_weeks,
                'temperature_c': patient.temperature_c,
            },
            'severity_answers': intake.severity_answers,
            'epidemiological_context': build_africa_context(
                country=intake.epidemiology.country,
                administrative_region=(
                    intake.epidemiology.administrative_region or patient.province
                ),
                health_zone=intake.epidemiology.health_zone,
                environment=intake.epidemiology.environment,
                season=intake.epidemiology.season,
                recent_travel=intake.epidemiology.recent_travel,
                endemic_conditions=intake.epidemiology.endemic_conditions,
                active_health_alerts=intake.epidemiology.active_health_alerts,
                source_date=intake.epidemiology.source_date,
            ),
            'allowed_specialties': sorted(CATALOG),
        }

    @staticmethod
    def _usage_trace(response: Any) -> dict[str, int | None]:
        usage = getattr(response, 'usage', None)
        if usage is None:
            return {}
        output_details = getattr(usage, 'output_tokens_details', None)
        return {
            'input_tokens': getattr(usage, 'input_tokens', None),
            'output_tokens': getattr(usage, 'output_tokens', None),
            'reasoning_tokens': getattr(output_details, 'reasoning_tokens', None),
            'total_tokens': getattr(usage, 'total_tokens', None),
        }

    def assess(self, intake: IntakeAnswers) -> tuple[LLMAssessment, str, dict]:
        total_started = time.perf_counter()
        if not self.enabled:
            trace = {
                'stage': 'configuration',
                'error': 'disabled_or_missing_key',
                'message': 'LLM désactivé, SDK absent ou clé API manquante.',
                'elapsed_seconds': 0.0,
            }
            logger.warning('LLM disabled or missing configuration')
            return fallback_assessment(intake), 'fallback', trace

        payload_started = time.perf_counter()
        payload = self._compact_payload(intake)
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        payload_elapsed = time.perf_counter() - payload_started
        api_started = time.perf_counter()

        logger.info(
            'OpenAI request start model=%s payload_chars=%d timeout_read=%s retries=%s '
            'max_output_tokens=%s reasoning_effort=%s verbosity=%s',
            settings.openai_model,
            len(payload_json),
            settings.openai_read_timeout_seconds,
            settings.openai_max_retries,
            settings.openai_max_output_tokens,
            settings.openai_reasoning_effort,
            settings.openai_text_verbosity,
        )

        response = None
        try:
            response = self.client.responses.create(
                model=settings.openai_model,
                instructions=ASSESSOR_PROMPT,
                input=payload_json,
                max_output_tokens=settings.openai_max_output_tokens,
                reasoning={'effort': settings.openai_reasoning_effort},
                text={
                    'verbosity': settings.openai_text_verbosity,
                    'format': {
                        'type': 'json_schema',
                        'name': 'allodocteur_v64_clinical_epidemiological_safety_assessment',
                        'strict': True,
                        'schema': V64_ASSESSMENT_SCHEMA,
                    },
                },
            )
            api_elapsed = time.perf_counter() - api_started
            usage_trace = self._usage_trace(response)
            if usage_trace:
                logger.info(
                    'OpenAI usage input=%s output=%s reasoning=%s total=%s',
                    usage_trace.get('input_tokens'),
                    usage_trace.get('output_tokens'),
                    usage_trace.get('reasoning_tokens'),
                    usage_trace.get('total_tokens'),
                )

            status = getattr(response, 'status', None)
            if status and status != 'completed':
                details = getattr(response, 'incomplete_details', None)
                reason = getattr(details, 'reason', 'unknown') if details else 'unknown'
                raise RuntimeError(
                    f'Réponse LLM incomplète: status={status}, reason={reason}, '
                    f'usage={usage_trace}'
                )

            output_text = (getattr(response, 'output_text', '') or '').strip()
            if not output_text:
                raise RuntimeError('Le LLM a renvoyé une sortie vide.')

            parse_started = time.perf_counter()
            raw = json.loads(output_text)
            assessment = LLMAssessment(
                chief_complaint=intake.complaint_text,
                clinical_summary=str(raw['clinical_summary'])[:800],
                facts=[],
                priority=raw['priority'],
                orientation='',
                primary_specialty=str(raw['primary_specialty'])[:120],
                alternative_specialties=[],
                possible_conditions=[str(item)[:160] for item in raw['possible_conditions'][:2]],
                reasons=[str(item)[:240] for item in raw['reasons'][:3]],
                what_to_do_now=[str(item)[:260] for item in raw['what_to_do_now'][:2]],
                worsening_signs=[str(item)[:260] for item in raw['worsening_signs'][:4]],
                missing_information=[],
                uncertainty=str(raw['uncertainty']),
                requires_human_review=bool(raw['requires_human_review']) or bool(raw['contradictions']),
                detected_severity_signs=[
                    str(item) for item in raw['detected_severity_signs'][:17]
                ],
                severity_evidence=[
                    str(item)[:300] for item in raw['severity_evidence'][:4]
                ],
                contradictions=[str(item)[:400] for item in raw['contradictions'][:6]],
                epidemiology_risk_notes=[str(item)[:300] for item in raw['epidemiology_risk_notes'][:4]],
                infection_control_precautions=[str(item)[:300] for item in raw['infection_control_precautions'][:4]],
            )
            parse_elapsed = time.perf_counter() - parse_started
            total_elapsed = time.perf_counter() - total_started
            trace = {
                'response_id': getattr(response, 'id', None),
                'model': settings.openai_model,
                'status': status or 'completed',
                'usage': usage_trace,
                'timings': {
                    'payload_seconds': round(payload_elapsed, 4),
                    'openai_seconds': round(api_elapsed, 4),
                    'parse_validation_seconds': round(parse_elapsed, 4),
                    'total_seconds': round(total_elapsed, 4),
                },
                'payload_characters': len(payload_json),
                'output_characters': len(output_text),
                'reasoning_effort': settings.openai_reasoning_effort,
                'text_verbosity': settings.openai_text_verbosity,
            }
            logger.info(
                'OpenAI request completed response_id=%s total=%.3fs',
                trace['response_id'],
                total_elapsed,
            )
            return assessment, 'llm', trace

        except Exception as exc:
            total_elapsed = time.perf_counter() - total_started
            usage_trace = self._usage_trace(response) if response is not None else {}
            trace = {
                'stage': 'openai_or_validation',
                'error': type(exc).__name__,
                'message': str(exc),
                'usage': usage_trace,
                'timings': {
                    'payload_seconds': round(payload_elapsed, 4),
                    'total_seconds': round(total_elapsed, 4),
                },
                'payload_characters': len(payload_json),
                'reasoning_effort': settings.openai_reasoning_effort,
                'text_verbosity': settings.openai_text_verbosity,
            }
            logger.exception('LLM assessment failed after %.3fs', total_elapsed)
            return fallback_assessment(intake), 'fallback', trace
