from llm.schemas import V64_ASSESSMENT_SCHEMA


def test_v64_schema_has_clinical_and_safety_fields():
    expected = {
        'clinical_summary',
        'priority',
        'primary_specialty',
        'possible_conditions',
        'reasons',
        'what_to_do_now',
        'worsening_signs',
        'detected_severity_signs',
        'severity_evidence',
        'contradictions',
    }
    expected |= {'uncertainty','requires_human_review','epidemiology_risk_notes','infection_control_precautions'}
    assert set(V64_ASSESSMENT_SCHEMA['properties']) == expected
    assert set(V64_ASSESSMENT_SCHEMA['required']) == expected
    assert V64_ASSESSMENT_SCHEMA['additionalProperties'] is False
