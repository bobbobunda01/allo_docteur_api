from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import Priority


class PatientProfile(BaseModel):
    date_of_birth: str | None = None
    age_years: int | None = Field(default=None, ge=0, le=130)
    sex: Literal['female', 'male', 'other', 'unknown'] = 'unknown'
    pregnant: bool | None = None
    pregnancy_weeks: int | None = Field(default=None, ge=0, le=45)
    province: str | None = Field(default=None, max_length=120)
    weight_kg: float | None = Field(default=None, ge=1, le=350)
    height_m: float | None = Field(default=None, ge=0.35, le=2.6)
    temperature_c: float | None = Field(default=None, ge=30, le=45)

    @model_validator(mode='after')
    def normalize_profile(self):
        if self.sex != 'female':
            self.pregnant = False
            self.pregnancy_weeks = None
        elif self.pregnant is False:
            self.pregnancy_weeks = None

        if self.age_years is None and self.date_of_birth:
            parsed = None
            for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d'):
                try:
                    parsed = datetime.strptime(self.date_of_birth.strip(), fmt).date()
                    break
                except ValueError:
                    continue
            if parsed:
                today = date.today()
                years = today.year - parsed.year - ((today.month, today.day) < (parsed.month, parsed.day))
                if 0 <= years <= 130:
                    self.age_years = years
        return self


class EpidemiologicalContext(BaseModel):
    country: str | None = Field(default=None, max_length=120)
    administrative_region: str | None = Field(default=None, max_length=160)
    health_zone: str | None = Field(default=None, max_length=160)
    african_subregion: str | None = Field(default=None, max_length=80)
    environment: str | None = Field(default=None, max_length=80)
    season: str | None = Field(default=None, max_length=80)
    recent_travel: list[str] = Field(default_factory=list, max_length=10)
    endemic_conditions: list[str] = Field(default_factory=list, max_length=20)
    active_health_alerts: list[str] = Field(default_factory=list, max_length=20)
    source_date: str | None = Field(default=None, max_length=40)


class IntakeAnswers(BaseModel):
    complaint_text: str = Field(min_length=3, max_length=6000)
    duration: str | None = Field(default=None, max_length=120)
    associated_signs: list[str] = Field(default_factory=list, max_length=20)
    prior_consultation: str | None = Field(default=None, max_length=120)
    attachment_present: bool = False
    medical_history: list[str] = Field(default_factory=list, max_length=30)
    patient: PatientProfile = Field(default_factory=PatientProfile)
    severity_answers: dict[str, bool] = Field(default_factory=dict)
    epidemiology: EpidemiologicalContext = Field(default_factory=EpidemiologicalContext)

    @field_validator('complaint_text')
    @classmethod
    def clean_complaint(cls, value: str) -> str:
        return ' '.join(value.strip().split())


class ClinicalFact(BaseModel):
    code: str = Field(max_length=100)
    status: Literal['present', 'absent', 'possible', 'unknown']
    severity: Literal['mild', 'moderate', 'severe', 'unknown'] = 'unknown'
    location: str | None = Field(default=None, max_length=120)
    evidence: str | None = Field(default=None, max_length=500)


class LLMAssessment(BaseModel):
    chief_complaint: str = Field(max_length=500)
    clinical_summary: str = Field(max_length=1200)
    facts: list[ClinicalFact] = Field(default_factory=list, max_length=20)
    priority: Priority
    orientation: str = Field(max_length=250)
    primary_specialty: str = Field(max_length=120)
    alternative_specialties: list[str] = Field(default_factory=list, max_length=3)
    possible_conditions: list[str] = Field(default_factory=list, max_length=3)
    reasons: list[str] = Field(default_factory=list, max_length=5)
    what_to_do_now: list[str] = Field(default_factory=list, max_length=4)
    worsening_signs: list[str] = Field(default_factory=list, max_length=5)
    missing_information: list[str] = Field(default_factory=list, max_length=5)
    uncertainty: Literal['low', 'moderate', 'high'] = 'moderate'
    requires_human_review: bool = False
    detected_severity_signs: list[str] = Field(default_factory=list, max_length=17)
    severity_evidence: list[str] = Field(default_factory=list, max_length=6)
    contradictions: list[str] = Field(default_factory=list, max_length=6)
    epidemiology_risk_notes: list[str] = Field(default_factory=list, max_length=4)
    infection_control_precautions: list[str] = Field(default_factory=list, max_length=4)
    disclaimer: str = 'Orientation de pré-triage uniquement, pas diagnostic.'


