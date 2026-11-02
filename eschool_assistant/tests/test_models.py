"""Tests for the Pydantic data models."""
from eschool_assistant.models import (
    CriterionCheck,
    InterpretationStatus,
    MatchStatus,
    School,
    SchoolMatchResult,
    SearchCriteria,
    SearchResponse,
)


class TestSearchCriteria:
    def test_defaults_all_none(self):
        c = SearchCriteria()
        assert c.location is None
        assert c.county is None
        assert c.min_fees is None
        assert c.max_fees is None
        assert c.gender is None
        assert c.admission_status is None
        assert c.accommodation is None
        assert c.query is None
        assert c.levels == []
        assert c.curriculums == []
        assert c.facilities == []
        assert c.religions == []
        assert c.unsupported_criteria == []
        assert c.clarifying_question is None
        assert c.interpretation_notes == []

    def test_has_any_criteria_true_with_location(self):
        c = SearchCriteria(location="KAMPALA")
        assert c.has_any_criteria is True

    def test_has_any_criteria_true_with_levels(self):
        c = SearchCriteria(levels=["Secondary"])
        assert c.has_any_criteria is True

    def test_has_any_criteria_false_when_empty(self, empty_criteria):
        assert empty_criteria.has_any_criteria is False

    def test_has_any_criteria_false_with_only_clarifying_question(self):
        c = SearchCriteria(clarifying_question="What are you looking for?")
        assert c.has_any_criteria is False


class TestSchool:
    def test_school_creation(self):
        s = School(
            name="Test School",
            slug="test-school",
            url="https://eschool.ug/find-schools?slug=test-school",
            level="Secondary",
            rating=4.5,
            location="Kampala",
            admission_status="Open for 2026",
        )
        assert s.name == "Test School"
        assert s.slug == "test-school"
        assert s.level == "Secondary"
        assert s.rating == 4.5
        assert s.location == "Kampala"

    def test_school_with_none_fields(self):
        s = School(name="Test", slug="test", url="https://example.com")
        assert s.school_id is None
        assert s.level is None
        assert s.rating is None
        assert s.location is None
        assert s.admission_status is None


class TestSchoolMatchResult:
    def test_is_full_match_with_confirmed_and_unknown(self):
        checks = [
            CriterionCheck(criterion="Location", status=MatchStatus.CONFIRMED),
            CriterionCheck(criterion="Fees", status=MatchStatus.UNKNOWN),
        ]
        result = SchoolMatchResult(school=School(name="T", slug="t", url=""), checks=checks)
        assert result.is_full_match is True
        assert result.confirmed_count == 1
        assert result.unknown_count == 1

    def test_not_full_match_with_not_matching(self):
        checks = [
            CriterionCheck(criterion="Location", status=MatchStatus.CONFIRMED),
            CriterionCheck(criterion="Level", status=MatchStatus.NOT_MATCHING),
        ]
        result = SchoolMatchResult(school=School(name="T", slug="t", url=""), checks=checks)
        assert result.is_full_match is False
        assert result.confirmed_count == 1
        assert result.unknown_count == 0

    def test_empty_checks_is_full_match(self):
        result = SchoolMatchResult(school=School(name="T", slug="t", url=""), checks=[])
        assert result.is_full_match is True
        assert result.confirmed_count == 0
        assert result.unknown_count == 0


class TestSearchResponse:
    def test_default_response(self):
        r = SearchResponse(
            status=InterpretationStatus.OK,
            criteria=SearchCriteria(),
        )
        assert r.status == InterpretationStatus.OK
        assert r.schools == []
        assert r.total_found_on_page == 0
        assert r.error is None
        assert r.notes == []

    def test_response_with_error(self):
        r = SearchResponse(
            status=InterpretationStatus.OK,
            criteria=SearchCriteria(),
            error="Site is down",
        )
        assert r.error == "Site is down"
