"""Tests for the validator."""
import pytest

from eschool_assistant.models import SearchCriteria
from eschool_assistant.validator import validate


class TestLocationValidation:
    def test_location_uppercased(self):
        sc = SearchCriteria(location="kampala")
        result = validate(sc)
        assert result.criteria.location == "KAMPALA"
        assert result.warnings == []

    def test_valid_location_preserved(self):
        sc = SearchCriteria(location="WAKISO")
        result = validate(sc)
        assert result.criteria.location == "WAKISO"

    def test_invalid_location_removed(self):
        sc = SearchCriteria(location="Nairobi")
        result = validate(sc)
        assert result.criteria.location is None
        assert any("Nairobi" in w for w in result.warnings)

    def test_location_with_spaces_trimmed(self):
        sc = SearchCriteria(location="  KAMPALA  ")
        result = validate(sc)
        assert result.criteria.location == "KAMPALA"

    def test_no_location_stays_none(self):
        sc = SearchCriteria()
        result = validate(sc)
        assert result.criteria.location is None


class TestCountyValidation:
    def test_valid_county_for_kampala(self):
        sc = SearchCriteria(location="KAMPALA", county="KAMPALA CENTRAL DIVISION")
        result = validate(sc)
        assert result.criteria.county == "KAMPALA CENTRAL DIVISION"
        assert result.warnings == []

    def test_county_uppercased(self):
        sc = SearchCriteria(location="KAMPALA", county="kampala central division")
        result = validate(sc)
        assert result.criteria.county == "KAMPALA CENTRAL DIVISION"

    def test_fuzzy_county_match(self):
        sc = SearchCriteria(location="KAMPALA", county="central")
        result = validate(sc)
        assert result.criteria.county == "KAMPALA CENTRAL DIVISION"

    def test_invalid_county_removed(self):
        sc = SearchCriteria(location="KAMPALA", county="NONEXISTENT DIVISION")
        result = validate(sc)
        assert result.criteria.county is None
        assert any("NONEXISTENT" in w for w in result.warnings)

    def test_county_without_location_passthrough(self):
        sc = SearchCriteria(county="SOME DIVISION")
        result = validate(sc)
        assert result.criteria.county == "SOME DIVISION"

    def test_county_for_unknown_location_passthrough(self):
        sc = SearchCriteria(county="SOME COUNTY")
        result = validate(sc)
        assert result.criteria.county == "SOME COUNTY"


class TestFeesValidation:
    def test_valid_fees_preserved(self):
        sc = SearchCriteria(min_fees=500000, max_fees=1000000)
        result = validate(sc)
        assert result.criteria.min_fees == 500000
        assert result.criteria.max_fees == 1000000

    def test_negative_min_fees_removed(self):
        sc = SearchCriteria(min_fees=-100)
        result = validate(sc)
        assert result.criteria.min_fees is None
        assert any("negative" in w.lower() for w in result.warnings)

    def test_negative_max_fees_removed(self):
        sc = SearchCriteria(max_fees=-100)
        result = validate(sc)
        assert result.criteria.max_fees is None
        assert any("negative" in w.lower() for w in result.warnings)

    def test_min_greater_than_max_swapped(self):
        sc = SearchCriteria(min_fees=5000000, max_fees=100000)
        result = validate(sc)
        assert result.criteria.min_fees == 100000
        assert result.criteria.max_fees == 5000000
        assert any("swapped" in w.lower() for w in result.warnings)

    def test_only_min_fees(self):
        sc = SearchCriteria(min_fees=200000)
        result = validate(sc)
        assert result.criteria.min_fees == 200000
        assert result.criteria.max_fees is None


class TestGenderValidation:
    def test_valid_gender_preserved(self):
        sc = SearchCriteria(gender="girls")
        result = validate(sc)
        assert result.criteria.gender == "girls"

    def test_alias_girls_school(self):
        sc = SearchCriteria(gender="girls school")
        result = validate(sc)
        assert result.criteria.gender == "girls"

    def test_alias_boys_only(self):
        sc = SearchCriteria(gender="boys only")
        result = validate(sc)
        assert result.criteria.gender == "boys"

    def test_alias_co_ed(self):
        sc = SearchCriteria(gender="co-ed")
        result = validate(sc)
        assert result.criteria.gender == "mixed"

    def test_invalid_gender_removed(self):
        sc = SearchCriteria(gender="purple")
        result = validate(sc)
        assert result.criteria.gender is None
        assert any("gender" in w.lower() for w in result.warnings)


class TestAccommodationValidation:
    def test_valid_boarding_preserved(self):
        sc = SearchCriteria(accommodation="Boarding")
        result = validate(sc)
        assert result.criteria.accommodation == "Boarding"

    def test_alias_boarding_school(self):
        sc = SearchCriteria(accommodation="boarding school")
        result = validate(sc)
        assert result.criteria.accommodation == "Boarding"

    def test_alias_day_only(self):
        sc = SearchCriteria(accommodation="day only")
        result = validate(sc)
        assert result.criteria.accommodation == "Day"

    def test_invalid_accommodation_removed(self):
        sc = SearchCriteria(accommodation="sleepover")
        result = validate(sc)
        assert result.criteria.accommodation is None


class TestAdmissionStatusValidation:
    def test_valid_open(self):
        sc = SearchCriteria(admission_status="open")
        result = validate(sc)
        assert result.criteria.admission_status == "open"

    def test_alias_admitting(self):
        sc = SearchCriteria(admission_status="admitting")
        result = validate(sc)
        assert result.criteria.admission_status == "open"

    def test_alias_admissions_closed(self):
        sc = SearchCriteria(admission_status="admissions closed")
        result = validate(sc)
        assert result.criteria.admission_status == "closed"

    def test_invalid_removed(self):
        sc = SearchCriteria(admission_status="maybe")
        result = validate(sc)
        assert result.criteria.admission_status is None


class TestLevelsValidation:
    def test_valid_level_preserved(self):
        sc = SearchCriteria(levels=["Secondary"])
        result = validate(sc)
        assert result.criteria.levels == ["Secondary"]

    def test_level_case_insensitive(self):
        sc = SearchCriteria(levels=["secondary"])
        result = validate(sc)
        assert result.criteria.levels == ["Secondary"]

    def test_invalid_level_removed(self):
        sc = SearchCriteria(levels=["Secondary", "University"])
        result = validate(sc)
        assert result.criteria.levels == ["Secondary"]
        assert any("University" in w for w in result.warnings)

    def test_multiple_valid_levels(self):
        sc = SearchCriteria(levels=["Primary", "Secondary"])
        result = validate(sc)
        assert set(result.criteria.levels) == {"Primary", "Secondary"}

    def test_duplicate_levels_deduplicated(self):
        sc = SearchCriteria(levels=["Secondary", "Secondary"])
        result = validate(sc)
        assert result.criteria.levels == ["Secondary"]


class TestSortingValidation:
    def test_valid_sorting(self):
        sc = SearchCriteria(sorting="FeesLow")
        result = validate(sc)
        assert result.criteria.sorting == "FeesLow"

    def test_case_insensitive(self):
        sc = SearchCriteria(sorting="feeslow")
        result = validate(sc)
        assert result.criteria.sorting == "FeesLow"

    def test_invalid_sorting_removed(self):
        sc = SearchCriteria(sorting="cheapest")
        result = validate(sc)
        assert result.criteria.sorting is None
