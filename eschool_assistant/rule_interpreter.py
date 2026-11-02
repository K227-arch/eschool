"""Rule-based interpreter — a no-API-key fallback for extracting search
criteria from natural language.

The assessment requires an AI model to interpret requests, and the primary
interpreter (``interpreter.py``) uses OpenAI for that.  However, to let
evaluators run the app without setting up an API key, this module provides a
deterministic, pattern-matching fallback that covers the common ways parents
describe schools.

It implements the same ``interpret(request) -> SearchCriteria`` interface as
the AI interpreter, so the pipeline can use it as a drop-in replacement.

How it works
------------
*  **Locations** — matches known district names (case-insensitive).
*  **Gender** — matches "girls' school", "boys only", "co-ed", etc.
*  **Accommodation** — matches "boarding", "day school", "day and boarding".
*  **Levels** — matches "primary", "secondary", "nursery", "international".
*  **Fees** — regex for "no more than UGX 1 million", "under 500K", etc.
*  **Admission status** — matches "admitting", "admissions open/closed".
*  **County** — tries to match division/county keywords against the known
   county map for the detected location.
*  **Unsupported criteria** — detects things like "Senior One admission",
   "good sports program", "near my home".
*  **Clarifying question** — if nothing is found and the request is vague.
"""

from __future__ import annotations

import re
import logging

from .config import (
    ACCOMMODATION_ALIASES,
    ADMISSION_ALIASES,
    COUNTY_MAP,
    GENDER_ALIASES,
    VALID_LEVELS,
    VALID_LOCATIONS,
)
from .models import SearchCriteria

logger = logging.getLogger(__name__)


class RuleBasedInterpreter:
    """Deterministic, pattern-matching interpreter (no API key needed)."""

    def interpret(self, request: str) -> SearchCriteria:
        """Extract ``SearchCriteria`` from *request* using regex/keyword rules."""
        if not request or not request.strip():
            raise ValueError("Request cannot be empty.")
        if len(request) > 2000:
            raise ValueError(f"Request too long ({len(request)} chars). Maximum is 2000.")
        if len(request.strip()) < 3:
            raise ValueError("Request too short. Please describe what you are looking for.")

        text = request.strip()
        text_lower = text.lower()
        notes: list[str] = []
        unsupported: list[str] = []

        # ── Location ──────────────────────────────────────────────────────
        location = _extract_location(text, text_lower)

        # ── County ────────────────────────────────────────────────────────
        county = _extract_county(text_lower, location, notes)

        # ── Fees ──────────────────────────────────────────────────────────
        min_fees, max_fees, fee_notes = _extract_fees(text_lower)
        notes.extend(fee_notes)

        # ── Gender ────────────────────────────────────────────────────────
        gender = _extract_gender(text_lower)

        # ── Accommodation ─────────────────────────────────────────────────
        accommodation = _extract_accommodation(text_lower)

        # ── Levels ────────────────────────────────────────────────────────
        levels = _extract_levels(text_lower)

        # ── Admission status ─────────────────────────────────────────────
        admission_status = _extract_admission_status(text_lower)

        # ── Unsupported criteria ──────────────────────────────────────────
        unsupported = _extract_unsupported(text_lower)

        # ── Build criteria ────────────────────────────────────────────────
        criteria = SearchCriteria(
            location=location,
            county=county,
            min_fees=min_fees,
            max_fees=max_fees,
            gender=gender,
            admission_status=admission_status,
            accommodation=accommodation,
            levels=levels,
            unsupported_criteria=unsupported,
            interpretation_notes=notes,
        )

        # ── Clarifying question for vague requests ───────────────────────
        if not criteria.has_any_criteria:
            criteria.clarifying_question = (
                "I'd like to help you find a school! Could you tell me which "
                "district you're looking in (e.g. Kampala, Wakiso), what level "
                "of school you need (primary, secondary, etc.), and any "
                "preferences like boarding or day, boys or girls, or a budget?"
            )

        return criteria


# ── Extraction helpers ────────────────────────────────────────────────────
def _extract_location(text: str, text_lower: str) -> str | None:
    """Match known district names in the text (case-insensitive)."""
    for loc in VALID_LOCATIONS:
        # Match as a whole word to avoid partial matches
        pattern = r"\b" + re.escape(loc) + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            return loc
    return None


