"""Shared pytest fixtures for the eSchool Assistant test suite."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from eschool_assistant.interpreter import Interpreter
from eschool_assistant.models import School, SearchCriteria
from eschool_assistant.parser import parse_search_results
from eschool_assistant.pipeline import clear_cache

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _clear_pipeline_cache():
    """Clear the search cache before every test."""
    clear_cache()
    yield
    clear_cache()


# ── Fixture helpers ────────────────────────────────────────────────────────
@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE_DIR


@pytest.fixture
def load_fixture():
    """Return a function that loads a fixture file by name."""
    def _load(name: str) -> str:
        path = FIXTURE_DIR / name
        with open(path, encoding="utf-8") as f:
            return f.read()
    return _load


@pytest.fixture
def kampala_mixed_html(load_fixture) -> str:
    return load_fixture("kampala_central_mixed.html")


@pytest.fixture
def kampala_all_html(load_fixture) -> str:
    return load_fixture("kampala_all.html")


@pytest.fixture
def no_results_html(load_fixture) -> str:
    return load_fixture("no_results.html")


@pytest.fixture
def school_detail_html(load_fixture) -> str:
    return load_fixture("school_detail_mbogo.html")


# ── Parsed schools from fixtures ──────────────────────────────────────────
@pytest.fixture
def kampala_schools(kampala_mixed_html):
    """Schools parsed from the Kampala Central mixed fixture."""
    schools, _ = parse_search_results(kampala_mixed_html)
    return schools


@pytest.fixture
def sample_school(kampala_schools) -> School:
    """First school from the fixture."""
    return kampala_schools[0]


@pytest.fixture
def secondary_school(kampala_schools) -> School | None:
    """A secondary school from the fixture, or None."""
    for s in kampala_schools:
        if s.level == "Secondary":
            return s
    return None


# ── Mock LLM client ───────────────────────────────────────────────────────
class FakeMessage:
    def __init__(self, content: str):
        self.content = content


class FakeChoice:
    def __init__(self, content: str):
        self.message = FakeMessage(content)


class FakeCompletionResponse:
    def __init__(self, content: str):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, json_responses: list[str]):
        self._responses = json_responses
        self._idx = 0
        self.call_count = 0
        self.last_kwargs = None

    def create(self, **kwargs):
        self.call_count += 1
        self.last_kwargs = kwargs
        if self._idx < len(self._responses):
            resp = FakeCompletionResponse(self._responses[self._idx])
            self._idx += 1
            return resp
        # Default to the last response
        return FakeCompletionResponse(self._responses[-1])

    @property
    def exhausted(self) -> bool:
        return self._idx >= len(self._responses)


class FakeChat:
    def __init__(self, completions: FakeCompletions):
        self.completions = completions


class FakeOpenAIClient:
    """A fake OpenAI client that returns canned JSON responses."""

    def __init__(self, json_responses: list[str] | list[dict]):
        strings = []
        for r in json_responses:
            if isinstance(r, dict):
                strings.append(json.dumps(r))
            else:
                strings.append(r)
        self._completions = FakeCompletions(strings)
        self.chat = FakeChat(self._completions)

    @property
    def call_count(self) -> int:
        return self._completions.call_count

    @property
    def last_kwargs(self):
        return self._completions.last_kwargs


@pytest.fixture
def make_interpreter():
    """Factory: create an Interpreter backed by a fake LLM.

    Usage::

        interp = make_interpreter([{"location": "KAMPALA", ...}])
        criteria = interp.interpret("test request")
    """
    def _make(json_responses: list[str] | list[dict]) -> tuple[Interpreter, FakeOpenAIClient]:
        client = FakeOpenAIClient(json_responses)
        interp = Interpreter(client=client, model="gpt-4o-mini")
        return interp, client
    return _make


@pytest.fixture
def failing_llm_client():
    """A fake OpenAI client whose completions.create always raises."""

    class FailingCompletions:
        call_count = 0
        def create(self, **kwargs):
            self.call_count += 1
            raise ConnectionError("API key invalid")

    class FailingChat:
        def __init__(self):
            self.completions = FailingCompletions()

    class FailingClient:
        def __init__(self):
            self.chat = FailingChat()

    return FailingClient()


# ── Mock HTTP client ──────────────────────────────────────────────────────
@pytest.fixture
def mock_http_client_factory():
    """Factory: create a mock httpx.Client that returns saved fixtures.

    Usage::

        client = mock_http_client_factory({"gender=girls": "kampala_central_mixed.html"})
    """
    import httpx

    def _create(url_map: dict[str, str] | None = None, default: str | None = None):
        url_map = url_map or {}

        class MockClient:
            def __init__(self):
                self.calls = []

            def get(self, url, headers=None):
                self.calls.append(url)
                fixture_name = default
                for pattern, name in url_map.items():
                    if pattern in url:
                        fixture_name = name
                        break
                if fixture_name is None:
                    # Empty page
                    html = "<html><body></body></html>"
                else:
                    with open(FIXTURE_DIR / fixture_name, encoding="utf-8") as f:
                        html = f.read()
                return httpx.Response(
                    status_code=200,
                    text=html,
                    request=httpx.Request("GET", url),
                )

        return MockClient()

    return _create


# ── Common criteria fixtures ──────────────────────────────────────────────
@pytest.fixture
def girls_boarding_criteria() -> SearchCriteria:
    """Criteria matching the example from the assessment brief."""
    return SearchCriteria(
        location="KAMPALA",
        county="KAMPALA CENTRAL DIVISION",
        max_fees=1000000,
        gender="girls",
        accommodation="Boarding",
        levels=["Secondary"],
        unsupported_criteria=["admitting Senior One students"],
        interpretation_notes=["Interpreted '1M' as max 1,000,000 UGX per term"],
    )


@pytest.fixture
def empty_criteria() -> SearchCriteria:
    return SearchCriteria()
