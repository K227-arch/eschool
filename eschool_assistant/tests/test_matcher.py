"""Tests for the deterministic matcher."""
from eschool_assistant.matcher import match_school
from eschool_assistant.models import MatchStatus, School, SearchCriteria


def make_school(**kwargs) -> School:
    defaults = {
        "name": "Test School",
        "slug": "test-school",
        "url": "https://eschool.ug/find-schools?slug=test-school",
    }
    defaults.update(kwargs)
    return School(**defaults)


class TestLocationMatching:
    def test_matching_location_confirmed(self):
        school = make_school(location="Kampala")
        criteria = SearchCriteria(location="KAMPALA")
        checks = match_school(school, criteria)
        loc = [c for c in checks if "Location" in c.criterion][0]
        assert loc.status == MatchStatus.CONFIRMED

    def test_non_matching_location_not_matching(self):
        school = make_school(location="Wakiso")
        criteria = SearchCriteria(location="KAMPALA")
        checks = match_school(school, criteria)
        loc = [c for c in checks if "Location" in c.criterion][0]
        assert loc.status == MatchStatus.NOT_MATCHING
        assert "Wakiso" in loc.detail

    def test_missing_location_unknown(self):
        school = make_school(location=None)
        criteria = SearchCriteria(location="KAMPALA")
        checks = match_school(school, criteria)
        loc = [c for c in checks if "Location" in c.criterion][0]
        assert loc.status == MatchStatus.UNKNOWN

    def test_case_insensitive_location(self):
        school = make_school(location="KAMPALA")
        criteria = SearchCriteria(location="kampala")
        checks = match_school(school, criteria)
        loc = [c for c in checks if "Location" in c.criterion][0]
        assert loc.status == MatchStatus.CONFIRMED


class TestLevelMatching:
    def test_matching_level_confirmed(self):
        school = make_school(level="Secondary")
        criteria = SearchCriteria(levels=["Secondary"])
        checks = match_school(school, criteria)
        lvl = [c for c in checks if "level" in c.criterion.lower()][0]
        assert lvl.status == MatchStatus.CONFIRMED

    def test_non_matching_level_not_matching(self):
        school = make_school(level="Secondary")
        criteria = SearchCriteria(levels=["Primary"])
        checks = match_school(school, criteria)
        lvl = [c for c in checks if "level" in c.criterion.lower()][0]
        assert lvl.status == MatchStatus.NOT_MATCHING

    def test_multiple_levels_one_matches(self):
        school = make_school(level="Primary")
        criteria = SearchCriteria(levels=["Secondary", "Primary"])
        checks = match_school(school, criteria)
        lvl = [c for c in checks if "level" in c.criterion.lower()][0]
        assert lvl.status == MatchStatus.CONFIRMED

    def test_missing_level_unknown(self):
        school = make_school(level=None)
        criteria = SearchCriteria(levels=["Secondary"])
        checks = match_school(school, criteria)
        lvl = [c for c in checks if "level" in c.criterion.lower()][0]
        assert lvl.status == MatchStatus.UNKNOWN


class TestAdmissionStatusMatching:
    def test_closed_matches_closed(self):
        school = make_school(admission_status="Admissions Closed")
        criteria = SearchCriteria(admission_status="closed")
        checks = match_school(school, criteria)
        adm = [c for c in checks if "Admission" in c.criterion][0]
        assert adm.status == MatchStatus.CONFIRMED

    def test_open_matches_open(self):
        school = make_school(admission_status="Open for 2026")
        criteria = SearchCriteria(admission_status="open")
        checks = match_school(school, criteria)
        adm = [c for c in checks if "Admission" in c.criterion][0]
        assert adm.status == MatchStatus.CONFIRMED

    def test_closed_does_not_match_open(self):
        school = make_school(admission_status="Admissions Closed")
        criteria = SearchCriteria(admission_status="open")
        checks = match_school(school, criteria)
        adm = [c for c in checks if "Admission" in c.criterion][0]
        assert adm.status == MatchStatus.NOT_MATCHING

    def test_missing_admission_status_unknown(self):
        school = make_school(admission_status=None)
        criteria = SearchCriteria(admission_status="open")
        checks = match_school(school, criteria)
        adm = [c for c in checks if "Admission" in c.criterion][0]
        assert adm.status == MatchStatus.UNKNOWN


