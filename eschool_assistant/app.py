"""Flask web application for the eSchool Assistant.

Run with:
    python -m eschool_assistant --web

Then open http://localhost:5000 in your browser.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask, render_template_string, request

from .pipeline import search_schools

load_dotenv()

app = Flask(__name__)


def _mode_label() -> str:
    if os.getenv("GROQ_API_KEY"):
        return "AI-powered · Groq"
    if os.getenv("OPENAI_API_KEY"):
        return "AI-powered · OpenAI"
    return "Rule-based mode"


# ── HTML template ─────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>eSchool Assistant</title>
  <style>
    /* ── Reset & base ────────────────────────────────── */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { font-size: 16px; -webkit-text-size-adjust: 100%; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                   "Helvetica Neue", Arial, sans-serif;
      background: #f0f4f8;
      color: #1a202c;
      min-height: 100vh;
      line-height: 1.5;
    }
    a { color: #0B4DBB; }
    a:hover { text-decoration: underline; }
    img { max-width: 100%; }

    /* ── Header ──────────────────────────────────────── */
    header {
      background: #0B4DBB;
      color: #fff;
      padding: 14px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 10px;
    }
    .header-brand { display: flex; align-items: center; gap: 10px; }
    .header-brand h1 { font-size: clamp(1.1rem, 3vw, 1.4rem); font-weight: 700; }
    .header-sub { font-size: 0.78rem; opacity: 0.75; margin-top: 1px; }
    .mode-badge {
      font-size: 0.75rem;
      background: rgba(255,255,255,0.18);
      padding: 3px 10px;
      border-radius: 20px;
      white-space: nowrap;
    }

    /* ── Search section ──────────────────────────────── */
    .search-section {
      background: #fff;
      border-bottom: 1px solid #e2e8f0;
      padding: 20px;
    }
    .search-section h2 {
      font-size: 0.9rem;
      font-weight: 600;
      color: #4a5568;
      margin-bottom: 10px;
    }
    .search-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .search-row input {
      flex: 1 1 220px;
      padding: 11px 14px;
      border: 2px solid #e2e8f0;
      border-radius: 8px;
      font-size: 0.95rem;
      outline: none;
      transition: border-color 0.15s;
      min-width: 0;
    }
    .search-row input:focus { border-color: #0B4DBB; }
    .search-row button {
      flex-shrink: 0;
      background: #0B4DBB;
      color: #fff;
      border: none;
      padding: 11px 22px;
      border-radius: 8px;
      font-size: 0.95rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s;
      width: 100%;
    }
    .search-row button:hover { background: #0a3fa0; }
    .search-row button:active { background: #083492; }

    /* On wider screens button is inline */
    @media (min-width: 480px) {
      .search-row button { width: auto; }
    }

    .examples {
      margin-top: 10px;
      font-size: 0.8rem;
      color: #718096;
      display: flex;
      flex-wrap: wrap;
      gap: 6px 12px;
      align-items: center;
    }
    .examples strong { color: #4a5568; }
    .ex-link {
      color: #0B4DBB;
      text-decoration: none;
      cursor: pointer;
      background: #EBF4FF;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 0.78rem;
    }
    .ex-link:hover { background: #BEE3F8; text-decoration: none; }

    /* ── Main content ────────────────────────────────── */
    main {
      max-width: 900px;
      margin: 0 auto;
      padding: 20px 16px 48px;
    }

    /* ── Criteria card ───────────────────────────────── */
    .criteria-card {
      background: #fff;
      border-radius: 10px;
      border: 1px solid #e2e8f0;
      padding: 16px 18px;
      margin-bottom: 16px;
    }
    .criteria-card h3 {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #718096;
      margin-bottom: 10px;
    }
    .criteria-pills { display: flex; flex-wrap: wrap; gap: 7px; }
    .pill {
      background: #EBF4FF;
      color: #1a56db;
      border-radius: 20px;
      padding: 4px 11px;
      font-size: 0.8rem;
      font-weight: 500;
    }
    .pill.unsupported { background: #FEFCBF; color: #744210; }
    .no-criteria { color: #a0aec0; font-style: italic; font-size: 0.88rem; }

    /* ── Notes ───────────────────────────────────────── */
    .note {
      display: flex;
      gap: 8px;
      background: #FFFBEB;
      border-left: 3px solid #F6AD55;
      padding: 8px 12px;
      border-radius: 0 6px 6px 0;
      font-size: 0.82rem;
      color: #744210;
      margin-bottom: 6px;
    }
    .note.info  { background: #EBF8FF; border-color: #63B3ED; color: #2C5282; }
    .note.mode  { background: #F0FFF4; border-color: #68D391; color: #22543D; }
    .note-icon  { flex-shrink: 0; }

    /* ── Clarification ───────────────────────────────── */
    .clarification {
      background: #EBF4FF;
      border: 1px solid #bee3f8;
      border-radius: 10px;
      padding: 20px 18px;
      margin-bottom: 16px;
    }
    .clarification h3 { color: #2B6CB0; margin-bottom: 8px; font-size: 1rem; }
    .clarification p  { color: #2C5282; font-size: 0.9rem; }

    /* ── Error box ───────────────────────────────────── */
    .error-box {
      background: #FFF5F5;
      border: 1px solid #fed7d7;
      border-radius: 10px;
      padding: 20px 18px;
      margin-bottom: 16px;
    }
    .error-box h3 { color: #C53030; margin-bottom: 8px; }
    .error-box p  { color: #742A2A; font-size: 0.88rem; }

    /* ── Results header ──────────────────────────────── */
    .results-header {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 14px;
    }
    .results-header h3 { font-size: 0.95rem; color: #2D3748; }
    .results-header a  { font-size: 0.8rem; white-space: nowrap; }

    /* ── School card ─────────────────────────────────── */
    .school-card {
      background: #fff;
      border-radius: 10px;
      border: 1px solid #e2e8f0;
      padding: 16px 18px;
      margin-bottom: 12px;
      transition: box-shadow 0.15s;
    }
    .school-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,0.07); }

    .school-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
      margin-bottom: 6px;
      flex-wrap: wrap;
    }
    .school-name {
      font-size: 1rem;
      font-weight: 700;
      flex: 1 1 200px;
    }
    .school-name a { color: #0B4DBB; text-decoration: none; }
    .school-name a:hover { text-decoration: underline; }

    .school-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
      font-size: 0.8rem;
      color: #718096;
      margin-bottom: 10px;
    }
    .school-meta span { display: flex; align-items: center; gap: 3px; }

    /* Badges */
    .badge {
      display: inline-flex;
      align-items: center;
      padding: 2px 9px;
      border-radius: 20px;
      font-size: 0.73rem;
      font-weight: 600;
      white-space: nowrap;
    }
    .badge-level  { background: #EDF2F7; color: #4A5568; }
    .badge-open   { background: #C6F6D5; color: #22543D; }
    .badge-closed { background: #FED7D7; color: #742A2A; }
    .badge-rating { background: #FEFCBF; color: #744210; }
    .badge-gender-girls        { background: #FED7E2; color: #97266D; }
    .badge-gender-boys         { background: #BEE3F8; color: #2C5282; }
    .badge-gender-mixed        { background: #E9D8FD; color: #553C9A; }
    .badge-accommodation       { background: #C6F6D5; color: #276749; }
    .badge-fees                { background: #FEFCBF; color: #744210; font-weight: 600; }

    /* Match checks — collapsible on mobile */
    .checks {
      border-top: 1px solid #EDF2F7;
      padding-top: 10px;
      margin-top: 6px;
    }
    .check {
      display: flex;
      gap: 7px;
      font-size: 0.8rem;
      padding: 3px 0;
      color: #4A5568;
      align-items: flex-start;
    }
    .sym { font-weight: 700; flex-shrink: 0; width: 14px; margin-top: 1px; }
    .sym.ok   { color: #38A169; }
    .sym.fail { color: #E53E3E; }
    .sym.unk  { color: #D69E2E; }
    .check-text strong { font-weight: 600; }

    /* Verdict */
    .verdict {
      margin-top: 10px;
      font-size: 0.78rem;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 6px;
      display: inline-block;
    }
    .verdict.full     { background: #C6F6D5; color: #22543D; }
    .verdict.partial  { background: #FEEBC8; color: #744210; }
    .verdict.mismatch { background: #FED7D7; color: #742A2A; }

    /* Toggle checks */
    .toggle-checks {
      font-size: 0.78rem;
      color: #0B4DBB;
      cursor: pointer;
      background: none;
      border: none;
      padding: 0;
      margin-top: 4px;
      text-decoration: underline;
    }

    /* ── Summary bar ─────────────────────────────────── */
    .summary-bar {
      background: #EBF4FF;
      border-radius: 10px;
      padding: 12px 18px;
      text-align: center;
      font-size: 0.85rem;
      color: #2B6CB0;
      margin-top: 16px;
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 6px 16px;
    }

    /* ── No results / landing ────────────────────────── */
    .empty-state {
      text-align: center;
      padding: 48px 20px;
      color: #718096;
    }
    .empty-state .icon { font-size: 2.8rem; margin-bottom: 14px; }
    .empty-state h3 { font-size: 1.15rem; color: #4A5568; margin-bottom: 8px; }
    .empty-state p { max-width: 400px; margin: 0 auto; font-size: 0.9rem; }

    /* ── Spinner ─────────────────────────────────────── */
    #spinner {
      display: none;
      text-align: center;
      padding: 48px 20px;
      color: #718096;
    }
    .spin {
      display: inline-block;
      width: 30px; height: 30px;
      border: 3px solid #e2e8f0;
      border-top-color: #0B4DBB;
      border-radius: 50%;
      animation: spin 0.75s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── Responsive breakpoints ──────────────────────── */

    /* Tablet+ */
    @media (min-width: 600px) {
      .search-section { padding: 22px 28px; }
      main { padding: 24px 24px 60px; }
      .school-card { padding: 18px 22px; }
      .criteria-card { padding: 16px 20px; }
    }

    /* Desktop */
    @media (min-width: 768px) {
      header { padding: 16px 32px; }
      .search-section { padding: 24px 32px; }
      main { padding: 28px 28px 72px; }
      .search-section h2 { font-size: 1rem; }
      .school-name { font-size: 1.05rem; }
    }

    /* Collapsed checks on small screens */
    @media (max-width: 499px) {
      .checks { display: none; }
      .checks.open { display: block; }
    }
    @media (min-width: 500px) {
      .toggle-checks { display: none; }
    }
  </style>
</head>
<body>

<!-- ── Header ── -->
<header>
  <div class="header-brand">
    <div>
      <h1>🏫 eSchool Assistant</h1>
      <div class="header-sub">School search for Uganda · powered by eSchool.ug</div>
    </div>
  </div>
  <span class="mode-badge">{{ mode }}</span>
</header>

<!-- ── Search ── -->
<div class="search-section">
  <h2>Describe the school you're looking for</h2>
  <form method="POST" id="searchForm" onsubmit="showSpinner()">
    <div class="search-row">
      <input type="text" name="request" id="requestInput"
             placeholder="e.g. girls boarding school in Kampala, max 1 million per term"
             value="{{ request_text }}" autocomplete="off" required>
      <button type="submit">Search</button>
    </div>
  </form>
  <div class="examples">
    <strong>Try:</strong>
    <a class="ex-link" onclick="fillSearch(this)">secondary schools in Kampala</a>
    <a class="ex-link" onclick="fillSearch(this)">girls boarding school in Wakiso</a>
    <a class="ex-link" onclick="fillSearch(this)">mixed primary in Mukono, max 500,000</a>
    <a class="ex-link" onclick="fillSearch(this)">somewhere affordable near town</a>
  </div>
</div>

<!-- ── Main ── -->
<main>
  <div id="spinner">
    <div class="spin"></div>
    <p style="margin-top:14px;font-size:0.9rem">Searching eSchool…</p>
  </div>

  {% if response %}

    <!-- Clarification -->
    {% if response.status.value == 'needs_clarification' %}
    <div class="clarification">
      <h3>💬 Could you give me a bit more detail?</h3>
      <p>{{ response.criteria.clarifying_question or (notes[0] if notes else "Please provide more details about what you're looking for.") }}</p>
    </div>

    <!-- Error -->
    {% elif response.error %}
    <div class="error-box">
      <h3>⚠ Something went wrong</h3>
      <p>{{ response.error }}</p>
      {% if response.search_url %}
      <p style="margin-top:10px;font-size:0.82rem">
        <a href="{{ response.search_url }}" target="_blank">Try the search directly on eSchool ↗</a>
      </p>
      {% endif %}
    </div>

    <!-- Results -->
    {% else %}

    <!-- Criteria pills -->
    <div class="criteria-card">
      <h3>Interpreted criteria</h3>
      <div class="criteria-pills">
        {% if criteria_items %}
          {% for item in criteria_items %}
            <span class="pill">{{ item }}</span>
          {% endfor %}
        {% else %}
          <span class="no-criteria">No specific criteria found</span>
        {% endif %}
        {% for u in response.criteria.unsupported_criteria %}
          <span class="pill unsupported" title="eSchool cannot filter by this">⚠ {{ u }}</span>
        {% endfor %}
      </div>
    </div>

    <!-- Notes — only shown when there's something genuinely useful to tell the user -->
    {% for note in notes %}
      {% if 'cannot' in note.lower() or 'not applied' in note.lower() or 'no schools' in note.lower() or 'removed' in note.lower() or 'widening' in note.lower() %}
        <div class="note"><span class="note-icon">⚠</span><span>{{ note }}</span></div>
      {% elif 'page' in note.lower() and 'of' in note.lower() %}
        <div class="note info"><span class="note-icon">ℹ</span><span>{{ note }}</span></div>
      {% elif note %}
        <div class="note info"><span class="note-icon">ℹ</span><span>{{ note }}</span></div>
      {% endif %}
    {% endfor %}

    <!-- School list -->
    {% if response.schools %}
    <div class="results-header">
      <h3>
        {{ response.schools|length }} school(s)
        {% if response.total_pages and response.total_pages > 1 %}
          <span style="font-weight:400;color:#718096">— page 1 of {{ response.total_pages }}</span>
        {% endif %}
      </h3>
      {% if response.search_url %}
      <a href="{{ response.search_url }}" target="_blank">View all on eSchool ↗</a>
      {% endif %}
    </div>

    {% for result in response.schools %}
    {% set school = result.school %}
    <div class="school-card">

      <!-- Top row: name + admission badge -->
      <div class="school-top">
        <div class="school-name">
          <a href="{{ school.url }}" target="_blank">{{ school.name }}</a>
        </div>
        {% if school.admission_status %}
          {% if 'closed' in school.admission_status.lower() %}
            <span class="badge badge-closed">{{ school.admission_status }}</span>
          {% else %}
            <span class="badge badge-open">{{ school.admission_status }}</span>
          {% endif %}
        {% endif %}
      </div>

      <!-- Meta row -->
      <div class="school-meta">
        {% if school.level %}
          <span><span class="badge badge-level">{{ school.level }}</span></span>
        {% endif %}
        {% if school.location %}
          <span>📍 {{ school.location }}</span>
        {% endif %}
        {% if school.gender %}
          {% if school.gender == 'girls' %}
            <span><span class="badge badge-gender-girls">👧 Girls</span></span>
          {% elif school.gender == 'boys' %}
            <span><span class="badge badge-gender-boys">👦 Boys</span></span>
          {% else %}
            <span><span class="badge badge-gender-mixed">👫 Mixed</span></span>
          {% endif %}
        {% endif %}
        {% if school.accommodation %}
          <span><span class="badge badge-accommodation">🏠 {{ school.accommodation }}</span></span>
        {% endif %}
        {% if school.fees_available and school.min_fees_per_term %}
          {% if school.min_fees_per_term == school.max_fees_per_term %}
            <span><span class="badge badge-fees">💰 UGX {{ "{:,}".format(school.min_fees_per_term) }}/term</span></span>
          {% else %}
            <span><span class="badge badge-fees">💰 UGX {{ "{:,}".format(school.min_fees_per_term) }}–{{ "{:,}".format(school.max_fees_per_term) }}/term</span></span>
          {% endif %}
        {% endif %}
        {% if school.rating %}
          <span><span class="badge badge-rating">★ {{ school.rating }}</span></span>
        {% endif %}
      </div>

      <!-- Toggle button (mobile only) -->
      {% if result.checks %}
      <button class="toggle-checks" onclick="toggleChecks(this)">Show details ▾</button>

      <!-- Match checks -->
      <div class="checks">
        {% for check in result.checks %}
        <div class="check">
          {% if check.status.value == 'confirmed' %}
            <span class="sym ok">✓</span>
          {% elif check.status.value == 'not_matching' %}
            <span class="sym fail">✗</span>
          {% else %}
            <span class="sym unk">?</span>
          {% endif %}
          <span class="check-text">
            <strong>{{ check.criterion }}</strong> — {{ check.detail }}
          </span>
        </div>
        {% endfor %}
      </div>

      <!-- Verdict -->
      {% if result.is_full_match and result.unknown_count == 0 %}
        <div class="verdict full">✓ Best match — all criteria confirmed</div>
      {% elif result.is_full_match %}
        <div class="verdict partial">✓ Good match · {{ result.unknown_count }} filter(s) unverifiable from card</div>
      {% else %}
        <div class="verdict mismatch">⚠ Partial — some criteria not met</div>
      {% endif %}
      {% endif %}

    </div>
    {% endfor %}

    <!-- Summary -->
    {% set full = response.schools|selectattr('is_full_match')|list|length %}
    {% set partial = response.schools|length - full %}
    <div class="summary-bar">
      <span><strong>{{ full }}</strong> fully matching</span>
      <span><strong>{{ partial }}</strong> with caveats</span>
      {% if response.search_url %}
      <span><a href="{{ response.search_url }}" target="_blank">All results on eSchool ↗</a></span>
      {% endif %}
    </div>

    {% else %}
    <!-- No results -->
    <div class="empty-state">
      <div class="icon">🔍</div>
      <h3>No schools found</h3>
      <p>Try removing some filters — for example, use a broader location or increase the budget.</p>
      {% if response.search_url %}
      <p style="margin-top:14px">
        <a href="{{ response.search_url }}" target="_blank">Search directly on eSchool ↗</a>
      </p>
      {% endif %}
    </div>
    {% endif %}

    {% endif %}

  {% else %}
  <!-- Landing state -->
  <div class="empty-state" style="padding-top:56px">
    <div class="icon">🏫</div>
    <h3>Find the right school in Uganda</h3>
    <p>
      Describe what you're looking for in plain language — location, level,
      budget, boarding, girls or boys — and we'll search eSchool for you.
    </p>
    <p style="margin-top:18px;font-size:0.82rem;color:#a0aec0">
      Live data from <a href="https://eschool.ug" target="_blank">eschool.ug</a>
    </p>
  </div>
  {% endif %}

</main>

<script>
  function fillSearch(el) {
    document.getElementById('requestInput').value = el.textContent.trim();
    document.getElementById('searchForm').submit();
  }
  function showSpinner() {
    document.getElementById('spinner').style.display = 'block';
  }
  function toggleChecks(btn) {
    const card = btn.closest('.school-card');
    const checks = card.querySelector('.checks');
    const open = checks.classList.toggle('open');
    btn.textContent = open ? 'Hide details ▴' : 'Show details ▾';
  }
</script>

</body>
</html>"""


