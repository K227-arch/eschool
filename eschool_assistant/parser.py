"""Parser — converts eSchool search-result HTML into ``School`` objects.

The search page is server-rendered HTML (no JSON endpoint).  Each school is
an ``<article class="card …">`` element containing a link to
``/find-schools?slug=<school-slug>``.  This module extracts every such card
and pulls out the fields that are visible on the results page.

Card fields available
---------------------
* name            — from the ``<h3>`` heading inside the card body
* slug            — from the ``href`` of the school link
* url             — full detail-page URL
* school_id       — from ``data-school-id`` on the waitlist button
* level           — from the level badge (e.g. "Secondary", "Primary")
* rating          — from the rating span (e.g. "4.3")
* location        — from the map-pin location span (district name)
* admission_status— from the status badge ("Admissions Closed", "Open for 2026" …)
* image_url       — from the ``<img>`` src

Pagination info is extracted from the ``page=N`` links.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from .models import School

logger = logging.getLogger(__name__)

# Regex for extracting page numbers from pagination links
_PAGE_RE = re.compile(r"[?&]page=(\d+)")
# Regex for the school slug in detail-page URLs
_SLUG_RE = re.compile(r"find-schools\?slug=([^&\"']+)")


def parse_search_results(html: str) -> tuple[list[School], int | None]:
    """Parse eSchool search-result HTML.

    Parameters
    ----------
    html : str
        Raw HTML from a GET request to the search page.

    Returns
    -------
    tuple[list[School], int | None]
        A list of parsed schools and the total number of pages (``None`` when
        pagination info is not found, meaning there's only one page).
    """
    soup = BeautifulSoup(html, "html.parser")

    schools = []
    for article in soup.find_all("article"):
        school = _parse_card(article)
        if school is not None:
            schools.append(school)

    total_pages = _extract_total_pages(soup)

    logger.debug("Parsed %d schools, total_pages=%s", len(schools), total_pages)
    return schools, total_pages


def _parse_card(article) -> Optional[School]:
    """Parse a single ``<article>`` element into a ``School``.

    Returns ``None`` when the article is not a school-result card (the page
    contains other articles for ads, newsletters, etc.).
    """
    # Must have a link to a school detail page
    link = article.find("a", href=_SLUG_RE)
    if link is None:
        return None

    href = link.get("href", "")
    slug_match = _SLUG_RE.search(href)
    if not slug_match:
        return None
    slug = slug_match.group(1)

    # Name — try the <h3> link first, then the image alt
    name = _extract_name(article, link)

    # School ID — from the data-school-id button
    school_id = None
    id_btn = article.find(attrs={"data-school-id": True})
    if id_btn:
        school_id = id_btn.get("data-school-id")

    # Level — from the badge in the card body
    level = _extract_level(article)

    # Rating — from the rating span
    rating = _extract_rating(article)

    # Location — from the map-pin span
    location = _extract_location(article)

    # Admission status — from the status badge
    admission_status = _extract_admission_status(article)

    # Image URL
    img = article.find("img")
    image_url = img.get("src") if img else None

    # Build the full URL (the href may be relative or absolute)
    url = href if href.startswith("http") else f"https://eschool.ug/{href.lstrip('/')}"

    return School(
        name=name.strip() if name else slug.replace("-", " ").title(),
        slug=slug,
        url=url,
        school_id=school_id,
        level=level,
        rating=rating,
        location=location,
        admission_status=admission_status,
        image_url=image_url,
    )


def _extract_name(article, link) -> str:
    """Extract the school name, preferring the <h3> text."""
    h3 = article.find("h3")
    if h3:
        text = h3.get_text(strip=True)
        if text:
            return text
    # Fall back to the link text
    text = link.get_text(strip=True)
    if text:
        return text
    # Fall back to image alt
    img = article.find("img")
    if img and img.get("alt"):
        return img["alt"].strip()
    return ""


def _extract_level(article) -> Optional[str]:
    """Extract the school level from a badge in the card body."""
    body = article.find("div", class_="card-body")
    if not body:
        body = article
    # The level badge is a <span class="badge"> that is NOT a status badge
    for badge in body.find_all("span", class_="badge"):
        text = badge.get_text(strip=True)
        # Skip status badges (handled separately) and rating badges
        if not text:
            continue
        lower = text.lower()
        if any(kw in lower for kw in ("admission", "open", "closed", "waitlist")):
            continue
        # Known levels
        known_levels = [
            "Nursery & Kindergaten",
            "Nursery & Primary",
            "Primary",
            "Secondary",
            "International",
        ]
        for kl in known_levels:
            if text == kl or text.lower() == kl.lower():
                return kl
        # If it looks like a level (short, no special chars), return it
        if len(text) < 30 and not any(c.isdigit() for c in text):
            return text
    return None


def _extract_rating(article) -> Optional[float]:
    """Extract the numeric rating (e.g. 4.3) or None when 0.0/unavailable."""
    # Rating is in a div with text-warning class
    for div in article.find_all("div", class_=re.compile(r"text-warning")):
        text = div.get_text(strip=True)
        # The rating is the leading number before the star icon
        match = re.match(r"^([\d.]+)", text)
        if match:
            val = float(match.group(1))
            # 0.0 means no ratings — treat as None
            if val > 0:
                return val
            return None
    return None


def _extract_location(article) -> Optional[str]:
    """Extract the location (district) from the map-pin span."""
    # Look for the location div with fi-map-pin icon
    for div in article.find_all("div", class_=re.compile(r"text-muted")):
        # Check for the map-pin icon
        if div.find("i", class_=re.compile(r"map-pin")):
            span = div.find("span")
            if span:
                text = span.get_text(strip=True)
                if text:
                    return text
            # Fallback: use the div's own text
            text = div.get_text(strip=True)
            if text:
                return text
    return None


def _extract_admission_status(article) -> Optional[str]:
    """Extract the admission status from the status badge.

    Returns the raw badge text (e.g. "Admissions Closed", "Open for 2026")
    so the matcher can interpret it.
    """
    # Status badges are in the image overlay, typically with text-danger or
    # text-success class
    for badge in article.find_all("span", class_=re.compile(r"badge")):
        text = badge.get_text(strip=True)
        if not text:
            continue
        lower = text.lower()
        if "admission" in lower or "open" in lower and "2026" in lower or "closed" in lower:
            return text
        if "open for" in lower:
            return text
    return None


def _extract_total_pages(soup) -> int | None:
    """Extract the total number of pages from pagination links.

    Pagination links look like ``?location=KAMPALA&page=35``.
    The highest page number found is the total.
    """
    max_page = None
    for a in soup.find_all("a", href=True):
        match = _PAGE_RE.search(a["href"])
        if match:
            page_num = int(match.group(1))
            if max_page is None or page_num > max_page:
                max_page = page_num
    return max_page


# ── Detail-page parser ────────────────────────────────────────────────────
# Maps the label text on the detail page to the canonical value we store.
_GENDER_MAP: dict[str, str] = {
    "girls": "girls",
    "girls only": "girls",
    "boys": "boys",
    "boys only": "boys",
    "mixed": "mixed",
    "co-education": "mixed",
    "co-ed": "mixed",
    "both": "mixed",
}

_ACCOMMODATION_MAP: dict[str, str] = {
    "boarding": "Boarding",
    "boarding only": "Boarding",
    "day": "Day",
    "day only": "Day",
    "day school": "Day",
    "day & boarding": "Day & Boarding",
    "day and boarding": "Day & Boarding",
}


def parse_school_detail(html: str) -> dict[str, str | None]:
    """Parse a school detail page and return enrichment fields.

    Returns a dict with keys: ``gender``, ``accommodation``,
    ``curriculum``, ``religion``.  Each value is either a canonical
    string or ``None`` when the field is not found on the page.

    The detail page uses a consistent pattern::

        <span class="... text-muted text-uppercase ...">Gender</span>
        <!-- sibling or parent contains the value, e.g. "girls" -->

    The full text of the parent container is "Gender girls", so we
    strip the label and take the remainder as the value.
    """
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, str | None] = {
        "gender": None,
        "accommodation": None,
        "curriculum": None,
        "religion": None,
    }

    # Find all label spans using eSchool's consistent CSS class pattern
    label_spans = soup.find_all(
        "span",
        class_=re.compile(r"text-muted", re.I),
        string=re.compile(r"^\s*(Gender|Section|Curriculum|Religion)\s*$", re.I),
    )

    for span in label_spans:
        label = span.get_text(strip=True).lower()
        # The value lives in the same parent container as the label
        parent = span.find_parent()
        if not parent:
            continue

        # Full text of the container minus the label itself
        full_text = parent.get_text(" ", strip=True)
        # Remove the label word from the start of the text
        value_raw = re.sub(
            r"^\s*" + re.escape(span.get_text(strip=True)) + r"\s*",
            "",
            full_text,
            flags=re.I,
        ).strip().lower()

        if not value_raw:
            continue

        if label == "gender":
            # Normalise to canonical gender value
            result["gender"] = _GENDER_MAP.get(value_raw)
            if result["gender"] is None:
                # Try partial match (e.g. "girls school" → "girls")
                for key, val in _GENDER_MAP.items():
                    if key in value_raw:
                        result["gender"] = val
                        break

        elif label == "section":
            # "Section" is eSchool's label for boarding/day
            result["accommodation"] = _ACCOMMODATION_MAP.get(value_raw)
            if result["accommodation"] is None:
                for key, val in _ACCOMMODATION_MAP.items():
                    if key in value_raw:
                        result["accommodation"] = val
                        break

        elif label == "curriculum":
            # Take the raw value capitalised (e.g. "UNEB", "Cambridge")
            result["curriculum"] = value_raw.upper() if len(value_raw) <= 12 else value_raw.title()

        elif label == "religion":
            result["religion"] = value_raw.title()

    logger.debug("Detail parse result: %s", result)
    return result