class TestFeesAreUnknown:
    """Fees are never shown on the card — always UNKNOWN."""

    def test_max_fees_unknown(self):
        school = make_school()
        criteria = SearchCriteria(max_fees=1000000)
        checks = match_school(school, criteria)
        fee = [c for c in checks if "Max fees" in c.criterion][0]
        assert fee.status == MatchStatus.UNKNOWN

    def test_min_fees_unknown(self):
        school = make_school()
        criteria = SearchCriteria(min_fees=500000)
        checks = match_school(school, criteria)
        fee = [c for c in checks if "Min fees" in c.criterion][0]
        assert fee.status == MatchStatus.UNKNOWN


class TestGenderIsUnknown:
    def test_gender_unknown(self):
        school = make_school()
        criteria = SearchCriteria(gender="girls")
        checks = match_school(school, criteria)
        gen = [c for c in checks if "Gender" in c.criterion][0]
        assert gen.status == MatchStatus.UNKNOWN


class TestAccommodationIsUnknown:
    def test_accommodation_unknown(self):
        school = make_school()
        criteria = SearchCriteria(accommodation="Boarding")
        checks = match_school(school, criteria)
        acc = [c for c in checks if "Accommodation" in c.criterion][0]
        assert acc.status == MatchStatus.UNKNOWN


class TestCountyIsUnknown:
    def test_county_unknown(self):
        school = make_school()
        criteria = SearchCriteria(county="KAMPALA CENTRAL DIVISION")
        checks = match_school(school, criteria)
        cty = [c for c in checks if "Division" in c.criterion][0]
        assert cty.status == MatchStatus.UNKNOWN


class TestQueryMatching:
    def test_query_in_name_confirmed(self):
        school = make_school(name="Greenhill Academy")
        criteria = SearchCriteria(query="Greenhill")
        checks = match_school(school, criteria)
        q = [c for c in checks if "Name search" in c.criterion][0]
        assert q.status == MatchStatus.CONFIRMED

    def test_query_not_in_name_unknown(self):
        school = make_school(name="Other School")
        criteria = SearchCriteria(query="Greenhill")
        checks = match_school(school, criteria)
        q = [c for c in checks if "Name search" in c.criterion][0]
        assert q.status == MatchStatus.UNKNOWN

    def test_query_case_insensitive(self):
        school = make_school(name="Greenhill Academy")
        criteria = SearchCriteria(query="greenhill")
        checks = match_school(school, criteria)
        q = [c for c in checks if "Name search" in c.criterion][0]
        assert q.status == MatchStatus.CONFIRMED


class TestNoCriteria:
    def test_empty_criteria_produces_no_checks(self):
        school = make_school()
        criteria = SearchCriteria()
        checks = match_school(school, criteria)
        assert checks == []

    def test_only_unsupported_criteria_no_checks(self):
        school = make_school()
        criteria = SearchCriteria(unsupported_criteria=["something"])
        checks = match_school(school, criteria)
        assert checks == []


class TestMultipleCriteria:
    def test_all_criteria_checked(self):
        school = make_school(
            location="Kampala", level="Secondary", admission_status="Admissions Closed"
        )
        criteria = SearchCriteria(
            location="KAMPALA",
            levels=["Secondary"],
            max_fees=1000000,
            gender="girls",
            accommodation="Boarding",
            admission_status="closed",
        )
        checks = match_school(school, criteria)
        assert len(checks) == 6  # location, level, max_fees, gender, accommodation, admission

    def test_mix_of_statuses(self):
        school = make_school(location="Wakiso", level="Secondary")
        criteria = SearchCriteria(
            location="KAMPALA",
            levels=["Secondary"],
            max_fees=1000000,
        )
        checks = match_school(school, criteria)
        statuses = [c.status for c in checks]
        assert MatchStatus.NOT_MATCHING in statuses  # location
        assert MatchStatus.CONFIRMED in statuses  # level
        assert MatchStatus.UNKNOWN in statuses  # fees
