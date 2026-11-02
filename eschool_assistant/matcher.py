"""Matcher — deterministic check of each school against the search criteria.

The matcher is the most important module for the brief's emphasis on
honesty: it never invents data and never claims a school meets a requirement
when the available information doesn't support that conclusion.

For every criterion the parent specified, the matcher returns a
``CriterionCheck`` with one of three statuses:

*  **CONFIRMED**     — the card data proves the criterion holds.
*  **NOT_MATCHING**   — the card data proves the criterion does *not* hold.
*  **UNKNOWN**        — the criterion was applied as a search filter, but the
   results card doesn't show the relevant field, so it can't be independently
   verified.

Which criteria can be verified from the card?
----------------------------------------------
*  Location — the card shows the school's district.
*  Level — the card shows the school level.
*  Admission status — the card shows "Admissions Closed" / "Open for 2026".
*  Query — we can check the school name against the keyword.

Which criteria are filter-only (UNKNOWN)?
------------------------------------------
*  Fees (min/max) — not shown on the card.
*  Gender — not shown on the card.
*  Accommodation (boarding/day) — not shown on the card.
*  County/division — not shown on the card.
*  Curriculums, facilities, religions — not shown on the card.

For these, the search filter was applied, so the school *should* match — but
we explicitly say we can't independently confirm it from the results page.
"""

from __future__ import annotations

import logging

from .models import CriterionCheck, MatchStatus, School, SearchCriteria

logger = logging.getLogger(__name__)


def match_school(school: School, criteria: SearchCriteria) -> list[CriterionCheck]:
    """Check *school* against every criterion in *criteria*.

    Returns a list of ``CriterionCheck`` objects, one per specified criterion.
    Criteria that the parent did not specify are skipped (no check produced).
    """
    checks: list[CriterionCheck] = []

    if criteria.location:
        checks.append(_check_location(school, criteria.location))

    if criteria.county:
        checks.append(_check_county(school, criteria.county))

    if criteria.min_fees is not None:
        checks.append(_check_min_fees(school, criteria.min_fees))

    if criteria.max_fees is not None:
        checks.append(_check_max_fees(school, criteria.max_fees))

    if criteria.gender:
        checks.append(_check_gender(school, criteria.gender))

    if criteria.admission_status:
        checks.append(_check_admission_status(school, criteria.admission_status))

    if criteria.accommodation:
        checks.append(_check_accommodation(school, criteria.accommodation))

    if criteria.levels:
        checks.append(_check_levels(school, criteria.levels))

    for curriculum in criteria.curriculums:
        checks.append(_check_curriculum(school, curriculum))

    for facility in criteria.facilities:
        checks.append(_check_facility(school, facility))

    for religion in criteria.religions:
        checks.append(_check_religion(school, religion))

    if criteria.query:
        checks.append(_check_query(school, criteria.query))

    return checks


def match_schools(
    schools: list[School], criteria: SearchCriteria
) -> list[CriterionCheck] | None:
    """Match a list of schools — convenience wrapper returning a list of
    ``SchoolMatchResult`` (imported lazily to avoid a circular import).
    """
    from .models import SchoolMatchResult

    results = []
    for school in schools:
        checks = match_school(school, criteria)
        results.append(SchoolMatchResult(school=school, checks=checks))
    return results


# ── Individual criterion checks ────────────────────────────────────────────
def _check_location(school: School, expected: str) -> CriterionCheck:
    """Compare the school's card location (district) with the requested one."""
    expected_upper = expected.strip().upper()

    if school.location:
        actual_upper = school.location.strip().upper()
        if actual_upper == expected_upper:
            return CriterionCheck(
                criterion=f"Location: {expected}",
                status=MatchStatus.CONFIRMED,
                detail=f"School is in {school.location}.",
            )
        else:
            return CriterionCheck(
                criterion=f"Location: {expected}",
                status=MatchStatus.NOT_MATCHING,
                detail=(
                    f"School is in {school.location}, not {expected}. "
                    "It appeared because eSchool's location search includes "
                    "nearby areas."
                ),
            )

    return CriterionCheck(
        criterion=f"Location: {expected}",
        status=MatchStatus.UNKNOWN,
        detail="Location not shown on the results card.",
    )


