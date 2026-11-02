# eSchool Assistant

An AI-powered school search assistant for [eSchool Uganda](https://eschool.ug).
Parents describe the kind of school they're looking for in natural language;
the assistant interprets the request, queries eSchool's existing search
functionality, and presents the results honestly — including what it could
and could not verify.

Built for the **Halvek Technologies AI Engineer Take-Home Assessment**.

---

## How it works

```
Parent's request (natural language)
        │
        ▼
┌──────────────────┐
│  Interpreter (AI) │  ← LLM extracts structured criteria (JSON, temp=0)
└────────┬─────────┘
         │  SearchCriteria
         ▼
┌──────────────────┐
│    Validator      │  ← normalises & validates against real eSchool filters
└────────┬─────────┘
         │  cleaned SearchCriteria + warnings
         ▼
┌──────────────────┐
│  Client (URL +   │  ← builds query string, fetches HTML with retries/timeouts
│  fetch)          │
└────────┬─────────┘
         │  HTML
         ▼
┌──────────────────┐
│     Parser       │  ← BeautifulSoup extracts school cards from HTML
└────────┬─────────┘
         │  list[School]
         ▼
┌──────────────────┐
│     Matcher       │  ← deterministic: ✓ confirmed / ✗ not matching / ? unknown
└────────┬─────────┘
         │  list[SchoolMatchResult]
         ▼
┌──────────────────┐
│    Presenter      │  ← formats results for the user
└──────────────────┘
```

The AI is used **only** for interpreting the request. Everything else — URL
building, fetching, parsing, matching, and presenting — is deterministic code.
The LLM never sees school data and never searches for schools.

---

## Quick start

### Prerequisites

- Python 3.11+
- An OpenAI API key (or any OpenAI-compatible provider)

### Installation

```bash
git clone <your-repo-url>
cd eschool-assistant
pip install -e ".[dev]"
```

### Configuration

```bash
cp .env.example .env
# Edit .env and add your OpenAI API key
```

### Running

**One-shot mode:**

```bash
python -m eschool_assistant "I'm looking for a girls' boarding school in Kampala, max 1 million per term"
```

**Interactive mode:**

```bash
python -m eschool_assistant
```

Then type search requests at the `Search>` prompt.

**Via installed entry point (after `pip install -e .`):**

```bash
eschool-search "mixed primary school in Wakiso"
```

**Additional options:**

```bash
python -m eschool_assistant --help
# --max-pages N   Fetch up to N result pages (default: 1)
# --verbose       Enable debug logging
```

### Demonstration (no API key needed)

```bash
python -m eschool_assistant.demo
```

This runs three pre-built examples using mock data:

1. A clearly specified request (the assessment's example)
2. An ambiguous request that triggers a clarifying question
3. A request with criteria too narrow to return results

---

## Running tests

```bash
python -m pytest eschool_assistant/tests/ -v
```

All 148 tests pass with no external dependencies (LLM and HTTP are mocked).

---

## Project structure

```
eschool_assistant/
├── __init__.py
├── config.py          # Valid filter values, location/county mappings, aliases
├── models.py          # Pydantic models: SearchCriteria, School, MatchResult, etc.
├── interpreter.py      # AI: parent text → SearchCriteria (JSON via OpenAI)
├── validator.py        # Normalise & validate AI output against known filters
├── client.py           # Build search URL + fetch HTML (timeouts, retries, typed errors)
├── parser.py           # HTML → School objects (BeautifulSoup)
├── matcher.py          # Deterministic: ✓/✗/? check of each school vs criteria
├── pipeline.py         # Orchestrates the full flow
├── presenter.py        # Formats results for display
├── cli.py              # Command-line interface (argparse + interactive)
├── demo.py             # Demonstration script (3 examples, no API key needed)
└── tests/
    ├── conftest.py      # Shared fixtures (mock LLM, mock HTTP, fixture loading)
    ├── test_models.py
    ├── test_interpreter.py
    ├── test_validator.py
    ├── test_client.py
    ├── test_parser.py
    ├── test_matcher.py
    ├── test_pipeline.py
    └── fixtures/       # Saved HTML from eschool.ug for testing
```

---

## Key design decisions

- **AI only interprets, never searches.** The LLM extracts structured criteria;
  all searching, parsing, and matching is deterministic. This keeps the AI's
  role minimal and testable.
- **Honest matching with three statuses.** Every criterion gets ✓ (confirmed
  from card data), ✗ (does not match card data), or ? (filtered by search but
  not visible on the card). We never claim a school meets a requirement we
  can't verify.
- **Specified vs. unspecified.** Fields the parent didn't mention are `null`,
  so we never silently apply defaults.
- **No secrets in the repo.** API keys go in `.env` (gitignored). Use
  `.env.example` as a template.

See [DESIGN.md](DESIGN.md) for the full design explanation.

---

## Assumptions and limitations

- **HTML scraping, no JSON API.** eSchool's search returns server-rendered
  HTML. We parse it with BeautifulSoup. If the site changes its HTML
  structure, the parser will need updating.
- **Limited card data.** Search result cards show name, level, rating,
  location, and admission status — but **not** fees, gender, or boarding
  status. These are applied as search filters but cannot be independently
  verified from the card. The matcher reports them as "?" (unknown).
- **County options are location-dependent.** We pre-build county mappings for
  Kampala, Wakiso, and Mukono. For other locations, county values are passed
  through without validation (the search will simply return no results for
  an invalid county).
- **First page only by default.** The search returns 24 results per page. By
  default we fetch only page 1. Use `--max-pages N` to fetch more.
- **robots.txt compliance.** eSchool's robots.txt allows general crawling
  (`Allow: /`) with `search=yes`. We respect this by making reasonable,
  rate-limited requests and not training AI models on the content.
- **No backend/database access.** As stated in the brief, we work only with
  the public search page.
