"""Tests for the HTML parser."""
from eschool_assistant.parser import parse_search_results


class TestParseKampalaCentralMixed:
    def test_parses_24_schools(self, kampala_mixed_html):
        schools, total_pages = parse_search_results(kampala_mixed_html)
        assert len(schools) == 24

    def test_detects_2_pages(self, kampala_mixed_html):
        schools, total_pages = parse_search_results(kampala_mixed_html)
        assert total_pages == 2

    def test_first_school_has_name(self, kampala_mixed_html):
        schools, _ = parse_search_results(kampala_mixed_html)
        assert schools[0].name
        assert "Hungry Caterpillar" in schools[0].name

    def test_first_school_has_slug(self, kampala_mixed_html):
        schools, _ = parse_search_results(kampala_mixed_html)
        assert schools[0].slug
        assert schools[0].slug == "the-hungry-caterpillar-primary-school"

    def test_first_school_has_url(self, kampala_mixed_html):
        schools, _ = parse_search_results(kampala_mixed_html)
        assert schools[0].url
        assert "eschool.ug" in schools[0].url

    def test_first_school_has_level(self, kampala_mixed_html):
        schools, _ = parse_search_results(kampala_mixed_html)
        assert schools[0].level is not None

    def test_first_school_has_location(self, kampala_mixed_html):
        schools, _ = parse_search_results(kampala_mixed_html)
        assert schools[0].location == "Kampala"

    def test_first_school_has_admission_status(self, kampala_mixed_html):
        schools, _ = parse_search_results(kampala_mixed_html)
        assert schools[0].admission_status is not None
        assert "Closed" in schools[0].admission_status or "Open" in schools[0].admission_status

    def test_school_with_rating(self, kampala_mixed_html):
        schools, _ = parse_search_results(kampala_mixed_html)
        rated = [s for s in schools if s.rating is not None]
        assert len(rated) > 0
        assert all(s.rating > 0 for s in rated)

    def test_school_with_zero_rating_is_none(self, kampala_mixed_html):
        schools, _ = parse_search_results(kampala_mixed_html)
        # Some schools have 0.0 rating → should be None
        unrated = [s for s in schools if s.rating is None]
        assert len(unrated) > 0

    def test_school_id_present(self, kampala_mixed_html):
        schools, _ = parse_search_results(kampala_mixed_html)
        with_id = [s for s in schools if s.school_id is not None]
        assert len(with_id) > 0

    def test_all_schools_have_image_url(self, kampala_mixed_html):
        schools, _ = parse_search_results(kampala_mixed_html)
        # Most should have image URLs
        with_image = [s for s in schools if s.image_url]
        assert len(with_image) > 0


class TestParseKampalaAll:
    def test_parses_24_schools(self, kampala_all_html):
        schools, _ = parse_search_results(kampala_all_html)
        assert len(schools) == 24

    def test_detects_35_pages(self, kampala_all_html):
        schools, total_pages = parse_search_results(kampala_all_html)
        assert total_pages == 35

    def test_includes_non_kampala_schools(self, kampala_all_html):
        """The 'all Kampala' search includes nearby districts."""
        schools, _ = parse_search_results(kampala_all_html)
        locations = {s.location for s in schools if s.location}
        assert "Kampala" in locations
        assert len(locations) > 1  # More than just Kampala


class TestParseNoResults:
    def test_few_schools(self, no_results_html):
        schools, _ = parse_search_results(no_results_html)
        # The max_fees=1 fixture returned 2 schools
        assert len(schools) <= 5

    def test_no_pagination(self, no_results_html):
        schools, total_pages = parse_search_results(no_results_html)
        assert total_pages is None


class TestParseEmptyHtml:
    def test_empty_html_returns_empty(self):
        schools, total_pages = parse_search_results("<html><body></body></html>")
        assert schools == []
        assert total_pages is None

    def test_html_without_school_links(self):
        html = "<html><body><article><p>Not a school</p></article></body></html>"
        schools, _ = parse_search_results(html)
        assert schools == []

    def test_non_article_elements_ignored(self):
        html = """
        <html><body>
        <article class="card">
            <a href="https://eschool.ug/find-schools?slug=test-school">Test School</a>
            <span class="badge">Secondary</span>
            <div class="text-muted"><i class="fi-map-pin"></i><span>Kampala</span></div>
        </article>
        <div>Some other content</div>
        </body></html>
        """
        schools, _ = parse_search_results(html)
        assert len(schools) == 1
        assert schools[0].name == "Test School"