def _check_county(school: School, expected: str) -> CriterionCheck:
    """County/division is not shown on the card — filtered by search only."""
    return CriterionCheck(
        criterion=f"Division/County: {expected}",
        status=MatchStatus.UNKNOWN,
        detail=(
            "The search filtered for this division, but the specific "
            "division is not shown on the results card."
        ),
    )


def _check_min_fees(school: School, min_fees: int) -> CriterionCheck:
    """Fees are not shown on the card — filtered by search only."""
    return CriterionCheck(
        criterion=f"Min fees: UGX {min_fees:,}",
        status=MatchStatus.UNKNOWN,
        detail=(
            "Fees are not displayed on the search results card. "
            "The search filtered for this minimum, but it cannot be "
            "independently verified here."
        ),
    )


def _check_max_fees(school: School, max_fees: int) -> CriterionCheck:
    """Fees are not shown on the card — filtered by search only."""
    return CriterionCheck(
        criterion=f"Max fees: UGX {max_fees:,}",
        status=MatchStatus.UNKNOWN,
        detail=(
            "Fees are not displayed on the search results card. "
            "The search filtered for this maximum, but it cannot be "
            "independently verified here. Check the school's detail page "
            "for actual fees."
        ),
    )


def _check_gender(school: School, expected: str) -> CriterionCheck:
    """Check gender — CONFIRMED/NOT_MATCHING when detail page was fetched,
    UNKNOWN (filter-only) otherwise."""
    label = {"mixed": "Mixed (co-education)", "boys": "Boys only", "girls": "Girls only"}
    criterion = f"Gender: {label.get(expected, expected)}"

    if school.detail_fetched and school.gender is not None:
        if school.gender.lower() == expected.lower():
            return CriterionCheck(
                criterion=criterion,
                status=MatchStatus.CONFIRMED,
                detail=f"School detail page confirms: {school.gender}.",
            )
        else:
            label_actual = label.get(school.gender, school.gender)
            return CriterionCheck(
                criterion=criterion,
                status=MatchStatus.NOT_MATCHING,
                detail=f"School is {label_actual}, not {label.get(expected, expected)}.",
            )

    if school.detail_fetched and school.gender is None:
        return CriterionCheck(
            criterion=criterion,
            status=MatchStatus.UNKNOWN,
            detail="Gender not listed on the school's detail page.",
        )

    return CriterionCheck(
        criterion=criterion,
        status=MatchStatus.UNKNOWN,
        detail=(
            "Gender filter was applied, but not yet verified from the detail page."
        ),
    )


def _check_admission_status(school: School, expected: str) -> CriterionCheck:
    """Check admission status from the card badge.

    The card shows "Admissions Closed" or "Open for 2026" etc.
    We interpret these to determine if admissions are open or closed.
    """
    expected_open = expected.strip().lower() == "open"

    if not school.admission_status:
        return CriterionCheck(
            criterion=f"Admission status: {'Open' if expected_open else 'Closed'}",
            status=MatchStatus.UNKNOWN,
            detail="Admission status not shown on the results card.",
        )

    status_text = school.admission_status.lower()
    is_open = "open" in status_text and "closed" not in status_text
    is_closed = "closed" in status_text

    if is_open:
        actual = "open"
    elif is_closed:
        actual = "closed"
    else:
        actual = "unknown"

    if actual == "unknown":
        return CriterionCheck(
            criterion=f"Admission status: {'Open' if expected_open else 'Closed'}",
            status=MatchStatus.UNKNOWN,
            detail=f"Card shows: '{school.admission_status}' — could not determine status.",
        )

    if actual == ("open" if expected_open else "closed"):
        return CriterionCheck(
            criterion=f"Admission status: {'Open' if expected_open else 'Closed'}",
            status=MatchStatus.CONFIRMED,
            detail=f"Card shows: '{school.admission_status}'.",
        )
    else:
        return CriterionCheck(
            criterion=f"Admission status: {'Open' if expected_open else 'Closed'}",
            status=MatchStatus.NOT_MATCHING,
            detail=f"Card shows: '{school.admission_status}', but you asked for "
            f"{'open' if expected_open else 'closed'} admissions.",
        )


