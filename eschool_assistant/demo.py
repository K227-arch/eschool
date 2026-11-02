"""Demonstration script — produces the three example outputs required by
Section 3E of the assessment brief.

Run without an API key::

    python -m eschool_assistant.demo

The script uses mock LLM responses and saved HTML fixtures so it works
offline. It demonstrates:

1. A request with clearly specified search criteria.
2. A request with missing or ambiguous information.
3. A request that returns no suitable results.
"""
from __future__ import annotations

import httpx
import json
import os

from eschool_assistant.interpreter import Interpreter
from eschool_assistant.pipeline import search_schools
from eschool_assistant.presenter import present

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "tests", "fixtures")


# ── Mock LLM infrastructure ────────────────────────────────────────────────
class _FakeMsg:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMsg(content)


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, responses):
        self.responses = responses
        self.idx = 0

    def create(self, **kwargs):
        r = self.responses[self.idx]
        self.idx += 1
        return _FakeResp(r)


class _FakeChat:
    def __init__(self, responses):
        self.completions = _FakeCompletions(responses)


class _FakeClient:
    def __init__(self, responses):
        self.chat = _FakeChat(responses)


def _mock_interpreter(criteria_dict):
    return Interpreter(client=_FakeClient([json.dumps(criteria_dict)]))


class _MockHttp:
    """Returns saved HTML fixtures based on URL patterns."""

    def __init__(self, url_map, default="kampala_central_mixed.html"):
        self.url_map = url_map
        self.default = default
        self.calls = []

    def get(self, url, headers=None):
        self.calls.append(url)
        for pattern, fixture_name in self.url_map.items():
            if pattern in url:
                path = os.path.join(FIXTURE_DIR, fixture_name)
                with open(path, encoding="utf-8") as f:
                    html = f.read()
                return httpx.Response(200, text=html, request=httpx.Request("GET", url))
        path = os.path.join(FIXTURE_DIR, self.default)
        with open(path, encoding="utf-8") as f:
            html = f.read()
        return httpx.Response(200, text=html, request=httpx.Request("GET", url))


def _run_demo(title, request, llm_response, http_map):
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)
    print(f"\n  PARENT REQUEST:")
    print(f'  "{request}"')
    print()

    interp = _mock_interpreter(llm_response)
    http_client = _MockHttp(http_map) if http_map else None
    response = search_schools(request, interpreter=interp, http_client=http_client)
    print(present(response))
    print()


def main():
    print()
    print("╔" + "═" * 70 + "╗")
    print("║" + " eSCHOOL ASSISTANT — DEMONSTRATION".center(70) + "║")
    print("║" + " Three example scenarios from Section 3E of the assessment".center(70) + "║")
    print("╚" + "═" * 70 + "╝")

    # ── Example 1: Clearly specified search criteria ──────────────────────
    _run_demo(
        "EXAMPLE 1: Clearly Specified Search Criteria",
        "I'm looking for a girls' boarding school in Kampala, preferably "
        "around Central Division, charging no more than UGX 1 million per "
        "term and currently admitting Senior One students.",
        {
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
        },
        {"location=KAMPALA": "kampala_central_mixed.html"},
    )

    # ── Example 2: Missing or ambiguous information ──────────────────────
    _run_demo(
        "EXAMPLE 2: Missing or Ambiguous Information",
        "somewhere affordable near town",
        {
            "clarifying_question": (
                "I'd like to help you find a school! Could you tell me: "
                "which district or area you're looking in (e.g. Kampala, "
                "Wakiso), and what level of school you need (nursery, "
                "primary, secondary)? 'Affordable' is also relative — "
                "do you have a rough budget per term?"
            ),
            "location": None,
            "max_fees": None,
            "levels": [],
            "unsupported_criteria": [],
            "interpretation_notes": [
                "'near town' is too vague to map to a specific district",
                "'affordable' has no numeric budget specified",
            ],
        },
        None,
    )

    # ── Example 3: No suitable results ───────────────────────────────────
    _run_demo(
        "EXAMPLE 3: Request That Returns No Suitable Results",
        "boarding secondary school in Kampala charging no more than "
        "UGX 5,000 per term",
        {
            "location": "KAMPALA",
            "max_fees": 5000,
            "accommodation": "Boarding",
            "levels": ["Secondary"],
            "interpretation_notes": [
                "Note: UGX 5,000 per term is extremely low for a boarding "
                "secondary school and may return very few or no results."
            ],
        },
        {"max_fees=5000": "no_results.html"},
    )

    print("=" * 72)
    print("  END OF DEMONSTRATION")
    print("=" * 72)
    print()
    print("  To run with a real OpenAI API key:")
    print("    1. Copy .env.example to .env and add your OPENAI_API_KEY")
    print("    2. Run: python -m eschool_assistant \"your search request\"")
    print("    Or enter interactive mode: python -m eschool_assistant")
    print()


if __name__ == "__main__":
    main()
