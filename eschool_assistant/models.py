"""Pydantic models — the data contracts shared across the pipeline.

The flow is::

    parent text  ──►  SearchCriteria  ──►  [URL build + fetch + parse]  ──►  School list
                                              │
                                              └──►  Matcher  ──►  SchoolMatchResult list
                                                                        │
                                                                        └──►  Presenter

Every field that the parent *did not mention* is ``None`` / empty.  This gives
us the "specified vs. unspecified" distinction the brief requires: the matcher
only checks criteria that are actually present, and the presenter explicitly
says which filters were applied.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums for clarity ──────────────────────────────────────────────────────
class MatchStatus(str, Enum):
    """Outcome of checking one criterion against one school."""

    CONFIRMED = "confirmed"      # ✅ the parsed data proves the criterion holds
    NOT_MATCHING = "not_matching"  # ❌ the parsed data proves it does *not* hold
    UNKNOWN = "unknown"          # ❓ can't tell from the available data


class InterpretationStatus(str, Enum):
    """High-level outcome of the AI interpretation step."""

    OK = "ok"                      # criteria extracted, ready to search
    NEEDS_CLARIFICATION = "needs_clarification"  # too vague — ask the parent


# ── SearchCriteria (produced by the AI interpreter) ───────────────────────
class SearchCriteria(BaseModel):
    """Structured search criteria extracted from a parent's request.

    Every field defaults to ``None`` / empty so that *unspecified* is
    distinguishable from *specified*.  The AI is instructed to only fill in
    a field when the parent explicitly mentions it.
    """

    # Core location filters
    location: Optional[str] = Field(
        None, description="District, uppercase, e.g. 'KAMPALA'"
    )
    county: Optional[str] = Field(
        None, description="Division/county, uppercase, e.g. 'KAMPALA CENTRAL DIVISION'"
    )

    # Fees (UGX per term)
    min_fees: Optional[int] = Field(None, description="Minimum fees in UGX per term")
    max_fees: Optional[int] = Field(None, description="Maximum fees in UGX per term")
    # Single-value filters
    gender: Optional[str] = Field(None, description="'mixed', 'boys', or 'girls'")
    admission_status: Optional[str] = Field(
        None, description="'open' or 'closed'"
    )
    accommodation: Optional[str] = Field(
        None, description="'Boarding', 'Day', or 'Day & Boarding'"
    )
    sorting: Optional[str] = Field(None, description="'Popular', 'FeesLow', or 'Newest'")

    # Multi-value filters
    levels: list[str] = Field(
        default_factory=list, description="School levels, e.g. ['Secondary']"
    )
    curriculums: list[str] = Field(default_factory=list)
    facilities: list[str] = Field(default_factory=list)
    religions: list[str] = Field(default_factory=list)

    # Free-text school-name search
    query: Optional[str] = Field(None, description="School name keyword")

    # ── Metadata the AI adds to help the rest of the pipeline ─────────────
    #: Criteria the parent mentioned but eSchool's search cannot filter for
    #: (e.g. "admitting Senior One students", "good sports program").
    #: These are reported back to the parent as limitations.
    unsupported_criteria: list[str] = Field(default_factory=list)

    #: A human-readable clarifying question.  When non-empty, the pipeline
    #: stops and asks this question instead of searching.
    clarifying_question: Optional[str] = None

    #: Free-form notes about interpretation decisions (e.g. "assumed '1M' means
    #: max 1 000 000 UGX per term").
    interpretation_notes: list[str] = Field(default_factory=list)

    @property
    def has_any_criteria(self) -> bool:
        """True when at least one usable search filter is set."""
        return any(
            [
                self.location,
                self.county,
                self.min_fees is not None,
                self.max_fees is not None,
                self.gender,
                self.admission_status,
                self.accommodation,
                self.query,
                bool(self.levels),
                bool(self.curriculums),
                bool(self.facilities),
                bool(self.religions),
            ]
        )


# ── School (parsed from the search-results HTML) ──────────────────────────
class School(BaseModel):
    """A single school card parsed from the eSchool search results page.

    Fields populated from the *search results card* (always available):
        name, slug, url, school_id, level, rating, location,
        admission_status, image_url

    Fields populated from the *school detail page* (via enrichment):
        gender, accommodation, curriculum, religion, detail_fetched
    """

    name: str
    slug: str
    url: str
    school_id: Optional[str] = None
    level: Optional[str] = None        # e.g. "Secondary", "Primary"
    rating: Optional[float] = None     # e.g. 4.3; None when "0.0" / no ratings
    location: Optional[str] = None     # district shown on the card
    admission_status: Optional[str] = None  # "Admissions Closed", "Open for 2026"
    image_url: Optional[str] = None

    # ── Detail-page fields (populated by enrich_schools) ─────────────────
    gender: Optional[str] = None        # "girls", "boys", "mixed"
    accommodation: Optional[str] = None  # "Boarding", "Day", "Day & Boarding"
    curriculum: Optional[str] = None    # e.g. "UNEB", "Cambridge"
    religion: Optional[str] = None      # e.g. "Catholic"
    county: Optional[str] = None        # e.g. "RUBAGA DIVISION NORTH"
    min_fees_per_term: Optional[int] = None  # minimum published termly fee (UGX)
    max_fees_per_term: Optional[int] = None  # maximum published termly fee (UGX)
    fees_available: bool = False         # True when real fee amounts were found
    detail_fetched: bool = False         # True once the detail page was parsed


# ── Criterion check result ────────────────────────────────────────────────
class CriterionCheck(BaseModel):
    """The result of evaluating one criterion against one school."""

    criterion: str           # human label, e.g. "Max fees ≤ UGX 1 000 000"
    status: MatchStatus
    detail: str = ""          # human-readable explanation


# ── School match result ───────────────────────────────────────────────────
class SchoolMatchResult(BaseModel):
    """A school paired with the outcome of checking every criterion."""

    school: School
    checks: list[CriterionCheck] = Field(default_factory=list)

    @property
    def is_full_match(self) -> bool:
        """True when no criterion is NOT_MATCHING (UNKNOWN is acceptable)."""
        return all(c.status != MatchStatus.NOT_MATCHING for c in self.checks)

    @property
    def confirmed_count(self) -> int:
        return sum(1 for c in self.checks if c.status == MatchStatus.CONFIRMED)

    @property
    def unknown_count(self) -> int:
        return sum(1 for c in self.checks if c.status == MatchStatus.UNKNOWN)


# ── Full search response ──────────────────────────────────────────────────
class SearchResponse(BaseModel):
    """The complete result returned to the CLI / API / presenter."""

    status: InterpretationStatus
    criteria: SearchCriteria
    schools: list[SchoolMatchResult] = Field(default_factory=list)
    total_found_on_page: int = 0
    total_pages: Optional[int] = None  # when pagination info is available
    page_fetched: int = 1
    search_url: Optional[str] = None
    error: Optional[str] = None  # populated when the search itself fails
    notes: list[str] = Field(default_factory=list)  # pipeline-level notes
