"""Client — builds the eSchool search URL from criteria and fetches the page.

This module contains **no AI logic** — it is pure deterministic code that:

1.  Converts a ``SearchCriteria`` into the query string the eSchool search
    endpoint expects (``build_url``).
2.  Fetches the HTML with ``httpx``, applying a timeout and simple retries
    (``fetch``).
3.  Raises clear, typed errors so the presenter can give the parent a friendly
    message instead of a stack trace.

Note on the ``accomadation`` parameter: the eSchool search form spells it
this way (sic).  We keep that spelling for the URL but expose the clean name
``accommodation`` in the models.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlencode

import httpx

from .config import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, RESULTS_PER_PAGE
from .models import SearchCriteria

logger = logging.getLogger(__name__)

# How many times to retry on transient errors
_MAX_RETRIES = 2
_RETRY_DELAY = 1.0  # seconds


# ── Error types ────────────────────────────────────────────────────────────
class SearchError(Exception):
    """Base error for all search-fetch failures."""


class SearchTimeoutError(SearchError):
    """The eSchool server did not respond in time."""


class SearchHTTPError(SearchError):
    """The eSchool server returned an error status code."""


# ── URL builder ───────────────────────────────────────────────────────────
def build_url(
    criteria: SearchCriteria,
    base_url: str = DEFAULT_BASE_URL,
    page: int = 1,
) -> str:
    """Build the eSchool search URL from ``SearchCriteria``.

    Only non-null / non-empty criteria are included in the query string.
    """
    params: list[tuple[str, str]] = []

    if criteria.query:
        params.append(("q", criteria.query))

    if criteria.location:
        params.append(("location", criteria.location))

    if criteria.county:
        params.append(("county", criteria.county))

    if criteria.min_fees is not None:
        params.append(("min_fees", str(criteria.min_fees)))

    if criteria.max_fees is not None:
        params.append(("max_fees", str(criteria.max_fees)))

    if criteria.gender:
        params.append(("gender", criteria.gender))

    if criteria.admission_status:
        params.append(("admission_status", criteria.admission_status))

    # Note: the site spells this parameter "accomadation" (sic).
    if criteria.accommodation:
        params.append(("accomadation", criteria.accommodation))

    if criteria.sorting:
        params.append(("sorting", criteria.sorting))

    # Multi-value params — each value becomes a separate entry
    for level in criteria.levels:
        params.append(("levels[]", level))

    for curriculum in criteria.curriculums:
        params.append(("curriculums[]", curriculum))

    for facility in criteria.facilities:
        params.append(("facilities[]", facility))

    for religion in criteria.religions:
        params.append(("religions[]", religion))

    if page > 1:
        params.append(("page", str(page)))

    query_string = urlencode(params)
    return f"{base_url.rstrip('/')}/find-schools/search?{query_string}"


# ── Fetcher ───────────────────────────────────────────────────────────────
def fetch(
    url: str,
    client: httpx.Client | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Fetch a URL and return the response body as text.

    Retries up to ``_MAX_RETRIES`` times on connection errors and 5xx
    responses.  Raises a typed :class:`SearchError` subclass on failure.

    Parameters
    ----------
    url : str
        The full search URL to fetch.
    client : httpx.Client, optional
        Injected for testing.  A new client is created when ``None``.
    timeout : int
        Per-request timeout in seconds.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-UG,en;q=0.9",
    }

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=timeout, follow_redirects=True)

    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 2):  # initial + retries
        try:
            logger.debug("Fetching %s (attempt %d)", url, attempt)
            response = client.get(url, headers=headers)

            if response.status_code == 200:
                return response.text

            if 500 <= response.status_code < 600 and attempt <= _MAX_RETRIES:
                logger.warning(
                    "Server returned %d, retrying (%d/%d)",
                    response.status_code, attempt, _MAX_RETRIES,
                )
                last_error = SearchHTTPError(
                    f"eSchool returned HTTP {response.status_code}"
                )
                time.sleep(_RETRY_DELAY)
                continue

            # Non-retryable HTTP error
            raise SearchHTTPError(
                f"eSchool returned HTTP {response.status_code}: "
                f"{response.reason_phrase}"
            )

        except httpx.TimeoutException as exc:
            last_error = SearchTimeoutError(
                f"The eSchool server did not respond within {timeout} seconds."
            )
            if attempt <= _MAX_RETRIES:
                logger.warning("Timeout, retrying (%d/%d)", attempt, _MAX_RETRIES)
                time.sleep(_RETRY_DELAY)
                continue
            raise last_error from exc

        except httpx.ConnectError as exc:
            last_error = SearchError(
                "Could not connect to eSchool. The site may be down."
            )
            if attempt <= _MAX_RETRIES:
                logger.warning("Connection error, retrying (%d/%d)", attempt, _MAX_RETRIES)
                time.sleep(_RETRY_DELAY)
                continue
            raise last_error from exc

    # Exhausted retries
    if last_error:
        raise last_error
    raise SearchError("An unexpected error occurred while fetching results.")


# ── High-level convenience ─────────────────────────────────────────────────
def search(
    criteria: SearchCriteria,
    base_url: str = DEFAULT_BASE_URL,
    max_pages: int = 1,
    client: httpx.Client | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[tuple[str, int | None]]:
    """Fetch one or more pages of search results.

    Returns a list of ``(html, total_pages)`` tuples — one per page fetched.
    The caller (usually the pipeline) parses each HTML with the parser.
    """
    results: list[tuple[str, int | None]] = []
    for page in range(1, max_pages + 1):
        url = build_url(criteria, base_url, page=page)
        html = fetch(url, client=client, timeout=timeout)
        results.append((html, None))  # total_pages filled by parser
        if page < max_pages:
            # Brief courtesy delay between page fetches
            time.sleep(0.5)
    return results