class SpecialtyOrientation(BaseModel):
    first_destination: str
    primary_specialty: str
    alternative_specialties: list[str] = Field(default_factory=list, max_length=3)
    emergency_first: bool
    rationale: list[str] = Field(default_factory=list, max_length=3)


class PatientResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_id: str
    priority: Priority
    color: str
    urgency_label: str
    orientation: str
    specialty: str
    possible_conditions: list[str] = Field(default_factory=list, max_length=3)
    diagnostic_disclaimer: str = (
        'Ces hypothèses sont indicatives et doivent être confirmées par un médecin.'
    )
    summary: str
    reasons: list[str] = Field(default_factory=list, max_length=5)
    what_to_do_now: list[str] = Field(default_factory=list, max_length=4)
    warning_signs: list[str] = Field(default_factory=list, max_length=5)
    disclaimer: str = 'Pré-triage et orientation uniquement, pas diagnostic.'


class TechnicalSummary(BaseModel):
    audit_id: str | None = None
    llm_used: bool
    extraction_mode: Literal['llm', 'fallback']
    severity_override_applied: bool
    requires_human_review: bool
    uncertainty: Literal['low', 'moderate', 'high']


class PublicTriageResponse(BaseModel):
    patient_result: PatientResult
    technical: TechnicalSummary


class TriageDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_id: str = Field(default_factory=lambda: f'case-{uuid4().hex}')
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal['completed', 'emergency_stop', 'technical_fallback', 'human_review']
    priority: Priority
    color: str
    urgency_label: str
    orientation: str
    message: str
    reasons: list[str] = Field(default_factory=list)
    severity_signs_triggered: list[str] = Field(default_factory=list)
    severity_evidence: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    severity_sources: list[str] = Field(default_factory=list)
    severity_override_applied: bool = False
    specialty_orientation: SpecialtyOrientation
    clinical_facts: list[ClinicalFact] = Field(default_factory=list)
    possible_conditions: list[str] = Field(default_factory=list, max_length=3)
    diagnostic_disclaimer: str = (
        'Ces hypothèses sont indicatives et doivent être confirmées par un médecin.'
    )
    what_to_do_now: list[str] = Field(default_factory=list)
    worsening_signs: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    llm_used: bool = False
    extraction_mode: Literal['llm', 'fallback']
    audit_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_public_response(self) -> PublicTriageResponse:
        return PublicTriageResponse(
            patient_result=PatientResult(
                case_id=self.case_id,
                priority=self.priority,
                color=self.color,
                urgency_label=self.urgency_label,
                orientation=self.orientation,
                specialty=self.specialty_orientation.primary_specialty,
                possible_conditions=([] if self.priority == Priority.P1 else self.possible_conditions[:3]),
                diagnostic_disclaimer=self.diagnostic_disclaimer,
                summary=self.message,
                reasons=self.reasons[:5],
                what_to_do_now=self.what_to_do_now[:4],
                warning_signs=self.worsening_signs[:5],
            ),
            technical=TechnicalSummary(
                audit_id=self.audit_id,
                llm_used=self.llm_used,
                extraction_mode=self.extraction_mode,
                severity_override_applied=bool(self.metadata.get('severity_override_applied')),
                requires_human_review=self.requires_human_review,
                uncertainty=self.metadata.get('uncertainty', 'high'),
            ),
        )
