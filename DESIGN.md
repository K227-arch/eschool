# Design Explanation

This document addresses the six points required by Section 4 (Deliverables,
point 4) of the assessment brief.

---

## 1. How the solution was designed

The core principle is **separation of concerns**: the AI does one thing
(interpreting natural language), and deterministic code does everything else.

### Architecture overview

```
parent text → Interpreter (AI) → SearchCriteria
    → Validator → cleaned criteria + warnings
    → Client (build URL + fetch HTML)
    → Parser → list[School]
    → Matcher → list[SchoolMatchResult]
    → Presenter → human-readable output
```

Each module has a single responsibility and a clear interface (Pydantic
models). This makes the system:

- **Testable**: every module can be tested in isolation with mocks.
- **Debuggable**: the pipeline returns the full `SearchResponse` including
  the interpreted criteria, the search URL, and per-school match details.
- **Replaceable**: the AI provider, HTTP client, and even the HTML parser can
  be swapped without touching the rest of the pipeline.

### Why Python + Pydantic?

Pydantic gives us runtime validation of the LLM's output for free. If the
model returns a string where an integer is expected (e.g., `"1000000"`
instead of `1000000` for `max_fees`), Pydantic either coerces it or raises a
clear error — we never silently pass bad data downstream.

### Why this flow and not a single LLM call?