@app.route("/", methods=["GET", "POST"])
def index():
    response = None
    request_text = ""
    notes = []
    criteria_items = []

    if request.method == "POST":
        request_text = request.form.get("request", "").strip()
        if request_text:
            response = search_schools(request_text)
            notes = response.notes or []

            c = response.criteria
            if c.location:
                criteria_items.append(f"📍 {c.location.title()}")
            if c.county:
                criteria_items.append(f"🗺 {c.county.title()}")
            if c.max_fees is not None:
                criteria_items.append(f"💰 Max UGX {c.max_fees:,}")
            if c.min_fees is not None:
                criteria_items.append(f"💰 Min UGX {c.min_fees:,}")
            if c.gender:
                criteria_items.append(f"👥 {c.gender.title()}")
            if c.accommodation:
                criteria_items.append(f"🏠 {c.accommodation}")
            if c.admission_status:
                criteria_items.append(f"📋 Admissions {c.admission_status}")
            if c.levels:
                criteria_items.append(f"🎓 {', '.join(c.levels)}")
            if c.curriculums:
                criteria_items.append(f"📚 {', '.join(c.curriculums)}")
            if c.facilities:
                criteria_items.append(f"🏗 {', '.join(c.facilities)}")
            if c.religions:
                criteria_items.append(f"⛪ {', '.join(c.religions)}")
            if c.query:
                criteria_items.append(f"🔍 '{c.query}'")

    return render_template_string(
        HTML,
        response=response,
        request_text=request_text,
        notes=notes,
        criteria_items=criteria_items,
        mode=_mode_label(),
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
