from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class TriagePayload(BaseModel):
    """Payload API minimal mais compatible avec le moteur AlloDocteur.

    Remarque importante : None signifie inconnu/non renseigné, pas forcément False.
    """

    complaint_text: str = Field(..., min_length=2, max_length=1200, description="Plainte principale en texte libre")
    duration: str | None = Field(default=None, description="Libellé durée utilisé par le moteur, ex. '1 à 3 jours'")
    duration_bucket: str | None = Field(default=None, description="Option API : lt_24h, 1_3_days, 4_7_days...")
    associated_signs: list[str] = Field(default_factory=list)
    medical_history: list[str] = Field(default_factory=list)
    already_consulted: str | None = None
    attachment_present: bool | None = False

    date_of_birth: str | None = Field(default=None, description="JJ/MM/AAAA")
    sex: Literal["Homme", "Femme", "Autre", "Inconnu"] | str | None = None
    province: str | None = None
    weight_kg: float | None = Field(default=None, ge=0, le=400)
    height_m: float | None = Field(default=None, ge=0, le=3)
    pregnant: bool | None = None

    immediate_red_flags: dict[str, bool | None] = Field(default_factory=dict)
    dynamic_answers: dict[str, Any] = Field(default_factory=dict)

    @field_validator("complaint_text")
    @classmethod
    def clean_complaint(cls, v: str) -> str:
        return " ".join(v.strip().split())

    @field_validator("associated_signs", "medical_history")
    @classmethod
    def clean_list(cls, v: list[str]) -> list[str]:
        return [str(x).strip() for x in v if str(x).strip()]

    @model_validator(mode="after")
    def normalize_duration(self):
        # Si le client envoie un bucket, on le convertit vers les libellés historiques du moteur.
        mapping = {
            "lt_24h": "Moins de 24 heures",
            "1_3_days": "1 à 3 jours",
            "4_7_days": "4 à 7 jours",
            "gt_1_week": "Plus d’une semaine",
            "gt_1_month": "Plus d’un mois",
            "gt_1_year": "Plus d’ une année",
        }
        if not self.duration and self.duration_bucket:
            self.duration = mapping.get(self.duration_bucket, self.duration_bucket)
        return self

    def to_engine_payload(self) -> dict[str, Any]:
        # Garder les clés attendues par l'ancien moteur.
        return {
            "complaint_text": self.complaint_text,
            "duration": self.duration or "",
            "associated_signs": self.associated_signs,
            "medical_history": self.medical_history,
            "already_consulted": self.already_consulted,
            "attachment_present": bool(self.attachment_present),
            "date_of_birth": self.date_of_birth,
            "sex": self.sex,
            "province": self.province or "",
            "weight_kg": self.weight_kg,
            "height_m": self.height_m,
            "pregnant": self.pregnant,
            "immediate_red_flags": self.immediate_red_flags or {},
        }


class TriageResponse(BaseModel):
    request_id: str
    priority_code: str
    color: str | None = None
    urgency_label: str | None = None
    orientation: str | None = None
    message: str | None = None
    reasons: list[str] = Field(default_factory=list)
    activated_domains: list[str] = Field(default_factory=list)
    activated_entries: list[str] = Field(default_factory=list)
    activated_modifiers: list[str] = Field(default_factory=list)
    activated_patterns: list[str] = Field(default_factory=list)
    score_total: int | float | None = None
    score_breakdown: list[str] = Field(default_factory=list)
    normalized_profile: dict[str, Any] = Field(default_factory=dict)
    case_fields: dict[str, Any] = Field(default_factory=dict)
    asked_questions: list[dict[str, Any]] = Field(default_factory=list)
    disclaimer: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    engine_loaded: bool
    kb_loaded: bool
    kb_path: str | None = None
