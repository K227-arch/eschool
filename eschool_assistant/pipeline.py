"""Pipeline — orchestrates the full search flow.

Improvements over v1:
- In-memory TTL cache so repeated searches return instantly.
- Smart result ranking: fully-confirmed matches first, then by rating.
- Broadening fallback: if a narrow county/division search returns 0 schools,
  automatically retry at district level so the parent always gets something.
- Deduplication: schools appearing on multiple pages are merged by slug.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Optional

import httpx

from .client import SearchError, build_url, fetch
from .config import DEFAULT_BASE_URL, DEFAULT_TIMEOUT
from .interpreter import Interpreter, LLMError
from .matcher import match_school
from .models import (
    InterpretationStatus,
    MatchStatus,
    SchoolMatchResult,
    SearchCriteria,
    SearchResponse,
)
from .parser import parse_search_results, parse_school_detail
from .rule_interpreter import RuleBasedInterpreter
from .validator import validate

logger = logging.getLogger(__name__)

# ── In-memory TTL cache ───────────────────────────────────────────────────
# Maps cache_key → (SearchResponse, timestamp)
_CACHE: dict[str, tuple[SearchResponse, float]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes — fresh enough, saves repeated fetches


def _cache_key(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def _cached(key: str) -> SearchResponse | None:
    entry = _CACHE.get(key)
    if entry and (time.time() - entry[1]) < CACHE_TTL_SECONDS:
        return entry[0]
    if entry:
        del _CACHE[key]  # expired
    return None


def _store(key: str, response: SearchResponse) -> None:
    _CACHE[key] = (response, time.time())


# ── Detail-page enrichment ────────────────────────────────────────────────
_ENRICH_MAX = 12      # max detail-page fetches per search call
_ENRICH_TTL = 3600    # cache detail pages for 1 hour

_DETAIL_CACHE: dict[str, tuple[dict, float]] = {}


def _detail_cached(slug: str) -> dict | None:
    entry = _DETAIL_CACHE.get(slug)
    if entry and (time.time() - entry[1]) < _ENRICH_TTL:
        return entry[0]
    if entry:
        del _DETAIL_CACHE[slug]
    return None


def _store_detail(slug: str, data: dict) -> None:
    _DETAIL_CACHE[slug] = (data, time.time())


def clear_cache() -> None:
    """Clear all caches — search results and detail pages."""
    _CACHE.clear()
    _DETAIL_CACHE.clear()


def enrich_schools(
    results: list,
    criteria,
    http_client=None,
    timeout: int = DEFAULT_TIMEOUT,
    max_enrich: int = _ENRICH_MAX,
) -> None:
    """Fetch detail pages for the top results and fill in gender/accommodation.

    Mutates each ``SchoolMatchResult.school`` in-place — sets ``gender``,
    ``accommodation``, ``curriculum``, ``religion``, and ``detail_fetched``.

    Only runs when the parent specified gender or accommodation (the two
    criteria that need detail-page data to be confirmed or rejected).
    Caps at ``max_enrich`` HTTP requests to keep the response time reasonable.
    """
    needs_gender = criteria.gender is not None
    needs_accommodation = criteria.accommodation is not None
    needs_fees = criteria.min_fees is not None or criteria.max_fees is not None
    if not needs_gender and not needs_accommodation and not needs_fees:
        logger.debug("Skipping enrichment — no gender/accommodation/fees criteria")
        return

    enriched = 0
    for result in results:
        if enriched >= max_enrich:
            break
        school = result.school
        if school.detail_fetched:
            continue

        # Detail cache hit
        cached = _detail_cached(school.slug)
        if cached:
            _apply_detail(school, cached)
            continue

        # Live fetch
        try:
            detail_html = fetch(school.url, client=http_client, timeout=timeout)
            detail_data = parse_school_detail(detail_html)
            _store_detail(school.slug, detail_data)
            _apply_detail(school, detail_data)
            enriched += 1
        except Exception as exc:
            logger.warning("Detail fetch failed for %s: %s", school.slug, exc)
            school.detail_fetched = True  # don't retry this session


def _apply_detail(school, data: dict) -> None:
    school.gender = data.get("gender")
    school.accommodation = data.get("accommodation")
    school.curriculum = data.get("curriculum")
    school.religion = data.get("religion")
    school.county = data.get("county")
    school.min_fees_per_term = data.get("min_fees_per_term")
    school.max_fees_per_term = data.get("max_fees_per_term")
    school.fees_available = bool(data.get("fees_available"))
    school.detail_fetched = True


# ── Result ranking ────────────────────────────────────────────────────────
def _rank(results: list[SchoolMatchResult]) -> list[SchoolMatchResult]:
    """Sort results so the best matches appear first.

    Tier 1 — no NOT_MATCHING checks + all confirmed  (full match, no unknowns)
    Tier 2 — no NOT_MATCHING checks (full match, some unknowns)
    Tier 3 — has NOT_MATCHING checks (partial mismatch)

    Within each tier, sort by rating descending (unrated schools go last).
    """
    def sort_key(r: SchoolMatchResult):
        not_matching = sum(1 for c in r.checks if c.status == MatchStatus.NOT_MATCHING)
        unknowns = r.unknown_count
        confirmed = r.confirmed_count
        rating = r.school.rating or 0.0

        if not_matching == 0 and unknowns == 0:
            tier = 0  # best: everything confirmed
        elif not_matching == 0:
            tier = 1  # good: passes, some unknowns
        else:
            tier = 2  # worst: something actively doesn't match

        return (tier, -rating)  # lower tier = better; higher rating = better

    return sorted(results, key=sort_key)


# ── Interpreter selection ─────────────────────────────────────────────────
def _default_interpreter() -> tuple[object, str]:
    if os.getenv("GROQ_API_KEY"):
        try:
            return Interpreter(), "AI (Groq)"
        except Exception:
            logger.warning("GROQ_API_KEY set but init failed, falling back")

    if os.getenv("OPENAI_API_KEY"):
        try:
            return Interpreter(), "AI"
        except Exception:
            logger.warning("OPENAI_API_KEY set but init failed, falling back")

    return RuleBasedInterpreter(), "rule-based"


# ── Core fetch + parse helper ─────────────────────────────────────────────
def _fetch_schools(
    criteria: SearchCriteria,
    base_url: str,
    max_pages: int,
    http_client,
    timeout: int,
    notes: list[str],
) -> tuple[list[SchoolMatchResult], int | None, str, str | None]:
    """Fetch, parse, deduplicate and match schools.

    Returns (match_results, total_pages, search_url, error_message).
    """
    search_url = build_url(criteria, base_url=base_url, page=1)

    # Check cache first
    cache_key = _cache_key(search_url)
    cached = _cached(cache_key)
    if cached:
        return cached.schools, cached.total_pages, search_url, None

    try:
        html = fetch(search_url, client=http_client, timeout=timeout)
    except SearchError as exc:
        return [], None, search_url, str(exc)

    schools, total_pages = parse_search_results(html)

    # Fetch additional pages
    seen_slugs: set[str] = {s.slug for s in schools}
    all_schools = list(schools)

    for page in range(2, min(max_pages + 1, (total_pages or 1) + 1)):
        try:
            page_html = fetch(
                build_url(criteria, base_url=base_url, page=page),
                client=http_client,
                timeout=timeout,
            )
            for s in parse_search_results(page_html)[0]:
                if s.slug not in seen_slugs:
                    all_schools.append(s)
                    seen_slugs.add(s.slug)
        except SearchError as exc:
            notes.append(f"Could not fetch page {page}: {exc}")
            break

    # Match and rank
    match_results = _rank([
        SchoolMatchResult(school=s, checks=match_school(s, criteria))
        for s in all_schools
    ])

    # ── Strict location filter ────────────────────────────────────────────
    # eSchool's search bleeds nearby districts into results (e.g. searching
    # "Kampala" also returns Wakiso, Mukono, Buikwe).  When the parent
    # specified a location AND the card shows a *different* district,
    # remove those schools entirely rather than showing them with a ✗.
    if criteria.location:
        before = len(match_results)
        match_results = [
            r for r in match_results
            if r.school.location is None
            or r.school.location.upper() == criteria.location.upper()
        ]
        removed = before - len(match_results)
        if removed:
            notes.append(
                f"{removed} school(s) from other districts were removed "
                f"(eSchool's search includes nearby areas, but you asked "
                f"specifically for {criteria.location.title()})."
            )

    return match_results, total_pages, search_url, None


# ── Main entry point ──────────────────────────────────────────────────────
def search_schools(
    request: str,
    interpreter: object | None = None,
    base_url: str = DEFAULT_BASE_URL,
    max_pages: int = 1,
    http_client: httpx.Client | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> SearchResponse:
    """Run the full search pipeline and return a :class:`SearchResponse`.

    Automatically falls back to rule-based interpretation when no API key
    is set.  Caches results for 5 minutes to speed up repeated searches.
    Ranks results so the best matches appear first.  If a narrow (county-
    level) search returns nothing, automatically retries at district level.
    """
    if interpreter is None:
        interpreter, mode = _default_interpreter()
    else:
        mode = "injected"

    notes: list[str] = []
    # Rule-based mode runs silently — no banner shown to the user.
    # The mode is visible in the web UI header badge and CLI interactive prompt.

    # ── 1. Interpret ─────────────────────────────────────────────────────
    try:
        raw_criteria = interpreter.interpret(request)
    except (LLMError, ValueError) as exc:
        # If AI fails (network block, API down), try rule-based silently
        if mode in ("AI (Groq)", "AI"):
            logger.warning("AI interpreter failed (%s), falling back to rule-based: %s", mode, exc)
            from .rule_interpreter import RuleBasedInterpreter
            try:
                raw_criteria = RuleBasedInterpreter().interpret(request)
                mode = "rule-based (AI fallback)"
            except (ValueError, Exception) as exc2:
                logger.error("Rule-based fallback also failed: %s", exc2)
                return SearchResponse(
                    status=InterpretationStatus.OK,
                    criteria=SearchCriteria(),
                    error=str(exc2),
                    notes=notes,
                )
        else:
            logger.error("Interpretation failed: %s", exc)
            return SearchResponse(
                status=InterpretationStatus.OK,
                criteria=SearchCriteria(),
                error=str(exc),
                notes=notes,
            )

    # ── 2. Validate ──────────────────────────────────────────────────────
    validation = validate(raw_criteria)
    criteria = validation.criteria
    # Only show warnings that are genuinely useful to the user
    # (e.g. "invalid location", "min > max fees").
    # Internal technical notes like "Matched county X → Y" run silently.
    notes.extend(validation.warnings)
    # interpretation_notes (e.g. "Interpreted 1M as 1,000,000") are kept on
    # the criteria object for the design explanation but not shown in the UI.

    # ── 3. Clarification needed? ─────────────────────────────────────────
    if criteria.clarifying_question and not criteria.has_any_criteria:
        return SearchResponse(
            status=InterpretationStatus.NEEDS_CLARIFICATION,
            criteria=criteria,
            notes=notes,
        )

    if not criteria.has_any_criteria:
        notes.append(
            "No searchable criteria were found. "
            "Please mention a location, level, budget, or other preference."
        )
        return SearchResponse(
            status=InterpretationStatus.NEEDS_CLARIFICATION,
            criteria=criteria,
            notes=notes,
        )

    # ── 4. Note unsupported criteria ─────────────────────────────────────
    if criteria.unsupported_criteria:
        notes.append(
            "Could not filter by: "
            + "; ".join(criteria.unsupported_criteria)
            + " (not supported by eSchool search)."
        )

    # ── 5. Fetch (with broadening fallback) ──────────────────────────────
    match_results, total_pages, search_url, error = _fetch_schools(
        criteria, base_url, max_pages, http_client, timeout, notes
    )

    if error:
        return SearchResponse(
            status=InterpretationStatus.OK,
            criteria=criteria,
            search_url=search_url,
            error=error,
            notes=notes,
        )

    # Broadening fallback: county search returned nothing → retry at district
    broadened = False
    if not match_results and criteria.county:
        broader = criteria.model_copy(update={"county": None})
        notes.append(
            f"No results for '{criteria.county}'. "
            f"Widening search to all of {criteria.location or 'the district'}…"
        )
        match_results, total_pages, search_url, error2 = _fetch_schools(
            broader, base_url, max_pages, http_client, timeout, notes
        )
        if error2:
            # Use original error if broadened also fails
            return SearchResponse(
                status=InterpretationStatus.OK,
                criteria=criteria,
                search_url=search_url,
                error=error2,
                notes=notes,
            )
        broadened = True

    # ── 6. Pagination note ────────────────────────────────────────────────
    pages_fetched = min(max_pages, total_pages or 1)
    if total_pages and total_pages > 1:
        notes.append(
            f"Showing page 1 of {total_pages} "
            f"({len(match_results)} schools). "
            "More results may exist on later pages."
        )

    # ── 7. Zero results ───────────────────────────────────────────────────
    if not match_results:
        hint = _relax_hint(criteria)
        notes.append(
            "No schools found matching your criteria. " + hint
        )

    # ── 7b. Enrich with detail-page data (gender, accommodation) ────────
    # Only fetches detail pages when the parent asked for gender or
    # accommodation — and only for the schools that survived filtering.
    if criteria.gender or criteria.accommodation:
        enrich_schools(
            match_results,
            criteria,
            http_client=http_client,
            timeout=timeout,
        )
        # Re-run the matcher on enriched schools so checks use the new data
        for result in match_results:
            result.checks = match_school(result.school, criteria)
        # Re-rank with the now-confirmed/not-matching gender/accommodation checks
        match_results = _rank(match_results)

    # ── 8. Cache the response ────────────────────────────────────────────
    response = SearchResponse(
        status=InterpretationStatus.OK,
        criteria=criteria,
        schools=match_results,
        total_found_on_page=len(match_results),
        total_pages=total_pages,
        page_fetched=pages_fetched,
        search_url=search_url,
        notes=notes,
    )
    if match_results:  # only cache non-empty results
        _store(_cache_key(search_url), response)

    return response


def _relax_hint(criteria: SearchCriteria) -> str:
    """Suggest which filter to relax based on what was specified."""
    suggestions = []
    if criteria.max_fees is not None:
        suggestions.append(f"raise the budget above UGX {criteria.max_fees:,}")
    if criteria.county:
        suggestions.append("remove the division/county filter")
    if criteria.accommodation:
        suggestions.append(f"remove the '{criteria.accommodation}' filter")
    if criteria.gender:
        suggestions.append("try 'mixed' instead of a single gender")
    if criteria.admission_status == "open":
        suggestions.append("remove the 'admissions open' filter")
    if not suggestions:
        suggestions.append("try a different location or broaden the criteria")
    return "Try: " + "; or ".join(suggestions[:3]) + "."
