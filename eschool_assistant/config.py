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

# ── County / division mapping ─────────────────────────────────────────────
# Built by scraping the live eSchool search page for every district.
# 52 of the 67 listed districts have schools; the rest have no results.
# Districts with NO schools on eSchool (as of discovery run):
#   BULIISA, KAMULI, KANUNGU, KYANKWANZI, NAMAYINGO, NEBBI, NGORA, PADER
COUNTY_MAP: dict[str, list[str]] = {
    "ADJUMANI": ["ADJUMANI COUNTY"],
    "ALEBTONG": ["ALEBTONG COUNTY"],
    "APAC": ["APAC MUNICIPALITY", "APAC COUNTY"],
    "ARUA": ["ARUA CITY DIVISION", "ARUA MUNICIPALITY"],
    "BUDUDA": ["BUDUDA COUNTY"],
    "BUIKWE": ["BUIKWE COUNTY SOUTH", "BUIKWE COUNTY NORTH", "NJERU MUNICIPALITY"],
    "BUKEDEA": ["BUKEDEA COUNTY", "KWEEN COUNTY"],
    "BUSHENYI": [
        "BUSHENYI-ISHAKA MUNICIPALITY",
        "IGARA COUNTY EAST",
        "IGARA COUNTY WEST",
    ],
    "BUTAMBALA": ["BUTAMBALA COUNTY"],
    "GULU": ["GULU CITY DIVISION EAST", "GULU CITY DIVISION WEST"],
    "HOIMA": ["HOIMA CITY DIVISION", "HOIMA COUNTY", "KIGOROBYA COUNTY"],
    "IBANDA": ["IBANDA MUNICIPALITY"],
    "IGANGA": ["IGANGA MUNICIPALITY", "IGANGA COUNTY"],
    "ISINGIRO": ["ISINGIRO COUNTY NORTH", "ISINGIRO COUNTY SOUTH", "KAZO COUNTY"],
    "JINJA": [
        "JINJA CITY DIVISION EAST",
        "JINJA CITY DIVISION WEST",
        "JINJA CITY DIVISION NORTH",
        "JINJA COUNTY",
    ],
    "KABALE": ["KABALE MUNICIPALITY", "NDORWA COUNTY WEST"],
    "KABAROLE": ["KABAROLE COUNTY"],
    "KAGADI": ["KAGADI COUNTY"],
    "KAKUMIRO": ["KAKUMIRO COUNTY"],
    "KALIRO": ["KALIRO COUNTY"],
    "KALUNGU": ["KALUNGU COUNTY EAST", "KALUNGU COUNTY WEST"],
    "KAMPALA": [
        "KAMPALA CENTRAL DIVISION",
        "KAWEMPE DIVISION NORTH",
        "KAWEMPE DIVISION SOUTH",
        "MAKINDYE DIVISION EAST",
        "MAKINDYE DIVISION WEST",
        "NAKAWA DIVISION",
        "RUBAGA DIVISION NORTH",
        "RUBAGA DIVISION SOUTH",
    ],
    "KAMWENGE": ["KAMWENGE COUNTY"],
    "KASESE": ["KASESE MUNICIPALITY", "BUKONJO COUNTY EAST", "BUKONJO COUNTY WEST"],
    "KAYUNGA": ["KAYUNGA COUNTY", "NTENJERU COUNTY"],
    "KIRYANDONGO": ["KIRYANDONGO COUNTY"],
    "KOLE": ["KOLE COUNTY"],
    "KUMI": ["KUMI MUNICIPALITY"],
    "KYEGEGWA": ["KYEGEGWA COUNTY"],
    "KYENJOJO": ["KYENJOJO COUNTY"],
    "KYOTERA": ["KYOTERA COUNTY", "RAKAI COUNTY"],
    "LIRA": ["LIRA CITY DIVISION EAST", "LIRA CITY DIVISION WEST"],
    "LUWEERO": ["LUWEERO COUNTY", "KATIKAMU COUNTY NORTH", "KATIKAMU COUNTY SOUTH"],
    "LWENGO": ["LWENGO COUNTY", "KINONI COUNTY", "BUKOTO COUNTY EAST"],
    "MANAFWA": ["MANAFWA COUNTY"],
    "MASAKA": ["MASAKA CITY DIVISION", "BUKOTO COUNTY WEST", "LWENGO COUNTY"],
    "MASINDI": ["MASINDI MUNICIPALITY", "MASINDI COUNTY"],
    "MAYUGE": ["MAYUGE COUNTY", "BUNYA COUNTY"],
    "MBALE": ["MBALE CITY DIVISION", "BUNGOKHO COUNTY"],
    "MBARARA": [
        "MBARARA CITY DIVISION EAST",
        "MBARARA CITY DIVISION WEST",
        "MBARARA COUNTY",
    ],
    "MITYANA": ["MITYANA MUNICIPALITY", "MITYANA COUNTY"],
    "MPIGI": ["MPIGI COUNTY"],
    "MUBENDE": ["MUBENDE MUNICIPALITY", "MUBENDE COUNTY", "KASSANDA COUNTY"],
    "MUKONO": [
        "MUKONO MUNICIPALITY",
        "MUKONO COUNTY NORTH",
        "MUKONO COUNTY SOUTH",
        "NAKIFUMA COUNTY",
    ],
    "NAKASEKE": ["NAKASEKE COUNTY"],
    "NAKASONGOLA": ["NAKASONGOLA COUNTY"],
    "NAMUTUMBA": ["NAMUTUMBA COUNTY"],
    "NAPAK": ["NAPAK COUNTY"],
    "NTUNGAMO": [
        "NTUNGAMO MUNICIPALITY",
        "NTUNGAMO COUNTY",
        "RUSHENYI COUNTY",
        "RUHAAMA COUNTY",
    ],
    "PALLISA": ["PALLISA COUNTY"],
    "RUBIRIZI": ["BUNYARUGURU COUNTY"],
    "RUKIGA": ["RUKIGA COUNTY"],
    "RUKUNGIRI": ["RUKUNGIRI MUNICIPALITY", "RUBABO COUNTY"],
    "SERERE": ["SERERE COUNTY"],
    "SHEEMA": ["SHEEMA MUNICIPALITY", "SHEEMA COUNTY NORTH", "SHEEMA COUNTY SOUTH"],
    "SOROTI": ["SOROTI MUNICIPALITY", "SOROTI COUNTY"],
    "TORORO": ["TORORO MUNICIPALITY", "TORORO NORTH COUNTY", "TORORO SOUTH COUNTY"],
    "WAKISO": [
        "BUSIRO COUNTY EAST",
        "BUSIRO COUNTY NORTH",
        "BUSIRO COUNTY SOUTH",
        "ENTEBBE MUNICIPALITY",
        "KIRA MUNICIPALITY",
        "KYADONDO COUNTY EAST",
        "MAKINDYE-SSABAGABO MUNICIPALITY",
        "NANSANA MUNICIPALITY",
    ],
    "YUMBE": ["ARINGA COUNTY", "ARINGA SOUTH COUNTY"],
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
