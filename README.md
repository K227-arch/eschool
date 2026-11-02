# eSchool Assistant

An AI-powered school search assistant for [eSchool Uganda](https://eschool.ug).
Parents describe the kind of school they're looking for in natural language;
the assistant interprets the request, queries eSchool's live search, and
presents results honestly — including what it could and could not verify.

Built for the **Halvek Technologies AI Engineer Take-Home Assessment**.

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/K227-arch/eschool.git
cd eschool
pip install -e ".[dev]"
```

### 2. Configure an API key (optional but recommended)

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Option A — Groq (free tier, no credit card needed)
# Get a key at: https://console.groq.com/keys
GROQ_API_KEY=gsk_your_key_here

# Option B — OpenAI
# OPENAI_API_KEY=sk-your_key_here

# No key? Leave both blank — rule-based mode works out of the box.
```

### 3. Run

**Web UI:**
```bash
python -m eschool_assistant --web
# Open http://localhost:5000
```

**CLI:**
```bash
python -m eschool_assistant "secondary schools in Kampala"
python -m eschool_assistant "girls boarding school in Wakiso, max 500,000"
python -m eschool_assistant "mixed primary in Mukono, admissions open"
```

**Demo (no API key, no network — uses saved snapshots):**
```bash
python -m eschool_assistant.demo
```

**Tests:**
```bash
python -m pytest eschool_assistant/tests/ -v
# 148 tests, all mocked — no API calls, no network needed
```

---

## How it works

```
Parent request (natural language)
        │
        ▼
┌─────────────────────────┐
│  Interpreter            │  Groq AI / OpenAI / rule-based (auto-selected)
│  text → SearchCriteria  │  temperature=0  |  compact prompt for small models
└──────────┬──────────────┘
           │  SearchCriteria (JSON)
           ▼
┌─────────────────────────┐
│  Validator              │  normalise + validate against real eSchool filters
└──────────┬──────────────┘
           │  cleaned criteria
           ▼
┌─────────────────────────┐
│  Client                 │  build URL → fetch HTML (retries, timeouts)
└──────────┬──────────────┘
           │  HTML
           ▼
┌─────────────────────────┐
│  Parser                 │  extract school cards
│  + detail enrichment    │  fetch gender / boarding from detail pages
└──────────┬──────────────┘
           │  list[School]
           ▼
┌─────────────────────────┐
│  Location filter        │  remove schools from wrong district
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Matcher                │  ✓ confirmed / ✗ not matching / ? unknown
└──────────┬──────────────┘
           │  list[SchoolMatchResult]  ranked best-first
           ▼
┌─────────────────────────┐
│  Presenter / Web UI     │  CLI text output or Flask web app
└─────────────────────────┘
```

The AI interprets language only. All searching, parsing, matching, and
ranking is deterministic code.

---

## Interpretation modes

| Mode | When active | Notes |
|------|-------------|-------|
| **Groq AI** (`allam-2-7b`) | `GROQ_API_KEY` set | Free tier, ~1s response |
| **OpenAI** (`gpt-4o-mini`) | `OPENAI_API_KEY` set (Groq takes priority) | Requires paid credits |
| **Rule-based** | No key set, or AI unreachable | Handles all standard requests |

If Groq is set but temporarily unreachable, the pipeline silently falls back
to rule-based so the app never shows an error to the user.

---

## What's verified vs. filtered-only

eSchool's search result cards only show **name, level, location, rating, and
admission status**. The pipeline enriches results by fetching each school's
detail page for gender and boarding.

| Criterion | Source | Status shown |
|-----------|--------|--------------|
| Location (district) | Search card | ✓ or ✗ confirmed |
| School level | Search card | ✓ or ✗ confirmed |
| Admission status | Search card | ✓ or ✗ confirmed |
| Gender | Detail page (fetched) | ✓ or ✗ confirmed |
| Accommodation (boarding/day) | Detail page (fetched) | ✓ or ✗ confirmed |
| Fees | Filter only | ? cannot verify from page |
| County/division | Filter only | ? cannot verify from card |
| Curriculum, facilities, religion | Filter only | ? cannot verify from card |

---

## Key features

- **Strict location filtering** — eSchool's search leaks nearby districts
  (e.g. Wakiso, Mukono when you search Kampala). The pipeline removes those
  and tells you how many were filtered out.
- **Smart ranking** — fully confirmed matches first, then matches with
  unknowns, then mismatches. Within each tier, sorted by rating.
- **5-minute cache** — repeated identical searches return instantly.
- **Broadening fallback** — if a county-level search returns nothing, the
  pipeline widens to district level automatically.
- **Hallucination guard** — for small Groq models, fields like levels,
  accommodation, and unsupported_criteria are cross-checked against the
  actual request text before being used.
- **Auto fallback** — Groq unreachable → rule-based mode, no error shown.

---

## Project structure

```
eschool_assistant/
├── config.py           # Filter values, county maps, Groq/OpenAI settings
├── models.py           # Pydantic models: SearchCriteria, School, MatchResult …
├── interpreter.py      # AI: text → SearchCriteria (Groq/OpenAI, temp=0)
├── rule_interpreter.py # Regex fallback interpreter (no API key needed)
├── validator.py        # Normalise AI output against real eSchool filter values
├── client.py           # URL builder + HTML fetcher (retries, typed errors)
├── parser.py           # HTML → School objects + detail-page enrichment
├── matcher.py          # ✓/✗/? checks per criterion per school
├── pipeline.py         # Full flow: interpret → validate → fetch → match → rank
├── presenter.py        # CLI text output formatter
├── app.py              # Responsive Flask web UI
├── cli.py              # argparse CLI (one-shot + interactive)
├── demo.py             # 3 offline demo examples (no key/network needed)
└── tests/
    ├── conftest.py     # Mock LLM + HTTP fixtures
    ├── test_*.py       # 148 tests covering every module
    └── fixtures/       # Saved HTML snapshots from eschool.ug
```

---

## Available search filters

| Filter | Values |
|--------|--------|
| Location | 67 Ugandan districts (e.g. KAMPALA, WAKISO, GULU) |
| County/division | Depends on district |
| Max/min fees per term | UGX integer |
| Gender | `mixed`, `boys`, `girls` |
| School level | Nursery & Kindergaten, Nursery & Primary, Primary, Secondary, International |
| Admission status | `open`, `closed` |
| Accommodation | `Boarding`, `Day`, `Day & Boarding` |
| Curriculum | UNEB, Cambridge, IB, Montessori, Islamic, Other |
| Facilities | Science Labs, Computer Lab, Library, Sports Facilities … |
| Religion | Catholic, Church of Uganda, SDA, Pentecostal, Islamic … |

---

## Limitations

- **HTML scraping** — no public JSON API. The parser will need updating if
  eSchool changes its HTML structure.
- **Fees not verifiable** — not shown on any public page; applied as filter only.
- **County pre-built for Kampala, Wakiso, Mukono only** — other districts
  pass through unvalidated.
- **Page 1 only by default** — 24 results per page; use `--max-pages N` for more.
- **Groq model quality** — `allam-2-7b` is the best free Groq model available.
  The compact prompt + hallucination guard keeps output clean for standard requests.
- **robots.txt** — `eschool.ug` allows crawling (`Allow: /`, `search=yes`).
  Requests are rate-limited and detail pages are cached for 1 hour.

See [DESIGN.md](DESIGN.md) for the full design explanation.
