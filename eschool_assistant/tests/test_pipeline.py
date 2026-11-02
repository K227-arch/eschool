"""End-to-end tests for the pipeline with mocked components."""
import httpx
import pytest

from eschool_assistant.interpreter import Interpreter
from eschool_assistant.models import InterpretationStatus
from eschool_assistant.pipeline import search_schools
from eschool_assistant.presenter import present


class TestNormalSearch:
    def test_returns_schools_with_matches(self, make_interpreter, mock_http_client_factory):
        interp, _ = make_interpreter([{
            "location": "KAMPALA",
            "county": "KAMPALA CENTRAL DIVISION",
            "max_fees": 1000000,
            "gender": "girls",
            "accommodation": "Boarding",
            "levels": ["Secondary"],
            "unsupported_criteria": ["admitting Senior One students"],
            "interpretation_notes": ["Interpreted 1M as 1,000,000 UGX"],
        }])
        http_client = mock_http_client_factory({
            "gender=girls": "kampala_central_mixed.html",
        })

        response = search_schools(
            "girls boarding school in Kampala, max 1M",
            interpreter=interp,
            http_client=http_client,
        )

        assert response.status == InterpretationStatus.OK
        assert response.total_found_on_page > 0
        assert response.criteria.location == "KAMPALA"
        assert response.criteria.gender == "girls"
        assert response.search_url is not None
        assert any("Senior One" in n for n in response.notes)
        assert len(response.schools) > 0

    def test_presenter_output_is_readable(self, make_interpreter, mock_http_client_factory):
        interp, _ = make_interpreter([{
            "location": "KAMPALA",
            "gender": "mixed",
        }])
        http_client = mock_http_client_factory({
            "gender=mixed": "kampala_central_mixed.html",
        })

        response = search_schools(
            "mixed schools in Kampala",
            interpreter=interp,
            http_client=http_client,
        )
        output = present(response)
        assert "eSCHOOL SEARCH RESULTS" in output
        assert "Location: KAMPALA" in output
        assert "Search URL:" in output

    def test_notes_include_pagination_info(self, make_interpreter, mock_http_client_factory):
        interp, _ = make_interpreter([{"location": "KAMPALA", "gender": "mixed"}])
        http_client = mock_http_client_factory({
            "gender=mixed": "kampala_central_mixed.html",
        })

        response = search_schools(
            "mixed schools in Kampala",
            interpreter=interp,
            http_client=http_client,
        )
        assert any("page" in n.lower() or "More results" in n for n in response.notes)


class TestVagueRequest:
    def test_returns_clarification(self, make_interpreter, mock_http_client_factory):
        interp, _ = make_interpreter([{
            "clarifying_question": "What area or type of school are you looking for?",
            "location": None,
            "levels": [],
            "unsupported_criteria": [],
            "interpretation_notes": [],
        }])
        http_client = mock_http_client_factory()

        response = search_schools(
            "a good school",
            interpreter=interp,
            http_client=http_client,
        )

        assert response.status == InterpretationStatus.NEEDS_CLARIFICATION
        assert response.criteria.clarifying_question is not None
        assert response.total_found_on_page == 0

    def test_no_usable_criteria_returns_clarification(self, make_interpreter, mock_http_client_factory):
        """AI returns only unsupported criteria → need clarification."""
        interp, _ = make_interpreter([{
            "location": None,
            "levels": [],
            "unsupported_criteria": ["good reputation"],
            "interpretation_notes": [],
        }])
        http_client = mock_http_client_factory()

        response = search_schools(
            "school with good reputation",
            interpreter=interp,
            http_client=http_client,
        )

        assert response.status == InterpretationStatus.NEEDS_CLARIFICATION


class TestLLMFailure:
    def test_llm_error_returns_error_response(self, failing_llm_client, mock_http_client_factory):
        interp = Interpreter(client=failing_llm_client, model="gpt-4o-mini")
        http_client = mock_http_client_factory()

        response = search_schools(
            "schools in Kampala",
            interpreter=interp,
            http_client=http_client,
        )

        assert response.error is not None
        assert "AI service" in response.error or "unavailable" in response.error.lower()

    def test_presenter_shows_error(self, failing_llm_client, mock_http_client_factory):
        interp = Interpreter(client=failing_llm_client, model="gpt-4o-mini")
        http_client = mock_http_client_factory()

        response = search_schools(
            "schools in Kampala",
            interpreter=interp,
            http_client=http_client,
        )
        output = present(response)
        assert "ERROR" in output


