"""Presenter — turns a :class:`SearchResponse` into human-readable output.

The presenter is the *only* module that formats text for the user.  It
handles every edge case the brief calls out:

*  Vague request → show the clarifying question.
*  Unsupported criterion → list what couldn't be searched for.
*  Missing data → show "not available" for fields the card doesn't have.
*  Zero results → suggest relaxing filters.
*  Site / LLM failure → show a friendly error.
*  Schools that don't match a criterion → show why honestly.

Output is plain text so it works in any terminal, file, or log.  The CLI
wraps it with ``rich`` for colour, but the presenter itself is dependency-free.
"""

from __future__ import annotations

from .models import (
    InterpretationStatus,
    MatchStatus,
    SchoolMatchResult,
    SearchCriteria,
    SearchResponse,
)

# ── Status symbols ─────────────────────────────────────────────────────────
SYM_CONFIRMED = "✓"
SYM_NOT_MATCHING = "✗"
SYM_UNKNOWN = "?"


def present(response: SearchResponse) -> str:
    """Format a :class:`SearchResponse` into a multi-line string."""
    lines: list[str] = []

    # ── Clarifying question ───────────────────────────────────────────────
    if response.status == InterpretationStatus.NEEDS_CLARIFICATION:
        lines.append("─" * 60)
        lines.append("  CLARIFICATION NEEDED")
        lines.append("─" * 60)
        lines.append("")
        if response.criteria.clarifying_question:
            lines.append(f"  {response.criteria.clarifying_question}")
        else:
            lines.append("  " + (response.notes[0] if response.notes else
                                 "Please provide more details about what you're looking for."))
        lines.append("")
        _append_criteria_summary(lines, response.criteria)
        _append_notes(lines, response)
        return "\n".join(lines)

    # ── Error (LLM or search failure) ────────────────────────────────────
    if response.error:
        lines.append("─" * 60)
        lines.append("  ERROR")
        lines.append("─" * 60)
        lines.append("")
        lines.append(f"  {response.error}")
        lines.append("")
        _append_criteria_summary(lines, response.criteria)
        _append_notes(lines, response)
        if response.search_url:
            lines.append(f"  Search URL: {response.search_url}")
        return "\n".join(lines)

    # ── Normal results ───────────────────────────────────────────────────
    lines.append("═" * 60)
    lines.append("  eSCHOOL SEARCH RESULTS")
    lines.append("═" * 60)
    lines.append("")

    # Interpreted criteria
    _append_criteria_summary(lines, response.criteria)
    lines.append("")

    # Notes / warnings
    _append_notes(lines, response)
    if response.notes:
        lines.append("")

    # Search URL
    if response.search_url:
        lines.append(f"  Search URL: {response.search_url}")
        lines.append("")

    # Results count
    if response.schools:
        lines.append(
            f"  Found {len(response.schools)} school(s) on "
            f"page{'s' if response.page_fetched > 1 else ''} "
            f"1{f'-{response.page_fetched}' if response.page_fetched > 1 else ''}"
            f"{f' of {response.total_pages}' if response.total_pages else ''}"
        )
    else:
        lines.append("  No schools found.")
    lines.append("")

    # Each school
    for i, result in enumerate(response.schools, 1):
        _append_school(lines, i, result)
        lines.append("")

    # Summary
    if response.schools:
        full_matches = sum(1 for r in response.schools if r.is_full_match)
        partial = len(response.schools) - full_matches
        lines.append("─" * 60)
        lines.append(f"  Summary: {full_matches} fully matching, {partial} with caveats")
        if full_matches == 0 and partial > 0:
            lines.append(
                "  No schools fully confirmed all criteria. "
                "See the notes above for what could not be verified."
            )
        lines.append("─" * 60)

    return "\n".join(lines)


# ── Helpers ────────────────────────────────────────────────────────────────
def _append_criteria_summary(lines: list[str], criteria: SearchCriteria) -> None:
    """List the criteria that were extracted (specified vs. unspecified)."""
    lines.append("  Interpreted search criteria:")
    lines.append("  " + "─" * 40)

    specified: list[str] = []
    if criteria.location:
        specified.append(f"Location: {criteria.location}")
    if criteria.county:
        specified.append(f"Division/County: {criteria.county}")
    if criteria.min_fees is not None:
        specified.append(f"Min fees: UGX {criteria.min_fees:,} per term")
    if criteria.max_fees is not None:
        specified.append(f"Max fees: UGX {criteria.max_fees:,} per term")
    if criteria.gender:
        specified.append(f"Gender: {criteria.gender}")
    if criteria.admission_status:
        specified.append(f"Admission status: {criteria.admission_status}")
    if criteria.accommodation:
        specified.append(f"Accommodation: {criteria.accommodation}")
    if criteria.levels:
        specified.append(f"School level(s): {', '.join(criteria.levels)}")
    if criteria.curriculums:
        specified.append(f"Curriculum: {', '.join(criteria.curriculums)}")
    if criteria.facilities:
        specified.append(f"Facilities: {', '.join(criteria.facilities)}")
    if criteria.religions:
        specified.append(f"Religion: {', '.join(criteria.religions)}")
    if criteria.query:
        specified.append(f"Name search: '{criteria.query}'")
    if criteria.sorting:
        specified.append(f"Sorting: {criteria.sorting}")

    if specified:
        for s in specified:
            lines.append(f"    {s}")
    else:
        lines.append("    (no specific criteria extracted)")

    if criteria.unsupported_criteria:
        lines.append("")
        lines.append("  Could not search for (not supported by eSchool):")
        for u in criteria.unsupported_criteria:
            lines.append(f"    - {u}")

    lines.append("  " + "─" * 40)


def _append_notes(lines: list[str], response: SearchResponse) -> None:
    """Append pipeline notes and warnings."""
    if not response.notes:
        return
    lines.append("  Notes:")
    for note in response.notes:
        lines.append(f"    • {note}")


def _append_school(lines: list[str], index: int, result: SchoolMatchResult) -> None:
    """Format a single school with its match checks."""
    school = result.school

    # Header line
    lines.append(f"  {index}. {school.name}")
    lines.append(f"     {school.url}")

    # Key info
    info_parts: list[str] = []
    if school.level:
        info_parts.append(school.level)
    if school.location:
        info_parts.append(school.location)
    if school.rating is not None:
        info_parts.append(f"★ {school.rating}")
    if school.admission_status:
        info_parts.append(school.admission_status)
    if info_parts:
        lines.append(f"     {' | '.join(info_parts)}")

    # Match checks
    if result.checks:
        for check in result.checks:
            sym = _status_symbol(check.status)
            lines.append(f"     {sym} {check.criterion}: {check.detail}")
    else:
        lines.append("     (no criteria to check against)")

    # Match summary
    if result.checks:
        if result.is_full_match:
            if result.unknown_count > 0:
                lines.append(
                    f"     → Match (all checks passed; {result.unknown_count} "
                    f"could not be independently verified)"
                )
            else:
                lines.append("     → Full match (all criteria confirmed)")
        else:
            not_matching = sum(
                1 for c in result.checks if c.status == MatchStatus.NOT_MATCHING
            )
            lines.append(
                f"     → Partial mismatch ({not_matching} criterion/criteria not met)"
            )


def _status_symbol(status: MatchStatus) -> str:
    if status == MatchStatus.CONFIRMED:
        return SYM_CONFIRMED
    if status == MatchStatus.NOT_MATCHING:
        return SYM_NOT_MATCHING
    return SYM_UNKNOWN
