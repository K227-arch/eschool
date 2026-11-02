"""Validator — normalises and validates the AI's raw ``SearchCriteria``.

The interpreter returns whatever the LLM produced.  This module cleans it up:
normalises case, maps plain-English aliases to canonical values, checks each
value against the real eSchool dropdown options, and adds notes about what it
changed.  Invalid values are *not* silently dropped — they are reported so the
presenter can tell the parent.

The result is a new ``SearchCriteria`` with canonical values plus any
``interpretation_notes`` the validator added.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import (
    ACCOMMODATION_ALIASES,
    ADMISSION_ALIASES,
    COUNTY_MAP,
    GENDER_ALIASES,
    VALID_ADMISSION_STATUSES,
    VALID_ACCOMMODATIONS,
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


@dataclass
class ValidationResult:
    """Returned by :func:`validate`."""

    criteria: SearchCriteria  # cleaned-up criteria
    warnings: list[str]  # issues the parent should know about


def validate(criteria: SearchCriteria) -> ValidationResult:
    """Normalise and validate ``criteria`` against the known eSchool filters.

    Returns a :class:`ValidationResult` with the cleaned criteria and a list
    of human-readable warnings for anything that was repaired or rejected.
    """
    warnings: list[str] = []
    notes: list[str] = list(criteria.interpretation_notes)

    # ── Location ──────────────────────────────────────────────────────────
    location = _normalise_location(criteria.location)
    if criteria.location and location is None:
        warnings.append(
            f"Location '{criteria.location}' is not a recognised Ugandan district. "
            "It was ignored — please check the spelling."
        )
        notes.append(f"Removed unrecognised location: '{criteria.location}'")
        location = None
    elif location and location != criteria.location:
        notes.append(f"Normalised location: '{criteria.location}' → '{location}'")

    # ── County ────────────────────────────────────────────────────────────
    county = _normalise_county(criteria.county, location, warnings, notes)

    # ── Fees ──────────────────────────────────────────────────────────────
    min_fees, max_fees = _normalise_fees(
        criteria.min_fees, criteria.max_fees, warnings, notes
    )

    # ── Gender ────────────────────────────────────────────────────────────
    gender = _normalise_single(
        criteria.gender, GENDER_ALIASES, VALID_GENDERS, "gender", warnings, notes
    )

    # ── Admission status ─────────────────────────────────────────────────
    admission_status = _normalise_single(
        criteria.admission_status,
        ADMISSION_ALIASES,
        VALID_ADMISSION_STATUSES,
        "admission status",
        warnings,
        notes,
    )

    # ── Accommodation ────────────────────────────────────────────────────
    accommodation = _normalise_single(
        criteria.accommodation,
        ACCOMMODATION_ALIASES,
        VALID_ACCOMMODATIONS,
        "accommodation",
        warnings,
        notes,
    )

    # ── Levels (multi-value) ─────────────────────────────────────────────
    levels = _normalise_multi(
        criteria.levels, VALID_LEVELS, "school level", warnings, notes
    )

    # ── Curriculums ───────────────────────────────────────────────────────
    curriculums = _normalise_multi(
        criteria.curriculums, VALID_CURRICULUMS, "curriculum", warnings, notes
    )

    # ── Facilities ───────────────────────────────────────────────────────
    facilities = _normalise_multi(
        criteria.facilities, VALID_FACILITIES, "facility", warnings, notes
    )

    # ── Religions ────────────────────────────────────────────────────────
    religions = _normalise_multi(
        criteria.religions, VALID_RELIGIONS, "religion", warnings, notes
    )

    # ── Sorting ──────────────────────────────────────────────────────────
    sorting = _normalise_sorting(criteria.sorting, warnings, notes)

    cleaned = SearchCriteria(
        location=location,
        county=county,
        min_fees=min_fees,
        max_fees=max_fees,
        gender=gender,
        admission_status=admission_status,
        accommodation=accommodation,
        sorting=sorting,
        levels=levels,
        curriculums=curriculums,
        facilities=facilities,
        religions=religions,
        query=criteria.query,
        unsupported_criteria=criteria.unsupported_criteria,
        clarifying_question=criteria.clarifying_question,
        interpretation_notes=notes,
    )

    return ValidationResult(criteria=cleaned, warnings=warnings)


# ── Field-level normalisers ────────────────────────────────────────────────
def _normalise_location(raw: str | None) -> str | None:
    if not raw:
        return None
    upper = raw.strip().upper()
    if upper in VALID_LOCATIONS:
        return upper
    return None


def _normalise_county(
    raw: str | None,
    location: str | None,
    warnings: list[str],
    notes: list[str],
) -> str | None:
    if not raw:
        return None
    upper = raw.strip().upper()

    # If we know the valid counties for this location, validate
    if location and location in COUNTY_MAP:
        valid = COUNTY_MAP[location]
        if upper in valid:
            return upper
        # Try a fuzzy match (contains / starts-with)
        fuzzy = _fuzzy_match(upper, valid)
        if fuzzy:
            notes.append(f"Matched county '{raw}' → '{fuzzy}'")
            return fuzzy
        warnings.append(
            f"County/division '{raw}' was not found among the divisions of "
            f"{location}. It was ignored."
        )
        notes.append(f"Removed unrecognised county: '{raw}'")
        return None

    # Location unknown or not in our map — pass through uppercased
    return upper


def _normalise_fees(
    min_fees: int | None,
    max_fees: int | None,
    warnings: list[str],
    notes: list[str],
) -> tuple[int | None, int | None]:
    if min_fees is not None and min_fees < 0:
        warnings.append("Minimum fees cannot be negative; it was removed.")
        min_fees = None

    if max_fees is not None and max_fees < 0:
        warnings.append("Maximum fees cannot be negative; it was removed.")
        max_fees = None

    if min_fees is not None and max_fees is not None and min_fees > max_fees:
        warnings.append(
            f"Min fees ({min_fees:,}) is greater than max fees ({max_fees:,}); "
            "the range was swapped."
        )
        min_fees, max_fees = max_fees, min_fees

    return min_fees, max_fees


def _normalise_single(
    raw: str | None,
    aliases: dict[str, str],
    valid: frozenset[str],
    label: str,
    warnings: list[str],
    notes: list[str],
) -> str | None:
    if not raw:
        return None
    key = raw.strip().lower()
    if key in aliases:
        return aliases[key]
    # Maybe it's already a canonical value (case-insensitive)
    for v in valid:
        if v.lower() == key:
            return v
    warnings.append(f"Unrecognised {label}: '{raw}'. It was ignored.")
    notes.append(f"Removed unrecognised {label}: '{raw}'")
    return None


def _normalise_multi(
    raw_list: list[str],
    valid: frozenset[str],
    label: str,
    warnings: list[str],
    notes: list[str],
) -> list[str]:
    result: list[str] = []
    for raw in raw_list:
        if not raw:
            continue
        # Exact match (case-insensitive)
        matched = None
        for v in valid:
            if v.lower() == raw.strip().lower():
                matched = v
                break
        if matched:
            if matched not in result:
                result.append(matched)
        else:
            # Fuzzy match
            fuzzy = _fuzzy_match(raw.strip().lower(), {v.lower() for v in valid})
            if fuzzy:
                # Map back to canonical form
                for v in valid:
                    if v.lower() == fuzzy:
                        if v not in result:
                            result.append(v)
                        matched = v
                        break
            if not matched:
                warnings.append(
                    f"Unrecognised {label}: '{raw}'. It was ignored."
                )
                notes.append(f"Removed unrecognised {label}: '{raw}'")
    return result


def _normalise_sorting(
    raw: str | None, warnings: list[str], notes: list[str]
) -> str | None:
    if not raw:
        return None
    for v in VALID_SORTING:
        if v.lower() == raw.strip().lower():
            return v
    warnings.append(f"Unrecognised sorting: '{raw}'. It was ignored.")
    return None


def _fuzzy_match(value: str, candidates: list[str] | set[str]) -> str | None:
    """Simple fuzzy matching for county/level names.

    Tries substring containment in both directions, then checks if the
    value starts with or ends with a candidate.
    """
    value_lower = value.lower().strip()
    for c in candidates:
        c_lower = c.lower().strip()
        if value_lower == c_lower:
            return c
        if c_lower in value_lower or value_lower in c_lower:
            return c
    # Try word-by-word overlap
    value_words = set(value_lower.split())
    for c in candidates:
        c_words = set(c.lower().split())
        if value_words & c_words and len(value_words & c_words) >= 1:
            # Only accept if there's meaningful overlap (not just "county")
            meaningful = value_words & c_words - {"county", "division", "municipality", "the", "a"}
            if meaningful:
                return c
    return None
