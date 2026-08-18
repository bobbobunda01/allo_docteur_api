from domain.enums import Priority
from llm.schemas import V64_ASSESSMENT_SCHEMA

def test_llm_schema_allows_p1():
    allowed = V64_ASSESSMENT_SCHEMA["properties"]["priority"]["enum"]
    assert allowed == ["P1", "P2", "P3", "P4"]

def test_priority_enum_contains_p1():
    assert Priority.P1.value == "P1"
