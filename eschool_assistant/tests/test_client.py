"""Tests for the client (URL builder + fetcher)."""
import httpx
import pytest
import respx

from eschool_assistant.client import (
    SearchError,
    SearchHTTPError,
    SearchTimeoutError,
    build_url,
    fetch,
)
from eschool_assistant.models import SearchCriteria

BASE = "https://eschool.ug"
SEARCH_URL = f"{BASE}/find-schools/search"


class TestBuildUrl:
    def test_empty_criteria(self):
        url = build_url(SearchCriteria(), base_url=BASE)
        assert url.startswith(SEARCH_URL)

    def test_location(self):
        url = build_url(SearchCriteria(location="KAMPALA"), base_url=BASE)
        assert "location=KAMPALA" in url

    def test_county(self):
        url = build_url(
            SearchCriteria(location="KAMPALA", county="KAMPALA CENTRAL DIVISION"),
            base_url=BASE,
        )
        assert "county=KAMPALA" in url  # URL-encoded

    def test_gender(self):
        url = build_url(SearchCriteria(gender="girls"), base_url=BASE)
        assert "gender=girls" in url

    def test_min_max_fees(self):
        url = build_url(SearchCriteria(min_fees=100000, max_fees=500000), base_url=BASE)
        assert "min_fees=100000" in url
        assert "max_fees=500000" in url

    def test_accommodation_uses_site_spelling(self):
        """The site parameter is 'accomadation' (sic), not 'accommodation'."""
        url = build_url(SearchCriteria(accommodation="Boarding"), base_url=BASE)
        assert "accomadation=Boarding" in url
        assert "accommodation" not in url.lower()

    def test_levels_multiple(self):
        url = build_url(
            SearchCriteria(levels=["Primary", "Secondary"]), base_url=BASE
        )
        # URL-encoded levels[] → levels%5B%5D
        assert "levels" in url
        assert "Primary" in url
        assert "Secondary" in url

    def test_admission_status(self):
        url = build_url(SearchCriteria(admission_status="open"), base_url=BASE)
        assert "admission_status=open" in url

    def test_sorting(self):
        url = build_url(SearchCriteria(sorting="FeesLow"), base_url=BASE)
        assert "sorting=FeesLow" in url

    def test_query(self):
        url = build_url(SearchCriteria(query="Greenhill"), base_url=BASE)
        assert "q=Greenhill" in url

    def test_page_parameter(self):
        url = build_url(SearchCriteria(location="KAMPALA"), base_url=BASE, page=3)
        assert "page=3" in url

    def test_no_page_when_first(self):
        url = build_url(SearchCriteria(location="KAMPALA"), base_url=BASE, page=1)
        assert "page=" not in url

    def test_curriculums(self):
        url = build_url(SearchCriteria(curriculums=["UNEB", "Cambridge"]), base_url=BASE)
        assert "UNEB" in url
        assert "Cambridge" in url

    def test_facilities(self):
        url = build_url(SearchCriteria(facilities=["Library"]), base_url=BASE)
        assert "Library" in url

    def test_religions(self):
        url = build_url(SearchCriteria(religions=["Catholic Founded"]), base_url=BASE)
        assert "Catholic+Founded" in url or "Catholic%20Founded" in url


class TestFetch:
    @respx.mock
    def test_successful_fetch(self):
        respx.get(SEARCH_URL).mock(
            return_value=httpx.Response(200, text="<html>ok</html>")
        )
        html = fetch(f"{SEARCH_URL}?location=KAMPALA")
        assert html == "<html>ok</html>"

    @respx.mock
    def test_http_500_raises_search_http_error(self):
        respx.get(SEARCH_URL).mock(
            return_value=httpx.Response(500, text="Server Error")
        )
        with pytest.raises(SearchHTTPError):
            fetch(f"{SEARCH_URL}?location=KAMPALA")

    @respx.mock
    def test_http_404_raises_search_http_error(self):
        respx.get(SEARCH_URL).mock(
            return_value=httpx.Response(404, text="Not Found")
        )
        with pytest.raises(SearchHTTPError):
            fetch(f"{SEARCH_URL}?location=KAMPALA")

    @respx.mock
    def test_timeout_raises_search_timeout_error(self):
        respx.get(SEARCH_URL).mock(side_effect=httpx.TimeoutException("timed out"))
        with pytest.raises(SearchTimeoutError):
            fetch(f"{SEARCH_URL}?location=KAMPALA", timeout=1)

    @respx.mock
    def test_connection_error_raises_search_error(self):
        respx.get(SEARCH_URL).mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(SearchError, match="connect"):
            fetch(f"{SEARCH_URL}?location=KAMPALA")

    @respx.mock
    def test_5xx_retried_then_succeeds(self):
        # First call returns 500, second returns 200
        route = respx.get(SEARCH_URL).mock(
            side_effect=[
                httpx.Response(500, text="Error"),
                httpx.Response(200, text="<html>ok</html>"),
            ]
        )
        html = fetch(f"{SEARCH_URL}?location=KAMPALA")
        assert html == "<html>ok</html>"
        assert route.call_count == 2
