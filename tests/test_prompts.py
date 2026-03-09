"""
Unit tests for src/prompts.py — parse_analysis_json()

Tests cover the structured output parser that extracts JSON from LLM responses.
No external services required.
"""
import pytest
from src.prompts import parse_analysis_json

_VALID_JSON = """{
  "root_cause": "El DOM cambió después de encontrar el elemento",
  "severity": "high",
  "confidence": "high",
  "investigation_steps": ["Verificar re-renders", "Añadir WebDriverWait"],
  "suggested_fix": "Re-fetch the element before interaction"
}"""

_DEEPSEEK_WRAPPED = f"""<thought>
Let me think about this error...
The stack trace shows a StaleElementReferenceException which means the DOM changed.
</thought>
{_VALID_JSON}"""


class TestParseAnalysisJson:
    def test_parses_clean_json(self):
        result = parse_analysis_json(_VALID_JSON)
        assert result is not None
        assert result["root_cause"] == "El DOM cambió después de encontrar el elemento"

    def test_strips_thought_tags(self):
        result = parse_analysis_json(_DEEPSEEK_WRAPPED)
        assert result is not None
        assert result["severity"] == "high"

    def test_returns_all_required_keys(self):
        result = parse_analysis_json(_VALID_JSON)
        assert result is not None
        for key in ("root_cause", "severity", "confidence", "investigation_steps", "suggested_fix"):
            assert key in result

    def test_investigation_steps_is_list(self):
        result = parse_analysis_json(_VALID_JSON)
        assert isinstance(result["investigation_steps"], list)
        assert len(result["investigation_steps"]) >= 1

    def test_json_embedded_in_text(self):
        """Parser must extract JSON even when surrounded by prose text."""
        raw = f"Aquí tienes el análisis:\n\n{_VALID_JSON}\n\nEspero que sea útil."
        result = parse_analysis_json(raw)
        assert result is not None

    def test_invalid_severity_gets_normalised(self):
        raw = _VALID_JSON.replace('"high"', '"catastrophic"')
        result = parse_analysis_json(raw)
        # Should normalise to "medium" rather than return None
        assert result is not None
        assert result["severity"] == "medium"

    def test_invalid_confidence_gets_normalised(self):
        raw = _VALID_JSON.replace('"confidence": "high"', '"confidence": "unknown"')
        result = parse_analysis_json(raw)
        assert result is not None
        assert result["confidence"] == "low"

    def test_missing_required_key_returns_none(self):
        import json
        data = json.loads(_VALID_JSON)
        del data["root_cause"]
        assert parse_analysis_json(json.dumps(data)) is None

    def test_plain_text_returns_none(self):
        assert parse_analysis_json("This is just plain text with no JSON.") is None

    def test_empty_string_returns_none(self):
        assert parse_analysis_json("") is None

    def test_malformed_json_returns_none(self):
        assert parse_analysis_json('{"root_cause": "broken", "severity":}') is None

    def test_investigation_steps_not_list_returns_none(self):
        import json
        data = json.loads(_VALID_JSON)
        data["investigation_steps"] = "should be a list"
        assert parse_analysis_json(json.dumps(data)) is None

    def test_valid_severity_values_accepted(self):
        import json
        for severity in ("critical", "high", "medium", "low"):
            data = json.loads(_VALID_JSON)
            data["severity"] = severity
            result = parse_analysis_json(json.dumps(data))
            assert result is not None
            assert result["severity"] == severity

    def test_valid_confidence_values_accepted(self):
        import json
        for confidence in ("high", "medium", "low"):
            data = json.loads(_VALID_JSON)
            data["confidence"] = confidence
            result = parse_analysis_json(json.dumps(data))
            assert result is not None
            assert result["confidence"] == confidence
