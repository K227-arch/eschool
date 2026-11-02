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
    GROQ_CONNECT_TIMEOUT,
    GROQ_DEFAULT_MODEL,
    GROQ_READ_TIMEOUT,
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
def build_system_prompt(compact: bool = False) -> str:
    """Build the LLM system prompt.

    ``compact=True`` produces a much shorter prompt for Groq models that
    time out on large payloads.  The schema is identical; only the field
    explanations are stripped down.
    """
    if compact:
        return f"""\
You extract school search criteria from a parent's request.
Return ONLY a valid JSON object. Use null for fields not mentioned. Use [] for empty lists.

JSON schema:
{{"location":null,"county":null,"min_fees":null,"max_fees":null,"gender":null,"admission_status":null,"accommodation":null,"sorting":null,"levels":[],"curriculums":[],"facilities":[],"religions":[],"query":null,"unsupported_criteria":[],"clarifying_question":null,"interpretation_notes":[]}}

Field rules:
- location: UPPERCASE Ugandan district only. Valid examples: KAMPALA, WAKISO, MUKONO, JINJA, GULU, MBALE, MBARARA. ONLY set if parent mentions a district/city. Otherwise null.
- county: UPPERCASE division only if explicitly mentioned (e.g. "KAMPALA CENTRAL DIVISION"). Otherwise null.
- max_fees: integer in UGX per term. "1 million"=1000000. "500K"=500000. Otherwise null.
- min_fees: integer in UGX per term. Otherwise null.
- gender: "girls", "boys", or "mixed" ONLY. Otherwise null.
- accommodation: "Boarding", "Day", or "Day & Boarding" ONLY. Otherwise null.
- admission_status: "open" or "closed" ONLY. Otherwise null.
- levels: list from ONLY these exact values: ["Nursery & Kindergaten","Nursery & Primary","Primary","Secondary","International"]. Set ONLY if parent says primary/secondary/nursery etc. Otherwise [].
- unsupported_criteria: things eSchool CANNOT filter e.g. specific class like "Senior One", quality like "best school". Do NOT add things that are already captured in other fields.
- clarifying_question: if request has NO extractable criteria at all, ask one question. Otherwise null.
- max_fees must be a plain integer, NOT a string.
- Do NOT invent levels or unsupported_criteria that the parent did not mention.
- Return ONLY the JSON. No markdown. No explanation. No extra text."""

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
3.  location MUST be an exact uppercase district name from the valid list \
(e.g. "KAMPALA", "WAKISO").  Never include city + division in location.
4.  county MUST be an exact uppercase county/division name (e.g. \
"KAMPALA CENTRAL DIVISION").  Set only if explicitly mentioned.
5.  max_fees and min_fees MUST be plain integers (not arrays or strings).
6.  levels MUST only contain values from the valid list above.  \
"Senior One" is NOT a level — put it in unsupported_criteria.
7.  Never fabricate or guess any value not explicitly mentioned.
8.  Return ONLY the JSON object, no markdown fences or explanation."""


# ── Provider detection ────────────────────────────────────────────────────
def _resolve_provider() -> tuple[str, str, str, float, float]:
    """Return ``(api_key, base_url, default_model, connect_timeout, read_timeout)``."""
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        return (
            groq_key,
            os.getenv("GROQ_BASE_URL", GROQ_BASE_URL),
            os.getenv("GROQ_MODEL", GROQ_DEFAULT_MODEL),
            GROQ_CONNECT_TIMEOUT,
            GROQ_READ_TIMEOUT,
        )

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        return (
            openai_key,
            os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL_AI),
            os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
            10.0,   # OpenAI connect timeout
            60.0,   # OpenAI read timeout
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
            self._client = client
            self._use_sdk = True
            self.model = model or DEFAULT_MODEL
            self._api_key = None
            self._base_url = None
            self._connect_timeout = 10.0
            self._read_timeout = 60.0
            self._compact_prompt = False
        else:
            self._api_key, self._base_url, default_model, self._connect_timeout, self._read_timeout = _resolve_provider()
            self.model = model or default_model
            self._client = None
            self._use_sdk = False
            # Use compact prompt for Groq (avoids large-payload timeouts)
            self._compact_prompt = bool(os.getenv("GROQ_API_KEY"))

    def interpret(self, request: str) -> SearchCriteria:
        """Interpret a parent's request into ``SearchCriteria``."""
        self._validate_input(request)
        compact = getattr(self, "_compact_prompt", False)
        messages = self._build_messages(request, compact=compact)

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

        return self._parse_response(raw_json, compact=compact, original_request=request)

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
        """Call the completions endpoint directly with httpx.post().

        Uses httpx.post() rather than httpx.Client() to reuse the default
        connection pool — this avoids the TCP reconnect overhead that was
        causing intermittent timeouts on Groq.
        """
        import httpx as _httpx

        url = f"{self._base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        timeout = _httpx.Timeout(
            connect=self._connect_timeout,
            read=self._read_timeout,
            write=10.0,
            pool=10.0,
        )

        payloads = [
            # Try with json_object mode first
            {
                "model": self.model,
                "messages": messages,
                "temperature": DEFAULT_TEMPERATURE,
                "response_format": {"type": "json_object"},
            },
            # Fallback: same but without response_format
            {
                "model": self.model,
                "messages": messages,
                "temperature": DEFAULT_TEMPERATURE,
            },
        ]

        for payload in payloads:
            try:
                resp = _httpx.post(url, json=payload, headers=headers, timeout=timeout)
            except (_httpx.ConnectTimeout, _httpx.ReadTimeout, _httpx.ConnectError) as exc:
                raise LLMError(
                    f"Could not reach {self._base_url}: {exc}"
                ) from exc

            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                if content and content.strip():
                    return content
                if "response_format" in payload:
                    continue   # empty body — retry without json_object
                raise LLMError("The AI returned an empty response.")

            # 400/422 → provider doesn't support response_format; retry without
            if resp.status_code in (400, 422) and "response_format" in payload:
                logger.debug("json_object rejected (HTTP %d), retrying without", resp.status_code)
                continue

            # 429 = quota/rate limit
            if resp.status_code == 429:
                raise LLMError(
                    f"API quota exceeded or rate limited. "
                    f"Check your {self._base_url} account billing."
                )

            raise LLMError(
                f"API returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        raise LLMError("API call failed for all attempted configurations.")

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
    def _build_messages(request: str, compact: bool = False) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": build_system_prompt(compact=compact)},
            {"role": "user", "content": request},
        ]

    @staticmethod
    def _parse_response(raw_json: str, compact: bool = False, original_request: str = "") -> SearchCriteria:
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

        # Coerce max_fees/min_fees from string or list to int
        for fee_field in ("max_fees", "min_fees"):
            val = data.get(fee_field)
            if isinstance(val, str):
                try:
                    data[fee_field] = int(val.replace(",", "").replace(" ", ""))
                except ValueError:
                    data[fee_field] = None
            elif isinstance(val, list):
                data[fee_field] = int(val[0]) if val and isinstance(val[0], (int, float)) else None

        # For compact-mode (small Groq models): sanitize hallucinated fields
        if compact:
            import re as _re
            req_lower = original_request.lower()
            valid_levels = {
                "Nursery & Kindergaten", "Nursery & Primary",
                "Primary", "Secondary", "International",
            }
            # Only keep levels the user actually mentioned by keyword
            level_keywords = {
                "Nursery & Kindergaten": [r"\bnursery\b", r"\bkinderg"],
                "Nursery & Primary":     [r"\bnursery\b", r"\bprimary\b"],
                "Primary":               [r"\bprimary\b"],
                "Secondary":             [r"\bsecondary\b", r"\bhigh school\b"],
                "International":         [r"\binternational\b"],
            }
            cleaned_levels = []
            for lvl in (data.get("levels") or []):
                if lvl in valid_levels:
                    kws = level_keywords.get(lvl, [])
                    if any(_re.search(kw, req_lower) for kw in kws):
                        cleaned_levels.append(lvl)
            data["levels"] = cleaned_levels

            # Only keep accommodation when the user explicitly said boarding/day
            if data.get("accommodation"):
                if not any(w in req_lower for w in ["boarding", "day school", "day only", "day and boarding"]):
                    data["accommodation"] = None

            # Only keep unsupported_criteria when a distinctive keyword appears in the request
            GENERIC_WORDS = {"school", "best", "good", "find", "looking", "need", "want", "make", "have", "with", "that", "this", "from", "near", "area", "some", "also"}
            cleaned_unsupported = []
            for u in (data.get("unsupported_criteria") or []):
                u_words = {w for w in u.lower().split() if len(w) > 3 and w not in GENERIC_WORDS}
                if u_words and any(w in req_lower for w in u_words):
                    cleaned_unsupported.append(u)
            data["unsupported_criteria"] = cleaned_unsupported

            # Always wipe query — small models echo the whole request
            data["query"] = None

        try:
            criteria = SearchCriteria(**data)
        except Exception as exc:
            raise LLMError(
                f"The AI returned data that does not match the expected schema: {exc}"
            ) from exc

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
