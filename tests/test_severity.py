from domain.models import IntakeAnswers
from intake.base_questions import IMMEDIATE_SEVERITY_SIGNS
from clinical.severity_gate import evaluate_severity

def test_registry_has_exactly_17_signs():
    assert len(IMMEDIATE_SEVERITY_SIGNS) == 17

def test_each_sign_triggers_emergency():
    for code in IMMEDIATE_SEVERITY_SIGNS:
        answers = {key: False for key in IMMEDIATE_SEVERITY_SIGNS}
        answers[code] = True
        result = evaluate_severity(answers)
        assert result.emergency is True
        assert result.triggered_codes == [code]
