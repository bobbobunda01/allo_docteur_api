from __future__ import annotations
from dataclasses import dataclass
from intake.base_questions import IMMEDIATE_SEVERITY_SIGNS

@dataclass(frozen=True)
class SeverityGateResult:
    emergency: bool
    triggered_codes: list[str]
    triggered_labels: list[str]


def evaluate_severity(answers: dict[str, bool]) -> SeverityGateResult:
    triggered_codes = [code for code in IMMEDIATE_SEVERITY_SIGNS if answers.get(code) is True]
    return SeverityGateResult(
        emergency=bool(triggered_codes),
        triggered_codes=triggered_codes,
        triggered_labels=[IMMEDIATE_SEVERITY_SIGNS[code] for code in triggered_codes],
    )
