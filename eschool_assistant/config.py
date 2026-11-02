"""Configuration constants for the eSchool Assistant.

All values here were discovered by inspecting the public search page at
https://eschool.ug/find-schools/search (see Step 0 investigation notes in
DESIGN.md).  Keeping them in one place makes the validator and URL builder
single sources of truth for what the site actually supports.
"""

from __future__ import annotations

import os

# ── eSchool endpoint ──────────────────────────────────────────────────────
DEFAULT_BASE_URL = os.getenv("ESCHOOL_BASE_URL", "https://eschool.ug")
SEARCH_PATH = "/find-schools/search"
DEFAULT_TIMEOUT = int(os.getenv("ESCHOOL_TIMEOUT", "30"))
RESULTS_PER_PAGE = 24  # observed during investigation
DEFAULT_MAX_PAGES = 3  # cap how many pages we fetch per query

# ── AI configuration ──────────────────────────────────────────────────────
# OpenAI defaults
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_BASE_URL_AI = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
DEFAULT_TEMPERATURE = 0.0  # deterministic extraction

# Groq defaults (OpenAI-compatible API)
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# gpt-oss-120b gives best extraction quality among available Groq models;
# allam-2-7b is the fastest fallback.
GROQ_DEFAULT_MODEL = os.getenv("GROQ_MODEL", "allam-2-7b")
GROQ_CONNECT_TIMEOUT = 15
GROQ_READ_TIMEOUT    = 120

# ── Valid dropdown values (mirrors the live search form) ──────────────────

#: Districts shown in the *Location* dropdown, stored uppercase exactly as
#: the site expects them in the query string.
VALID_LOCATIONS: frozenset[str] = frozenset(
    [
        "ADJUMANI", "ALEBTONG", "APAC", "ARUA", "BUDUDA", "BUIKWE",
        "BUKEDEA", "BULIISA", "BUSHENYI", "BUTAMBALA", "GULU", "HOIMA",
        "IBANDA", "IGANGA", "ISINGIRO", "JINJA", "KABALE", "KABAROLE",
        "KAGADI", "KAKUMIRO", "KALIRO", "KALUNGU", "KAMPALA", "KAMULI",
        "KAMWENGE", "KANUNGU", "KASESE", "KAYUNGA", "KIRYANDONGO", "KOLE",
        "KUMI", "KYANKWANZI", "KYEGEGWA", "KYENJOJO", "KYOTERA", "LIRA",
        "LUWEERO", "LWENGO", "MANAFWA", "MASAKA", "MASINDI", "MAYUGE",
        "MBALE", "MBARARA", "MITYANA", "MPIGI", "MUBENDE", "MUKONO",
        "NAKASEKE", "NAKASONGOLA", "NAMAYINGO", "NAMUTUMBA", "NAPAK",
        "NEBBI", "NGORA", "NTUNGAMO", "PADER", "PALLISA", "RUBIRIZI",
        "RUKIGA", "RUKUNGIRI", "SERERE", "SHEEMA", "SOROTI", "TORORO",
        "WAKISO", "YUMBE",
    ]
)

#: Gender radio values.
VALID_GENDERS: frozenset[str] = frozenset({"mixed", "boys", "girls"})

#: Admission-status radio values.
VALID_ADMISSION_STATUSES: frozenset[str] = frozenset({"open", "closed"})

#: School-level checkbox values (note "Kindergaten" spelling from the site).
VALID_LEVELS: frozenset[str] = frozenset(
    [
        "Nursery & Kindergaten",
        "Nursery & Primary",
        "Primary",
        "Secondary",
        "International",
    ]
)

#: Curriculum checkbox values.
VALID_CURRICULUMS: frozenset[str] = frozenset(
    ["UNEB", "Cambridge", "IB", "Montessori", "Islamic", "Other"]
)

#: Facility checkbox values.
VALID_FACILITIES: frozenset[str] = frozenset(
    [
        "Science Labs",
        "Computer Lab",
        "Library",
        "Sports Facilities",
        "Cafeteria",
        "School Transport",
        "School Clinic",
        "Music & Arts",
    ]
)

#: Religion / affiliation checkbox values.
VALID_RELIGIONS: frozenset[str] = frozenset(
    [
        "Catholic Founded",
        "Church of Uganda (Anglican)",
        "Seventh-day Adventist (SDA)",
        "Pentecostal / Born-Again",
        "Islamic / Muslim",
        "Non-Denominational / Secular",
        "Other Affiliation",
    ]
)

#: Accommodation dropdown values.
#: The site parameter is spelled ``accomadation`` (sic) — we keep that spelling
#: for URL building but expose a clean enum to the rest of the code.
VALID_ACCOMMODATIONS: frozenset[str] = frozenset(
    ["Day & Boarding", "Day", "Boarding"]
)

#: Sorting dropdown values.
VALID_SORTING: frozenset[str] = frozenset({"Popular", "FeesLow", "Newest"})

# ── County / division mapping (populated server-side per location) ─────────
# Only the most common locations are pre-built; the validator can fetch the
# rest dynamically from the live page.
COUNTY_MAP: dict[str, list[str]] = {
    "KAMPALA": [
        "KAWEMPE DIVISION SOUTH",
        "KAMPALA CENTRAL DIVISION",
        "KAWEMPE DIVISION NORTH",
        "RUBAGA DIVISION SOUTH",
        "MAKINDYE DIVISION EAST",
        "NAKAWA DIVISION",
        "RUBAGA DIVISION NORTH",
        "MAKINDYE DIVISION WEST",
    ],
    "WAKISO": [
        "BUSIRO COUNTY SOUTH",
        "MAKINDYE-SSABAGABO MUNICIPALITY",
        "BUSIRO COUNTY EAST",
        "NANSANA MUNICIPALITY",
        "KIRA MUNICIPALITY",
        "ENTEBBE MUNICIPALITY",
        "KYADONDO COUNTY EAST",
        "BUSIRO COUNTY NORTH",
    ],
    "MUKONO": [
        "MUKONO MUNICIPALITY",
        "NAKIFUMA COUNTY",
        "MUKONO COUNTY SOUTH",
        "MUKONO COUNTY NORTH",
    ],
}

# ── Friendly aliases for fuzzy matching ────────────────────────────────────
#: Maps common plain-English words the parent might use to the canonical
#: values the site expects.  The validator uses these to normalise AI output.
GENDER_ALIASES: dict[str, str] = {
    "mixed": "mixed",
    "co-education": "mixed",
    "coeducation": "mixed",
    "co-ed": "mixed",
    "co ed": "mixed",
    "both": "mixed",
    "boys": "boys",
    "boys only": "boys",
    "all boys": "boys",
    "boys school": "boys",
    "girls": "girls",
    "girls only": "girls",
    "all girls": "girls",
    "girls school": "girls",
}

ACCOMMODATION_ALIASES: dict[str, str] = {
    "boarding": "Boarding",
    "boarding only": "Boarding",
    "boarding school": "Boarding",
    "day": "Day",
    "day only": "Day",
    "day school": "Day",
    "day scholar": "Day",
    "day and boarding": "Day & Boarding",
    "day & boarding": "Day & Boarding",
    "both day and boarding": "Day & Boarding",
}

ADMISSION_ALIASES: dict[str, str] = {
    "open": "open",
    "admitting": "open",
    "accepting": "open",
    "open for admission": "open",
    "admissions open": "open",
    "closed": "closed",
    "admissions closed": "closed",
    "not admitting": "closed",
}