def _check_accommodation(school: School, expected: str) -> CriterionCheck:
    """Check accommodation — CONFIRMED/NOT_MATCHING when detail page was
    fetched, UNKNOWN otherwise."""
    criterion = f"Accommodation: {expected}"

    if school.detail_fetched and school.accommodation is not None:
        # Exact match
        if school.accommodation.lower() == expected.lower():
            return CriterionCheck(
                criterion=criterion,
                status=MatchStatus.CONFIRMED,
                detail=f"School detail page confirms: {school.accommodation}.",
            )
        # "Day & Boarding" satisfies both "Boarding" and "Day" requests
        if school.accommodation == "Day & Boarding" and expected in ("Boarding", "Day"):
            return CriterionCheck(
                criterion=criterion,
                status=MatchStatus.CONFIRMED,
                detail=(
                    f"School is {school.accommodation}, which includes "
                    f"{expected} option."
                ),
            )
        return CriterionCheck(
            criterion=criterion,
            status=MatchStatus.NOT_MATCHING,
            detail=f"School is {school.accommodation}, not {expected}.",
        )

    if school.detail_fetched and school.accommodation is None:
        return CriterionCheck(
            criterion=criterion,
            status=MatchStatus.UNKNOWN,
            detail="Accommodation/boarding status not listed on detail page.",
        )

    return CriterionCheck(
        criterion=criterion,
        status=MatchStatus.UNKNOWN,
        detail="Accommodation filter was applied, not yet verified from detail page.",
    )


def _check_levels(school: School, expected_levels: list[str]) -> CriterionCheck:
    """Check the school's level against the requested levels."""
    if not school.level:
        return CriterionCheck(
            criterion=f"School level: {', '.join(expected_levels)}",
            status=MatchStatus.UNKNOWN,
            detail="School level not shown on the results card.",
        )

    school_level_lower = school.level.lower()
    for expected in expected_levels:
        if school_level_lower == expected.lower():
            return CriterionCheck(
                criterion=f"School level: {', '.join(expected_levels)}",
                status=MatchStatus.CONFIRMED,
                detail=f"School level: {school.level}.",
            )

    return CriterionCheck(
        criterion=f"School level: {', '.join(expected_levels)}",
        status=MatchStatus.NOT_MATCHING,
        detail=f"School level is {school.level}, which doesn't match the requested level(s).",
    )


def _check_curriculum(school: School, curriculum: str) -> CriterionCheck:
    """Curriculum is not shown on the card — filtered by search only."""
    return CriterionCheck(
        criterion=f"Curriculum: {curriculum}",
        status=MatchStatus.UNKNOWN,
        detail=(
            "Curriculum is not shown on the results card. "
            "The search filtered for this, but it cannot be independently "
            "verified here."
        ),
    )


def _check_facility(school: School, facility: str) -> CriterionCheck:
    """Facilities are not shown on the card — filtered by search only."""
    return CriterionCheck(
        criterion=f"Facility: {facility}",
        status=MatchStatus.UNKNOWN,
        detail=(
            "Facilities are not listed on the results card. "
            "The search filtered for this, but it cannot be independently "
            "verified here."
        ),
    )


def _check_religion(school: School, religion: str) -> CriterionCheck:
    """Religion/affiliation is not shown on the card — filtered by search only."""
    return CriterionCheck(
        criterion=f"Religion: {religion}",
        status=MatchStatus.UNKNOWN,
        detail=(
            "Religious affiliation is not shown on the results card. "
            "The search filtered for this, but it cannot be independently "
            "verified here."
        ),
    )


def _check_query(school: School, query: str) -> CriterionCheck:
    """Check if the school name contains the search keyword."""
    if not query:
        return CriterionCheck(
            criterion=f"Name search: '{query}'",
            status=MatchStatus.UNKNOWN,
            detail="No search keyword was provided.",
        )

    if query.lower() in school.name.lower():
        return CriterionCheck(
            criterion=f"Name search: '{query}'",
            status=MatchStatus.CONFIRMED,
            detail=f"School name '{school.name}' contains '{query}'.",
        )

    return CriterionCheck(
        criterion=f"Name search: '{query}'",
        status=MatchStatus.UNKNOWN,
        detail=(
            f"School name '{school.name}' doesn't obviously contain '{query}'. "
            "It may have matched on other criteria."
        ),
    )
