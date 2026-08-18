from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from clinical.text_safety_gate import normalize_text
from domain.models import IntakeAnswers


@dataclass(frozen=True)
class EpidemiologySafetyResult:
    priority_floor: str | None = None
    matched_alerts: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    infection_control_alert: bool = False
    public_health_review: bool = False
    stale_context: bool = False


HIGH_CONSEQUENCE = ('ebola', 'marburg', 'fievre hemorragique', 'cholera', 'mpox', 'rougeole', 'meningite', 'polio', 'fievre jaune')


def _source_is_stale(value: str | None, days: int = 30) -> bool:
    if not value:
        return True
    try:
        d = datetime.fromisoformat(value[:10]).date()
        return (date.today() - d).days > days
    except ValueError:
        return True


def evaluate_epidemiology_safety(intake: IntakeAnswers) -> EpidemiologySafetyResult:
    epi = intake.epidemiology
    text = normalize_text(intake.complaint_text + ' ' + ' '.join(intake.associated_signs))
    alerts = [normalize_text(a) for a in epi.active_health_alerts]
    stale = _source_is_stale(epi.source_date) if alerts else False
    if not alerts or stale:
        return EpidemiologySafetyResult(stale_context=stale)

    matched: list[str] = []
    evidence: list[str] = []
    infection = False
    review = False
    floor: str | None = None

    febrile = any(x in text for x in ('fievre', 'temperature elevee', 'frissons'))
    diarrhea = 'diarrhee' in text or 'selles liquides' in text
    rash = any(x in text for x in ('eruption', 'boutons', 'vesicules', 'cloques', 'taches'))
    bleeding = any(x in text for x in ('saign', 'hemorrag'))
    neuro = any(x in text for x in ('nuque raide', 'convulsion', 'confus', 'somnolent'))
    weakness = any(x in text for x in ('faiblesse', 'paralys'))

    for alert in alerts:
        compatible = False
        if 'cholera' in alert: compatible = diarrhea
        elif 'ebola' in alert or 'marburg' in alert or 'fievre hemorragique' in alert: compatible = febrile and (bleeding or diarrhea)
        elif 'mpox' in alert: compatible = febrile and rash
        elif 'rougeole' in alert: compatible = febrile and rash
        elif 'meningite' in alert: compatible = febrile and neuro
        elif 'polio' in alert: compatible = weakness
        elif 'fievre jaune' in alert: compatible = febrile
        else: compatible = febrile
        if compatible:
            matched.append(alert)
            evidence.append(f'Symptômes compatibles avec une alerte sanitaire active fournie : {alert}')
            review = True
            floor = 'P2'
            if any(h in alert for h in HIGH_CONSEQUENCE):
                infection = True

    return EpidemiologySafetyResult(
        priority_floor=floor,
        matched_alerts=tuple(matched),
        evidence=tuple(evidence),
        infection_control_alert=infection,
        public_health_review=bool(matched),
        stale_context=False,
    )
