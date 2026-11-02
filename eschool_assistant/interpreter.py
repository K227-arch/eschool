"""AI interpreter — converts a parent's natural-language request into
structured ``SearchCriteria`` using an LLM.

This is the *only* module that talks to an AI model.  Everything else in the
pipeline is deterministic.  The LLM is never given school data and never
asked to "search" — it only extracts the criteria the parent mentioned.

Design notes
------------
*  Calls the chat completions REST endpoint directly with ``httpx``, so it
   works with any OpenAI-compatible provider (OpenAI, Groq, OpenRouter …)
   without requiring a specific SDK version.
*  Temperature is pinned to 0 for deterministic extraction.
*  The system prompt embeds the valid filter values from ``config.py`` so the
   model returns canonical values where possible.
*  Fields the parent did *not* mention are returned as ``null`` / empty,
   giving us the "specified vs. unspecified" distinction the brief requires.
*  If the request is too vague to extract any criteria, the model returns a
   ``clarifying_question`` instead.
*  The ``client`` param is injected in tests to pass a fake that returns
   canned JSON without hitting the network.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from .config import (
    DEFAULT_BASE_URL_AI,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    GROQ_BASE_URL,
    GROQ_DEFAULT_MODEL,
    VALID_ACCOMMODATIONS,
    VALID_ADMISSION_STATUSES,
    VALID_CURRICULUMS,
    VALID_FACILITIES,
    VALID_GENDERS,
    VALID_LEVELS,
    VALID_LOCATIONS,
    VALID_RELIGIONS,
    VALID_SORTING,
)
from .models import SearchCriteria

logger = logging.getLogger(__name__)

# ── Input validation limits ───────────────────────────────────────────────
MAX_REQUEST_LENGTH = 2000
MIN_REQUEST_LENGTH = 3


# ── System prompt ─────────────────────────────────────────────────────────
def build_system_prompt() -> str:
    """Build the LLM system prompt.  Kept separate so tests can inspect it."""
    return f"""\
You are a search-criteria extractor for eSchool (eschool.ug), a Ugandan \
school discovery platform.  A parent describes the kind of school they are \
looking for in ordinary language.  Your job is to extract structured search \
criteria from their request — nothing more.  You must NOT invent school \
data, search for schools, or recommend specific schools.

Return a JSON object with exactly these fields (use null or [] for anything \
the parent did not mention):

{{
  "location": null,
  "county": null,
  "min_fees": null,
  "max_fees": null,
  "gender": null,
  "admission_status": null,
  "accommodation": null,
  "sorting": null,
  "levels": [],
  "curriculums": [],
  "facilities": [],
  "religions": [],
  "query": null,
  "unsupported_criteria": [],
  "clarifying_question": null,
  "interpretation_notes": []
}}

FIELD GUIDE

location    — A Ugandan district (UPPERCASE).  Valid values: \
{sorted(VALID_LOCATIONS)}.
county      — A division/county within the chosen district (UPPERCASE).  \
Only set if the parent mentions a specific area/division/county.
min_fees    — Minimum termly fees in UGX (integer).  Only set if the parent \
specifies a minimum.
max_fees    — Maximum termly fees in UGX (integer).  Only set if the parent \
specifies a maximum.  Interpret "1 million" or "1M" as 1000000.
gender      — One of: {sorted(VALID_GENDERS)}.  "girls' school" → "girls", \
"boys' school" → "boys", otherwise null.
admission_status — "open" or "closed".  Only set if the parent explicitly \
mentions admission status.
accommodation — One of: {sorted(VALID_ACCOMMODATIONS)}.  "boarding school" \
→ "Boarding", "day school" → "Day".
sorting     — One of: {sorted(VALID_SORTING)}.  Only set if the parent \
mentions a preference for cheap/popular/new schools.
levels      — List of school levels from: {sorted(VALID_LEVELS)}.  \
"secondary school" → ["Secondary"], "primary" → ["Primary"].
curriculums — List from: {sorted(VALID_CURRICULUMS)}.
facilities  — List from: {sorted(VALID_FACILITIES)}.
religions   — List from: {sorted(VALID_RELIGIONS)}.
query       — A school-name keyword, only if the parent names a specific \
school.

unsupported_criteria — List of things the parent asked for that eSchool's \
search CANNOT filter for.  Examples: "admitting Senior One students", \
"good sports program", "near my home", "with transport".
clarifying_question — If the request is too vague to extract ANY meaningful \
criteria (e.g. "a good school"), set this to a single clarifying question \
for the parent.  Leave null otherwise.
interpretation_notes — List of interpretation decisions, e.g. \
["Interpreted '1M' as max 1 000 000 UGX per term"].

