POLICY DOCKET

From Prototype to Database-Backed System

Backend, schema, and the analysis pipeline behind the click-through mockup — written after five iterations on the front-end prototype, September 2026.

## 1. Why a database, now

The current health-docket repo is entirely file-based: sources.yaml configures what to track, scrapers write meetings.json and briefing.json, and a Jinja2 template renders static HTML for GitHub Pages. That has worked well at the current scale — six tracked bodies, on the order of a few dozen meetings a year — because the relationships have been simple: one body has many meetings, and each meeting has at most one relevance note.

The features built into the prototype over the last several rounds break that shape. A meeting can now belong to more than one legislative subject at once. A subject spans every tier. A “focus area” is itself a saved grouping of policy areas that should be editable without touching code. A document moves through several states — linked, downloaded, extracted, tagged — that need tracking independently of the meeting itself. Those are many-to-many relationships, which JSON files can represent but can’t query: every cross-cut in the mockup (the subject page, the tier snapshot, the sparkline) is currently recomputed by hand in the browser’s JavaScript, against whatever got hardcoded into the page. A relational database does that work once, with an index, and the aggregate becomes a short query instead of a reimplemented loop.

## 2. Architecture overview

Six pipeline stages, each a scheduled job, each writing back to the database. Only the last stage ever talks to a browser.


Fig. 1 — the data-collation pipeline, stage by stage

- Scrape — meeting occurrences. Unchanged from today’s scrapers; they write rows instead of JSON.

- Capture documents — actually download the agenda and minutes files behind each meeting, closing the gap the prototype currently flags with “not yet captured” badges.

- Extract — OCR plus an LLM turn captured files into plain text.

- Tag subjects — an LLM assigns Legislative Subjects to each meeting, with a confidence score, replacing today’s stand-in of reusing NNPH’s coarse admin tags.

- Generate briefings — the “why this matters to NNPH” note, now grounded in real extracted text instead of just a meeting title.

- Serve — an API layer aggregates rows into whatever a given screen needs, on request.

## 3. Database schema

Eleven tables. The taxonomy tables (policy areas, subjects, tiers) are mostly static reference data; the rest track bodies, meetings, documents, and the AI-generated layers on top of them.


Fig. 2 — core schema; boxes are tables, lines are foreign-key relationships

| Table | Purpose | Notable columns |
| --- | --- | --- |
| tiers | Reference table: federal / state / local. | key, label |
| policy_areas | Congress’s 32-bucket taxonomy — static reference data, seeded once from Congress.gov. | name, sort_order |
| legislative_subjects | The tier below policy_areas — Medicaid, Behavioral Health, and so on. | policy_area_id, name |
| bodies | Tracked government bodies — replaces sources.yaml. | tier_id, scraper_type, scraper_config (json) |
| body_admin_tags | NNPH’s own coarse relevance tags per body (budget, hr, it …). | body_id, tag |
| meetings | One row per meeting occurrence. | body_id, occurred_at, status, external_id |
| meeting_documents | Agenda / minutes / exhibit files per meeting, tracked through capture and extraction as separate states. | meeting_id, doc_type, extraction_status |
| meeting_subjects | Many-to-many: which subjects a meeting actually touched. | meeting_id, subject_id, confidence, tagged_by |
| briefings | The “why this matters to NNPH” note. | meeting_id, note_text, confidence, model_version |
| focus_areas | User-defined cross-cutting groupings — replaces the hardcoded FOCUS_AREAS array. | name |
| focus_area_policy_areas | Many-to-many: which policy areas sit inside a focus area. | focus_area_id, policy_area_id |

Two columns are worth calling out because they exist specifically to keep the AI layer honest: tagged_by on meeting_subjects is either ai or human, so a tag you’ve personally confirmed is distinguishable from one nobody’s checked; and model_version on briefings records exactly which prompt/model produced a given note, so a claim can be traced back to how it was generated rather than taken on faith. external_id on meetings (the source system’s own event ID, where one exists) is what makes re-running the scrapers idempotent — an upsert keyed on it instead of appending duplicate rows.

## 4. How the pipeline collates information for analysis

Every summary element in the prototype is a small aggregate query once the schema exists. These are illustrative, not exact syntax:

Gov-snapshot strip (flagged / upcoming / bodies per tier):

SELECT b.tier_id,
  count(*) FILTER (WHERE br.id IS NOT NULL)      AS flagged,
  count(*) FILTER (WHERE m.occurred_at > now())  AS upcoming,
  count(DISTINCT b.id)                           AS bodies