class TestHTTPFailure:
    def test_connection_error_returns_error(self, make_interpreter):
        interp, _ = make_interpreter([{"location": "KAMPALA"}])

        class FailingClient:
            def get(self, url, headers=None):
                raise httpx.ConnectError("Connection refused")

        response = search_schools(
            "schools in Kampala",
            interpreter=interp,
            http_client=FailingClient(),
        )

        assert response.error is not None
        assert response.search_url is not None
        assert response.criteria.location == "KAMPALA"

    def test_http_500_returns_error(self, make_interpreter):
        interp, _ = make_interpreter([{"location": "KAMPALA"}])

        class Server500Client:
            def get(self, url, headers=None):
                return httpx.Response(
                    status_code=500,
                    text="Server Error",
                    request=httpx.Request("GET", url),
                )

        response = search_schools(
            "schools in Kampala",
            interpreter=interp,
            http_client=Server500Client(),
        )

        assert response.error is not None
        assert "500" in response.error or "error" in response.error.lower()


class TestLowResults:
    def test_few_results_handled(self, make_interpreter, mock_http_client_factory):
        interp, _ = make_interpreter([{
            "location": "KAMPALA",
            "max_fees": 1,
            "interpretation_notes": [],
        }])
        http_client = mock_http_client_factory({
            "max_fees=1": "no_results.html",
        })

        response = search_schools(
            "Kampala schools with very low fees",
            interpreter=interp,
            http_client=http_client,
        )

        assert response.status == InterpretationStatus.OK
        assert response.total_found_on_page <= 5


class TestUnsupportedCriteria:
    def test_unsupported_criteria_noted_in_response(self, make_interpreter, mock_http_client_factory):
        interp, _ = make_interpreter([{
            "location": "KAMPALA",
            "gender": "girls",
            "unsupported_criteria": ["Senior One admission", "good sports program"],
            "interpretation_notes": [],
        }])
        http_client = mock_http_client_factory({
            "gender=girls": "kampala_central_mixed.html",
        })

        response = search_schools(
            "girls school in Kampala with sports",
            interpreter=interp,
            http_client=http_client,
        )

        assert any("Senior One" in n for n in response.notes)
        assert any("sports" in n.lower() for n in response.notes)


class TestEndToEndFullFlow:
    """Full end-to-end test: interpret → validate → fetch → parse → match → present."""

    def test_complete_pipeline_produces_correct_output(self, make_interpreter, mock_http_client_factory):
        from eschool_assistant.pipeline import clear_cache
        clear_cache()
        # Mock the LLM to return criteria matching the assessment example
        interp, _ = make_interpreter([{
            "location": "KAMPALA",
            "county": "KAMPALA CENTRAL DIVISION",
            "max_fees": 1000000,
            "gender": "girls",
            "accommodation": "Boarding",
            "levels": ["Secondary"],
            "unsupported_criteria": ["currently admitting Senior One students"],
            "interpretation_notes": [
                "Interpreted '1M' as max 1,000,000 UGX per term",
                "Assumed 'Central Division' refers to Kampala Central Division",
            ],
        }])

        # Mock HTTP to return the Kampala fixture
        http_client = mock_http_client_factory({
            "location=KAMPALA": "kampala_central_mixed.html",
        })

        # Run the full pipeline
        request = (
            "I'm looking for a girls' boarding school in Kampala, "
            "preferably around Central Division, charging no more than "
            "UGX 1 million per term and currently admitting Senior One students."
        )
        response = search_schools(request, interpreter=interp, http_client=http_client)

        # Verify response structure
        assert response.status == InterpretationStatus.OK
        assert response.criteria.location == "KAMPALA"
        assert response.criteria.county == "KAMPALA CENTRAL DIVISION"
        assert response.criteria.max_fees == 1000000
        assert response.criteria.gender == "girls"
        assert response.criteria.accommodation == "Boarding"
        assert response.criteria.levels == ["Secondary"]
        assert response.search_url is not None
        assert response.total_found_on_page > 0

        # Verify schools have match results
        assert len(response.schools) > 0
        for result in response.schools:
            assert result.school.name
            assert result.school.url
            assert len(result.checks) > 0

        # Verify the presenter output mentions the unsupported criterion
        output = present(response)
        assert "Senior One" in output
        assert "Location: KAMPALA" in output
        assert "Max fees: UGX 1,000,000" in output

        # Verify the search URL was actually called
        assert len(http_client.calls) >= 1