RULES
1.  Only fill a field when the parent EXPLICITLY mentions it.
2.  Fees are per TERM in UGX.  If the parent says "per year", divide by 3 \
and note it.
3.  Never fabricate or guess location, county, or any value not mentioned.
4.  Return ONLY the JSON object, no markdown fences or explanation."""


# ── Provider detection ────────────────────────────────────────────────────
def _resolve_provider() -> tuple[str, str, str]:
    """Return ``(api_key, base_url, default_model)`` from environment vars.

    Priority: GROQ_API_KEY → OPENAI_API_KEY → RuntimeError.
    """
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        return (
            groq_key,
            os.getenv("GROQ_BASE_URL", GROQ_BASE_URL),
            os.getenv("GROQ_MODEL", GROQ_DEFAULT_MODEL),
        )

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        return (
            openai_key,
            os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL_AI),
            os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        )

    raise RuntimeError(
        "No AI API key found. Set GROQ_API_KEY or OPENAI_API_KEY, "
        "or the rule-based interpreter will be used automatically."
    )


# ── Interpreter ───────────────────────────────────────────────────────────
class Interpreter:
    """LLM-powered request interpreter.

    Calls the chat completions REST endpoint directly with ``httpx`` so it
    works with any OpenAI-compatible provider without SDK version constraints.

    Parameters
    ----------
    client : object, optional
        Injected for testing (must expose ``client.chat.completions.create``).
        When ``None`` the interpreter auto-detects the provider from env vars.
    model : str, optional
        Model name override.
    """

    def __init__(
        self,
        client: Optional[object] = None,
        model: Optional[str] = None,
    ) -> None:
        if client is not None:
            # Test / injected mode — delegate to the client's SDK interface
            self._client = client
            self._use_sdk = True
            self.model = model or DEFAULT_MODEL
            self._api_key = None
            self._base_url = None
        else:
            # Live mode — call REST directly with httpx
            self._api_key, self._base_url, default_model = _resolve_provider()
            self.model = model or default_model
            self._client = None
            self._use_sdk = False

    def interpret(self, request: str) -> SearchCriteria:
        """Interpret a parent's request into ``SearchCriteria``."""
        self._validate_input(request)
        messages = self._build_messages(request)

        try:
            if self._use_sdk:
                raw_json = self._call_via_sdk(messages)
            else:
                raw_json = self._call_via_httpx(messages)
        except LLMError:
            raise
        except Exception as exc:
            logger.error("LLM API call failed: %s", exc)
            raise LLMError(f"The AI service is unavailable: {exc}") from exc

        return self._parse_response(raw_json)

    @property
    def status(self) -> str:
        return f"Interpreter(model={self.model})"

    # ── Call paths ────────────────────────────────────────────────────────
    def _call_via_sdk(self, messages: list[dict]) -> str:
        """Used in tests where a fake SDK client is injected."""
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=DEFAULT_TEMPERATURE,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    def _call_via_httpx(self, messages: list[dict]) -> str:
        """Call the completions endpoint directly with httpx."""
        import httpx

        url = f"{self._base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # Try with json_object response format first
        for payload in [
            {
                "model": self.model,
                "messages": messages,
                "temperature": DEFAULT_TEMPERATURE,
                "response_format": {"type": "json_object"},
            },
            # Fallback without response_format if provider doesn't support it
            {
                "model": self.model,
                "messages": messages,
                "temperature": DEFAULT_TEMPERATURE,
            },
        ]:
            with httpx.Client(timeout=60) as http:
                resp = http.post(url, json=payload, headers=headers)

            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]

            # 400/422 usually means unsupported param → try without it
            if resp.status_code in (400, 422) and "response_format" in payload:
                logger.debug("json_object mode not supported, retrying without it")
                continue

            # Any other error is fatal
            raise LLMError(
                f"API returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        raise LLMError("API call failed for all attempted payload configurations.")

    # ── Helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _validate_input(request: str) -> None:
        if not request or not request.strip():
            raise ValueError("Request cannot be empty.")
        if len(request) > MAX_REQUEST_LENGTH:
            raise ValueError(
                f"Request too long ({len(request)} chars). "
                f"Maximum is {MAX_REQUEST_LENGTH}."
            )
        if len(request.strip()) < MIN_REQUEST_LENGTH:
            raise ValueError(
                "Request too short. Please describe what you are looking for."
            )

    @staticmethod
    def _build_messages(request: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": request},
        ]

    @staticmethod
    def _parse_response(raw_json: str) -> SearchCriteria:
        if not raw_json or not raw_json.strip():
            raise LLMError("The AI returned an empty response.")

        try:
            data: dict[str, Any] = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            logger.warning("LLM returned invalid JSON, attempting repair: %s", exc)
            data = _extract_json(raw_json)
            if data is None:
                raise LLMError(
                    f"The AI returned invalid JSON that could not be repaired: {exc}"
                ) from exc

        try:
            criteria = SearchCriteria(**data)
        except Exception as exc:
            raise LLMError(
                f"The AI returned data that does not match the expected schema: {exc}"
            ) from exc

        if criteria.clarifying_question and not criteria.has_any_criteria:
            logger.info("LLM requested clarification: %s", criteria.clarifying_question)

        return criteria


# ── JSON repair helper ────────────────────────────────────────────────────
def _extract_json(text: str) -> dict[str, Any] | None:
    """Try to salvage a JSON object from text that may have markdown fences."""
    import re

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


class LLMError(Exception):
    """Raised when the LLM fails or returns unparseable output."""
