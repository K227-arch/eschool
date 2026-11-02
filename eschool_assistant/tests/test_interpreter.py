"""Tests for the AI interpreter (with a mocked LLM — no real API calls)."""
import json

import pytest

from eschool_assistant.interpreter import (
    Interpreter,
    LLMError,
    MAX_REQUEST_LENGTH,
    build_system_prompt,
)
from eschool_assistant.models import SearchCriteria


class TestSystemPrompt:
    def test_contains_valid_locations(self):
        prompt = build_system_prompt()
        assert "KAMPALA" in prompt
        assert "WAKISO" in prompt

    def test_contains_valid_genders(self):
        prompt = build_system_prompt()
        for g in ["mixed", "boys", "girls"]:
            assert g in prompt

    def test_contains_valid_levels(self):
        prompt = build_system_prompt()
        assert "Secondary" in prompt
        assert "Primary" in prompt

    def test_contains_accommodation_values(self):
        prompt = build_system_prompt()
        assert "Boarding" in prompt
        assert "Day" in prompt

    def test_instructs_null_for_unspecified(self):
        prompt = build_system_prompt()
        assert "null" in prompt.lower()

    def test_mentions_ugx(self):
        prompt = build_system_prompt()
        assert "UGX" in prompt

    def test_mentions_unsupported_criteria(self):
        prompt = build_system_prompt()
        assert "unsupported_criteria" in prompt

    def test_mentions_clarifying_question(self):
        prompt = build_system_prompt()
        assert "clarifying_question" in prompt


class TestInputValidation:
    def test_empty_request_raises(self, make_interpreter):
        interp, _ = make_interpreter([{}])
        with pytest.raises(ValueError, match="empty"):
            interp.interpret("")

    def test_whitespace_only_request_raises(self, make_interpreter):
        interp, _ = make_interpreter([{}])
        with pytest.raises(ValueError, match="empty"):
            interp.interpret("   \n\t  ")

    def test_too_long_request_raises(self, make_interpreter):
        interp, _ = make_interpreter([{}])
        with pytest.raises(ValueError, match="too long"):
            interp.interpret("x" * (MAX_REQUEST_LENGTH + 1))

    def test_too_short_request_raises(self, make_interpreter):
        interp, _ = make_interpreter([{}])
        with pytest.raises(ValueError, match="too short"):
            interp.interpret("ab")


class TestInterpretNormal:
    def test_extracts_all_criteria(self, make_interpreter):
        resp = {
            "location": "KAMPALA",
            "county": "KAMPALA CENTRAL DIVISION",
            "max_fees": 1000000,
            "gender": "girls",
            "accommodation": "Boarding",
            "levels": ["Secondary"],
            "unsupported_criteria": ["admitting Senior One students"],
            "interpretation_notes": ["Interpreted 1M as 1,000,000 UGX"],
        }
        interp, client = make_interpreter([resp])
        criteria = interp.interpret("girls boarding school in Kampala, max 1M")

        assert criteria.location == "KAMPALA"
        assert criteria.county == "KAMPALA CENTRAL DIVISION"
        assert criteria.max_fees == 1000000
        assert criteria.gender == "girls"
        assert criteria.accommodation == "Boarding"
        assert criteria.levels == ["Secondary"]
        assert "admitting Senior One students" in criteria.unsupported_criteria
        assert client.call_count == 1

    def test_uses_temperature_zero(self, make_interpreter):
        interp, client = make_interpreter([{"location": "KAMPALA"}])
        interp.interpret("schools in Kampala")
        assert client.last_kwargs["temperature"] == 0.0

    def test_uses_json_response_format(self, make_interpreter):
        interp, client = make_interpreter([{"location": "KAMPALA"}])
        interp.interpret("schools in Kampala")
        assert client.last_kwargs["response_format"] == {"type": "json_object"}

    def test_partial_criteria(self, make_interpreter):
        resp = {"location": "WAKISO", "levels": ["Primary"]}
        interp, _ = make_interpreter([resp])
        criteria = interp.interpret("primary school in Wakiso")

        assert criteria.location == "WAKISO"
        assert criteria.levels == ["Primary"]
        assert criteria.max_fees is None
        assert criteria.gender is None


class TestInterpretVague:
    def test_vague_request_returns_clarifying_question(self, make_interpreter):
        resp = {
            "clarifying_question": "What area or type of school are you looking for?",
            "location": None,
            "levels": [],
            "unsupported_criteria": [],
            "interpretation_notes": [],
        }
        interp, _ = make_interpreter([resp])
        criteria = interp.interpret("a good school")

        assert criteria.clarifying_question is not None
        assert not criteria.has_any_criteria


class TestInterpretMalformed:
    def test_markdown_fenced_json_is_repaired(self, make_interpreter):
        inner = json.dumps({"location": "WAKISO", "gender": "mixed"})
        resp = f"Here is the result:\n```json\n{inner}\n```"
        interp, _ = make_interpreter([resp])
        criteria = interp.interpret("mixed school in Wakiso")
        assert criteria.location == "WAKISO"
        assert criteria.gender == "mixed"

    def test_completely_invalid_json_raises_llm_error(self, make_interpreter):
        interp, _ = make_interpreter(["not json at all !!!"])
        with pytest.raises(LLMError, match="invalid JSON"):
            interp.interpret("test request")

    def test_empty_response_raises_llm_error(self, make_interpreter):
        interp, _ = make_interpreter([""])
        with pytest.raises(LLMError, match="empty"):
            interp.interpret("test request")

    def test_schema_mismatch_raises_llm_error(self, make_interpreter):
        """If the LLM returns valid JSON but with wrong types."""
        interp, _ = make_interpreter([{"location": 12345, "max_fees": "not a number"}])
        # Pydantic should coerce int to str, but "not a number" for max_fees
        # should fail validation
        with pytest.raises(LLMError):
            interp.interpret("test request")


class TestLLMFailure:
    def test_api_error_raises_llm_error(self, failing_llm_client):
        interp = Interpreter(client=failing_llm_client, model="gpt-4o-mini")
        with pytest.raises(LLMError, match="AI service is unavailable"):
            interp.interpret("schools in Kampala")