FROM meetings m
JOIN bodies b ON b.id = m.body_id
LEFT JOIN briefings br ON br.meeting_id = m.id
GROUP BY b.tier_id;

Bucket-tile sparkline (monthly meeting counts):

SELECT date_trunc('month', occurred_at) AS month, count(*)
FROM meetings WHERE body_id IN (…)
GROUP BY 1 ORDER BY 1;

Subject cross-tier page (e.g. Medicaid), grouped by tier:

SELECT b.tier_id, m.occurred_at, m.title, br.note_text
FROM meeting_subjects ms
JOIN legislative_subjects s ON s.id = ms.subject_id AND s.name = 'Medicaid'
JOIN meetings m ON m.id = ms.meeting_id
JOIN bodies b ON b.id = m.body_id
LEFT JOIN briefings br ON br.meeting_id = m.id
ORDER BY b.tier_id, m.occurred_at DESC;

At this scale — a handful of bodies, a few hundred meetings a year — these can run live on every page load with an index on occurred_at and body_id. Materialized views or a caching layer would be premature; they’re worth revisiting only if the number of tracked bodies grows by an order of magnitude.

## 5. Backend recommendation

- Database: start with SQLite. Zero operational overhead, a single file, consistent with the project’s current git-repo-as-source-of-truth philosophy. Move to Postgres only if this becomes multi-user or write volume grows meaningfully.

- Framework: Python + FastAPI. The scrapers are already Python, and FastAPI can serve both the JSON API and, paired with Jinja2, the HTML pages themselves — one framework covers both jobs instead of splitting the stack.

- Data access: plain parameterized SQL (sqlite3 / psycopg2) is enough at this schema size; an ORM like SQLAlchemy is a reasonable option but not a requirement.

- Scheduling: keep GitHub Actions cron for the scrape / capture / extract / tag / brief stages — that infrastructure already exists and works.

One real change worth being upfront about: the Serve stage needs a process that’s running continuously to answer API requests, and GitHub Pages only serves static files — it can’t run a backend. That means this design needs somewhere new to live: a small always-on host (Render, Railway, Fly.io, or a cheap VPS), typically in the $5–$10/month range. That’s the first recurring cost this project would take on; everything today is free because it’s 100% static.

## 6. Frontend / UI recommendation

Two structural options. Recommending the simpler one, given this is maintained solo and the existing scrapers are already Python:

A — Server-rendered pages (recommended). FastAPI + Jinja2 render the same three screens already built — Overview, Health, Subject — with the existing vanilla JS handling client-side interaction (tab switches, expand/collapse) against small API endpoints for anything genuinely dynamic. This is the path of least redesign: most of the render() functions already written in the prototype become nearly identical, just fetching from an endpoint instead of reading a hardcoded array.

B — A full single-page app (React) calling a JSON API. More moving parts and more to maintain alone; only worth it if this grows into a multi-person tool with substantially more screens than exist today.

The endpoints that would back exactly what’s already built:

- GET /api/policy-areas — the overview bucket grid, with live per-bucket flagged counts and sparkline data instead of hardcoded values

- GET /api/health/snapshot — the three-tier gov-snapshot strip

- GET /api/health/attention?limit=4 — flagged meetings

- GET /api/health/upcoming — upcoming meetings across tiers

- GET /api/health/bodies?tier=federal — tier panel, past/upcoming split, doc-status per meeting

- GET /api/subjects/{slug} — the cross-tier subject page

- GET/POST /api/focus-areas — focus-area filter config, now editable instead of hardcoded in the page

## 7. What carries over from the prototype

The five rounds of click-through iteration aren’t thrown away — they’re the interaction spec. Nearly every render function in the artifact maps one-to-one to one of the endpoints above; swapping a hardcoded array for a fetch() call is most of the rewrite. The information architecture — Overview → Health → Subject, tier tabs, the past/upcoming split, doc-status badges — doesn’t need to change to support any of this.

## 8. What actually unlocks this, in priority order

- meeting_documents plus the extraction pipeline (stages 2–3). Without this, “minutes” stays a badge that says “not yet captured” forever — this is the one piece that turns the prototype’s honesty flags into real data.

- meeting_subjects tagging (stage 4). Without this, the subject page stays as thin as it is today for Medicaid — one real bullet, two empty tiers.

- Everything else — schema, API, frontend — is comparatively mechanical. The two items above are where the actual open technical questions live: whether Washoe’s Legistar API is reachable, and whether the NELIS scraper’s selectors hold up against the live site.