def _extract_county(text_lower: str, location: str | None, notes: list[str]) -> str | None:
    """Try to match a county/division from the text."""
    if not location or location not in COUNTY_MAP:
        return None

    valid = COUNTY_MAP[location]

    # Method 1: Match "X division/county/municipality" patterns
    # e.g. "central division" → "KAMPALA CENTRAL DIVISION"
    matches = re.findall(r"(\w+)\s+(division|county|municipality)", text_lower)
    for word, suffix in matches:
        candidate = f"{word} {suffix}".upper()
        if candidate in valid:
            return candidate
        for v in valid:
            if candidate in v or v in candidate:
                notes.append(f"Matched county '{word} {suffix}' -> '{v}'")
                return v

    # Method 2: Match distinctive keywords from county names
    # e.g. parent says "central" → matches "KAMPALA CENTRAL DIVISION"
    for v in valid:
        # Get distinctive words (skip generic suffixes AND the district name itself)
        v_words = set(v.lower().split()) - {
            "division", "county", "municipality",
            "south", "north", "east", "west",
            location.lower() if location else "",
        }
        for word in v_words:
            if len(word) < 4:
                continue
            if re.search(r"\b" + re.escape(word) + r"\b", text_lower):
                notes.append(f"Matched county '{word}' -> '{v}'")
                return v

    return None


def _extract_fees(text_lower: str) -> tuple[int | None, int | None, list[str]]:
    """Extract min/max fees from text using regex patterns."""
    notes: list[str] = []
    min_fees = None
    max_fees = None

    # Normalize text for fee parsing
    # Patterns: "no more than UGX 1 million", "maximum 500,000", "under 1M",
    #           "at least 200,000", "between 100,000 and 500,000",
    #           "charging UGX 500,000", "fees under 1M", "1 million per term"

    # First try "between X and Y" pattern
    between_match = re.search(
        r"between\s+([\d,.]+\s*(?:million|m|thousand|k)?)\s+and\s+([\d,.]+\s*(?:million|m|thousand|k)?)",
        text_lower,
    )
    if between_match:
        min_fees = _parse_fee_amount(between_match.group(1))
        max_fees = _parse_fee_amount(between_match.group(2))
        if min_fees and max_fees:
            notes.append(f"Interpreted fee range: UGX {min_fees:,}–{max_fees:,}")
        return min_fees, max_fees, notes

    # Max fees patterns
    max_patterns = [
        r"(?:no more than|maximum|max|under|below|at most|not exceeding|up to)\s+"
        r"(?:ugx\s*)?([\d,.]+\s*(?:million|m|thousand|k)?)",
        r"(?:ugx\s*)([\d,.]+\s*(?:million|m|thousand|k)?)\s*(?:per\s*term|termly)?"
        r"(?:\s+(?:maximum|max|or\s+less))",
    ]
    for pattern in max_patterns:
        match = re.search(pattern, text_lower)
        if match:
            amount = _parse_fee_amount(match.group(1))
            if amount:
                max_fees = amount
                notes.append(f"Interpreted max fees as UGX {amount:,} per term")
                break

    # Min fees patterns
    min_patterns = [
        r"(?:at least|minimum|min|above|over|starting from)\s+"
        r"(?:ugx\s*)?([\d,.]+\s*(?:million|m|thousand|k)?)",
    ]
    for pattern in min_patterns:
        match = re.search(pattern, text_lower)
        if match:
            amount = _parse_fee_amount(match.group(1))
            if amount:
                min_fees = amount
                notes.append(f"Interpreted min fees as UGX {amount:,} per term")
                break

    return min_fees, max_fees, notes


def _parse_fee_amount(raw: str) -> int | None:
    """Parse a fee amount string like '1 million', '500,000', '1M', '500K'."""
    raw = raw.strip().lower()
    if not raw:
        return None

    # Remove "per term", "termly", etc.
    raw = re.sub(r"\s*(?:per\s*term|termly|per\s*year|yearly|per\s*annum)\s*", "", raw)

    # Handle "million" / "m" suffix
    million_match = re.match(r"([\d,.]+)\s*(?:million|m\b)", raw)
    if million_match:
        num = float(million_match.group(1).replace(",", ""))
        return int(num * 1_000_000)

    # Handle "thousand" / "k" suffix
    thousand_match = re.match(r"([\d,.]+)\s*(?:thousand|k\b)", raw)
    if thousand_match:
        num = float(thousand_match.group(1).replace(",", ""))
        return int(num * 1_000)

    # Plain number
    num_match = re.match(r"([\d,]+)", raw)
    if num_match:
        return int(num_match.group(1).replace(",", ""))

    return None


def _extract_gender(text_lower: str) -> str | None:
    """Match gender keywords."""
    # Check for multi-word patterns first (more specific)
    patterns = [
        (r"girls['\s]*school|all\s*girls|girls\s*only|girls['\s]*boarding", "girls"),
        (r"boys['\s]*school|all\s*boys|boys\s*only|boys['\s]*boarding", "boys"),
        (r"co[-\s]?education|co[-\s]?ed|mixed\s*school|both\s*boys\s*and\s*girls", "mixed"),
    ]
    for pattern, value in patterns:
        if re.search(pattern, text_lower):
            return value
    # Simple single-word matches
    if re.search(r"\bgirls\b", text_lower) and not re.search(r"\bboys\b", text_lower):
        return "girls"
    if re.search(r"\bboys\b", text_lower) and not re.search(r"\bgirls\b", text_lower):
        return "boys"
    if re.search(r"\bmixed\b", text_lower):
        return "mixed"
    return None