We could ask the LLM to "search for schools" in one shot, but that would mean
the model either needs access to the school database (which we don't have)
or would hallucinate results. By splitting interpretation from search, the
LLM only does what it's good at (understanding language), and the search uses
the real eSchool platform — no invented data.

---

## 2. How the natural-language request is converted into search criteria

### The interpreter prompt

The system prompt (see `interpreter.py`, `build_system_prompt()`) tells the
LLM:

1. Its role: extract structured search criteria from a parent's request.
2. The exact JSON schema to return (with every field defaulting to `null` or
   `[]`).
3. The valid values for each filter (e.g., the 67 Ugandan districts, the
   valid gender values, valid school levels).
4. Rules: only fill fields the parent explicitly mentions; interpret "1M" as
   1,000,000 UGX; never fabricate values; identify unsupported criteria; ask
   a clarifying question if the request is too vague.

### Example

**Input:**
> "I'm looking for a girls' boarding school in Kampala, preferably around
> Central Division, charging no more than UGX 1 million per term and
> currently admitting Senior One students."

**LLM output (JSON):**
```json
{
  "location": "KAMPALA",
  "county": "KAMPALA CENTRAL DIVISION",
  "max_fees": 1000000,
  "gender": "girls",
  "accommodation": "Boarding",
  "levels": ["Secondary"],
  "unsupported_criteria": ["currently admitting Senior One students"],
  "interpretation_notes": [
    "Interpreted '1M' as max 1,000,000 UGX per term",
    "Assumed 'Central Division' refers to Kampala Central Division"
  ]
}
```

### Why temperature 0?

We want deterministic extraction — the same request should produce the same
criteria every time. Temperature 0 minimises randomness.

### Why JSON mode?

OpenAI's `response_format={"type": "json_object"}` guarantees valid JSON
output. Combined with Pydantic validation on our side, we get two layers of
structure enforcement. If the LLM still returns malformed JSON (e.g., wrapped
in markdown fences), the interpreter attempts a repair before raising an
`LLMError`.

---

## 3. How the application interacts with eSchool

### What we discovered (Step 0 investigation)

The search page at `https://eschool.ug/find-schools/search` is
server-rendered HTML — there is no JSON API. A GET request with query
parameters returns a full HTML page with school cards embedded.

### Available search filters

| Parameter | Type | Values |
|-----------|------|--------|
| `location` | dropdown | 67 Ugandan districts (uppercase) |
| `county` | dropdown (depends on location) | Divisions/counties per district |
| `min_fees` | text | UGX amount (integer) |
| `max_fees` | text | UGX amount (integer) |
| `gender` | radio | `mixed`, `boys`, `girls` |
| `levels[]` | checkbox | `Nursery & Kindergaten`, `Nursery & Primary`, `Primary`, `Secondary`, `International` |
| `admission_status` | radio | `open`, `closed` |
| `accomadation` (sic) | dropdown | `Day & Boarding`, `Day`, `Boarding` |
| `curriculums[]` | checkbox | `UNEB`, `Cambridge`, `IB`, `Montessori`, `Islamic`, `Other` |
| `facilities[]` | checkbox | Science Labs, Computer Lab, Library, etc. |
| `religions[]` | checkbox | Catholic Founded, Church of Uganda, etc. |
| `sorting` | dropdown | `Popular`, `FeesLow`, `Newest` |
| `q` | text | School name keyword |
| `page` | integer | Pagination (24 results per page) |

Note: the site spells the accommodation parameter as `accomadation` (sic). We
keep that spelling for URL building but expose it as `accommodation` in our
models.

### How we fetch

The `client.py` module:
1. **Builds the URL** from `SearchCriteria`, only including non-null fields.
2. **Fetches with httpx** with a configurable timeout (default 30s).
3. **Retries** up to 2 times on connection errors and HTTP 5xx responses.
4. **Raises typed errors** (`SearchHTTPError`, `SearchTimeoutError`,
   `SearchError`) so the pipeline can show a friendly message instead of
   crashing.

### What the results page shows

Each school card (an `<article>` element) contains:
- School name, slug, and detail-page URL
- Level (e.g., "Secondary")
- Rating (e.g., 4.3)
- Location (district, e.g., "Kampala")
- Admission status badge ("Admissions Closed" / "Open for 2026")
- School ID (from a `data-school-id` attribute)

**Not shown on the card**: fees, gender, boarding/day status, county,
curriculum, facilities, religion. These are applied as search filters but
cannot be independently verified from the results page.

### robots.txt

eSchool's `robots.txt` allows general crawling (`Allow: /`) with
`search=yes`. We make reasonable, rate-limited requests (with delays between
page fetches) and do not train AI models on the content.

---

## 4. Why we chose this AI integration and technical approach

### AI integration: OpenAI API with JSON mode

- **Structured output**: JSON mode guarantees valid JSON, which we validate
  with Pydantic. This is more reliable than parsing free-form text.
- **Temperature 0**: Deterministic extraction — the same input always
  produces the same criteria.
- **Minimal AI surface area**: The LLM only sees the parent's text and the
  system prompt. It never sees school data, never searches, and never
  recommends. This keeps the AI's role narrow and the rest of the system
  fully deterministic and testable.
- **Provider flexibility**: The interpreter uses the `openai` Python library,
  which supports any OpenAI-compatible endpoint (OpenRouter, Azure, local
  LLMs via `OPENAI_BASE_URL`).

### Technical approach: Python, Pydantic, httpx, BeautifulSoup, pytest

- **Python**: The brief allows any language. Python has the best ecosystem
  for AI integration (the `openai` library), structured data (Pydantic), and
  HTML parsing (BeautifulSoup).
- **Pydantic**: Runtime validation of LLM output — catches type mismatches
  and missing fields that would otherwise propagate as silent bugs.
- **httpx**: Modern HTTP client with synchronous API, connection pooling,
  and first-class timeout/retry support. Pairs well with `respx` for testing.
- **BeautifulSoup**: Robust HTML parsing that handles real-world messy HTML.
  The parser targets structural elements (article tags, specific classes)
  rather than fragile CSS selectors.
- **pytest**: Standard testing framework with fixtures and parametrisation.
  All tests use mocks — no real API calls or network requests.

### Why CLI and not a web app?

The brief allows CLI, API, or web app. A CLI is the simplest to build, test,
and demonstrate while still being usable. The pipeline is framework-agnostic
(`search_schools()` returns a `SearchResponse` Pydantic model), so adding a
FastAPI endpoint later would be a thin wrapper.

---

## 5. How we handle ambiguity, missing information, and failures

### Ambiguity

| Situation | Behaviour |
|-----------|-----------|
| Vague request ("a good school") | LLM returns a `clarifying_question`; pipeline stops and asks the parent |
| Unsupported criterion ("admitting Senior One") | Reported in `unsupported_criteria`; search continues with supported filters; parent is told what was left out |
| Ambiguous fees ("around 1M") | LLM interprets as max 1,000,000 and notes the interpretation in `interpretation_notes` |
| Ambiguous location ("near town") | If the LLM can't map it to a valid district, the validator removes it with a warning |

### Missing information

| Situation | Behaviour |
|-----------|-----------|
| Parent omits a filter (e.g., no budget) | Field stays `null`; no filter applied; matcher doesn't check it |
| School card missing a field (e.g., no rating) | Parsed as `None`; matcher reports "?" (unknown) |
| Criterion filtered by search but not shown on card | Matcher reports "?" with explanation: "filtered by search, not shown on results card" |
| School in a different district than searched | Matcher reports ✗ with explanation: "School is in {X}, not {Y}. It appeared because eSchool's location search includes nearby areas." |

### Failures

| Situation | Behaviour |
|-----------|-----------|
| LLM API down / key invalid | `LLMError` caught; friendly message: "The AI service is unavailable" |
| LLM returns invalid JSON | Repair attempted (strip markdown fences); if still invalid, `LLMError` with message |
| eSchool site down | `SearchError` caught; retries up to 2 times; friendly message: "Could not connect to eSchool" |
| HTTP 500 from eSchool | Retried up to 2 times; if persistent, `SearchHTTPError` with status code |
| Request timeout | `SearchTimeoutError` with timeout duration |
| No schools match | Pipeline notes: "No schools found. Try relaxing some filters..." |
| Empty or huge input | Input validation rejects requests < 3 chars or > 2000 chars |
| Prompt injection | The LLM is instructed to only extract criteria; it cannot execute code, access files, or make network requests. Input length is capped. |

### The three-status matcher

The most important design decision for honesty. For every criterion the
parent specified, the matcher returns one of:

- **✓ Confirmed**: the card data proves the criterion holds (e.g., school is
  in Kampala, asked for Kampala).
- **✗ Not matching**: the card data proves the criterion does not hold (e.g.,
  school level is Primary, asked for Secondary).
- **? Unknown**: the criterion was applied as a search filter but the card
  doesn't show the relevant field (e.g., fees, gender, boarding status). We
  trust the search filter but explicitly say we can't independently verify it.

This prevents the system from ever claiming a school meets a requirement
when the available data doesn't support that conclusion — which is the
brief's key concern.

---

## 6. What we would improve with more time

### Short-term improvements

1. **School detail page enrichment.** The card doesn't show fees, gender, or
   boarding status, but the detail page does. After parsing search results,
   we could fetch each school's detail page to verify these criteria
   independently (moving them from "?" to "✓" or "✗"). This would add one
   HTTP request per school — acceptable with rate limiting.

2. **Dynamic county validation.** Currently we pre-build county mappings for
   only Kampala, Wakiso, and Mukono. For other locations, county values pass
   through unvalidated. We could dynamically fetch the search page with just
   the location parameter to discover valid county options.

3. **Caching.** Repeated searches with the same criteria could return cached
   results instead of re-fetching from eSchool. A simple TTL-based cache
   (e.g., 5 minutes) would reduce load on the site and speed up responses.

4. **Evaluation set for the interpreter.** A set of 50–100 parent requests
   with expected criteria would let us measure the LLM's extraction accuracy
   and catch regressions when we change the prompt or model.

5. **Fuzzy location matching.** A parent might say "Kampala city" or "in and
   around Kampala". Currently the validator does exact matching (case-
   insensitive). A fuzzy matcher using edit distance or embeddings would
   handle minor variations.

### Medium-term improvements

6. **Conversational loop.** When the system asks a clarifying question, the
   parent's answer should be combined with the original request for a
   refined search. This requires maintaining conversation state.

7. **FastAPI web endpoint.** A thin wrapper around `search_schools()` that
   exposes a REST API. The presenter could return JSON instead of text, with
   a separate frontend for rendering.

8. **Official API integration.** If eSchool provides (or would provide) a
   JSON API, we'd switch from HTML scraping to structured API calls —
   eliminating parser fragility and giving us richer data per result.

9. **Cost and latency monitoring.** Track LLM token usage and response times
   to identify when to switch models (e.g., gpt-4o-mini for simple requests,
   gpt-4o for complex ones).

### Long-term improvements

10. **Streaming results.** Fetch and display results as they're parsed,
    rather than waiting for all pages to load.

11. **Multi-language support.** Parents might search in Luganda or other
    Ugandan languages. The interpreter could be extended to handle these.

12. **A/B testing of prompts.** Compare different system prompts on the
    evaluation set to find the best extraction accuracy.