def _extract_accommodation(text_lower: str) -> str | None:
    """Match accommodation keywords."""
    if re.search(r"day\s*and\s*boarding|both\s*day\s*and\s*boarding", text_lower):
        return "Day & Boarding"
    if re.search(r"\bboarding\b", text_lower):
        return "Boarding"
    if re.search(r"day\s*school|day\s*scholar|day\s*only", text_lower):
        return "Day"
    return None


def _extract_levels(text_lower: str) -> list[str]:
    """Match school level keywords."""
    levels: list[str] = []

    # Check compound patterns first
    if re.search(r"nursery\s*(?:and|&)\s*kinderga?r?ten", text_lower):
        if "Nursery & Kindergaten" not in levels:
            levels.append("Nursery & Kindergaten")
    if re.search(r"nursery\s*(?:and|&)\s*primary", text_lower):
        if "Nursery & Primary" not in levels:
            levels.append("Nursery & Primary")

    # Single-level patterns
    if re.search(r"\bsecondary\b|\bhigh\s*school\b|\bo\s*level\b|\ba\s*level\b", text_lower):
        if "Secondary" not in levels:
            levels.append("Secondary")
    if re.search(r"\bprimary\b", text_lower) and not re.search(r"nursery\s*(?:and|&)\s*primary", text_lower):
        if "Primary" not in levels:
            levels.append("Primary")
    if re.search(r"\bnursery\b", text_lower) and not re.search(r"nursery\s*(?:and|&)\s*(?:primary|kinderga?r?ten)", text_lower):
        if "Nursery & Primary" not in levels and "Nursery & Kindergaten" not in levels:
            levels.append("Nursery & Primary")
    if re.search(r"\bkinderga?r?ten\b|\bpre[-\s]*school\b", text_lower):
        if "Nursery & Kindergaten" not in levels:
            levels.append("Nursery & Kindergaten")
    if re.search(r"\binternational\b", text_lower):
        if "International" not in levels:
            levels.append("International")

    # Infer secondary from "Senior One/S1/S2..." (Ugandan secondary classes)
    if re.search(r"senior\s*(?:one|1|two|2|three|3|four|4|five|5|six|6)|\bs[1-6]\b", text_lower):
        if "Secondary" not in levels:
            levels.append("Secondary")

    return levels


def _extract_admission_status(text_lower: str) -> str | None:
    """Match admission status keywords."""
    if re.search(r"admissions?\s*open|open\s*for\s*admission|currently\s*admitting|admitting\s*students|accepting\s*(?:new\s*)?students|open\s*for\s*\d{4}", text_lower):
        return "open"
    if re.search(r"admissions?\s*closed|not\s*admitting|closed\s*for\s*admission", text_lower):
        return "closed"
    return None


def _extract_unsupported(text_lower: str) -> list[str]:
    """Detect criteria that eSchool's search cannot filter for."""
    unsupported: list[str] = []

    # Specific class/year admission (e.g., "Senior One", "S1", "Primary 1")
    if re.search(r"senior\s*(?:one|1|two|2|three|3|four|4|five|5|six|6)|\bs[1-6]\b|primary\s*[1-7]|p[1-7]\b|admitting\s+\w+\s+students", text_lower):
        # Extract the specific phrase
        match = re.search(r"(currently\s+)?admitting\s+(.+?)(?:\.|$|and)", text_lower)
        if match:
            unsupported.append(f"admitting {match.group(2).strip()}")
        elif re.search(r"senior\s*(?:one|1|two|2|three|3|four|4|five|5|six|6)", text_lower):
            match = re.search(r"(senior\s*(?:one|1|two|2|three|3|four|4|five|5|six|6)\s*students?)", text_lower)
            if match:
                unsupported.append(f"admitting {match.group(1)}")

    # Sports/extra-curricular quality
    if re.search(r"good\s*sports|sports\s*program|excellent\s*sports|strong\s*sports|sports\s*facilities", text_lower):
        unsupported.append("good sports program")

    # Proximity
    if re.search(r"near\s*(?:my\s*)?home|nearby|close\s*to\s*(?:me|home|town)|walking\s*distance|near\s*here", text_lower):
        unsupported.append("school near home/area")

    # Quality/reputation
    if re.search(r"good\s*reputation|top\s*school|best\s*school|high[-\s]*performing|excellent\s*academic|good\s*results|top\s*performing", text_lower):
        unsupported.append("school quality/reputation")

    # Specific teacher/staff requirements
    if re.search(r"qualified\s*teachers|experienced\s*teachers|good\s*teachers", text_lower):
        unsupported.append("teacher qualifications")

    # Transport (if not matching the facility checkbox)
    if re.search(r"school\s*transport|bus\s*service|transport\s*available", text_lower):
        unsupported.append("school transport service")

    # Deduplicate
    seen = set()
    result = []
    for u in unsupported:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result
