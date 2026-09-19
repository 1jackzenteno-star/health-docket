POLICY DOCKET

System Design Specification

A database-backed rebuild of the government-meeting tracker for NNPH — requirements, architecture, data model, API, build plan, and open risks.

|  |  |
| --- | --- |
| Status | Draft for review — v1.0 |
| Prepared for | Jack Zenteno, Northern Nevada Public Health (NNPH) |
| Prepared with | Claude (Sonnet 5) |
| Date | September 19, 2026 |
| Repository | github.com/1jackzenteno-star/health-docket |
| Supersedes | Sections 1–9 of the prior working note “Policy Docket: From Prototype to Database-Backed System” (Sept 19, 2026), consolidated and expanded here |
| Reference only, not spec of record | Three interactive HTML mockups built during design exploration: “Policy Docket,” “Docket Build Map,” and “Screen to Source.” See §3.4. |


### Revision history

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | Sept 19, 2026 | Initial backend/schema note: architecture overview, 11-table schema, aggregation queries, backend/frontend recommendation, build-order Gantt chart. |
| 1.0 | Sept 19, 2026 | Expanded into a full specification: requirements, UX/IA spec, expanded data model and API detail, operational considerations, risks, glossary and appendix. Declared as the specification of record in place of the interactive mockups. |

### Contents

- 1. Purpose & Background

- 2. Requirements

- 3. Information Architecture & UX Specification

- 4. Data Model

- 5. System Architecture

- 6. API Specification

- 7. Frontend Implementation Approach

- 8. Build Plan

- 9. Operational Considerations

- 10. Risks & Open Questions

- 11. Appendix — Glossary, Policy Area Taxonomy, Tracked Bodies


## 1. Purpose & Background

### 1.1 Problem statement

NNPH staff need to know, without hunting across six different government websites, what federal, state, and local bodies are discussing that could affect the department — budget actions, Medicaid policy, board-authority changes, grant conditions — and whether a meeting is one NNPH's own board needs to act on. That need started as a single question: could a dashboard show, at a glance, what's relevant before anyone clicks through? Five rounds of interactive prototyping answered the interaction-design half of that question. This document answers the other half: what has to exist underneath the screen for the dashboard to run on real, current, trustworthy data instead of a hand-built mockup.

### 1.2 Current state

The health-docket repository is a working, deployed system today, not a concept. It is entirely file-based: config/sources.yaml declares which six bodies to track and how to scrape each; per-body scrapers in scrapers/ (Legistar, NELIS, Congress.gov, SNHD, and a generic HTML fallback) write results to data/meetings.json; scripts/generate_briefing.py produces data/briefing.json; scripts/render_site.py renders a Jinja2 template to static HTML; and a weekly GitHub Actions workflow re-runs the whole chain and publishes the result to GitHub Pages. The project's own README states its guiding separation: nothing in scripts/ or scrapers/ ever edits HTML directly, and nothing in templates/ ever contains meeting data. That separation is preserved, not discarded, by everything in this document.

This has worked because the relationships involved have been simple — one body has many meetings, each meeting has at most one relevance note. It has real limits: agenda and minutes documents are linked but never actually downloaded or read; there is no concept of a meeting touching more than one subject; and every cross-cutting view (a tier snapshot, a subject drill-down) would have to be hand-assembled in template logic rather than queried, because JSON files have no query engine.

### 1.3 Goals

- Extend the current single-topic (Health) tracker to all 32 of Congress.gov's Policy Area buckets, without re-architecting for each new one.

- Let a meeting be tagged with more than one Legislative Subject, and let a subject (e.g. Medicaid) be viewed across all three tiers at once, aligned to each body's next meeting date.

- Turn agenda/minutes links into actually-captured, actually-read documents, so a meeting's relevance can be judged from its real content rather than its title alone.

- Keep every AI-generated claim (a relevance note, a subject tag) traceable to what produced it, never presented as unattributed fact.

- Keep the system operable by one person, part-time, at a cost NNPH can carry indefinitely without budget approval.

### 1.4 Non-goals

- Not a public-facing product for other health districts or the general public — NNPH's own dashboard, first.

- Not multi-tenant and not a system with user accounts or logins beyond Jack's own operational access to the backend.

- Not real-time — a weekly-to-daily refresh cadence, consistent with how often these bodies actually meet, is sufficient.

- Does not track or store any personal data about meeting attendees or the public — the source material is public government record (agendas, minutes, hearing notices).

- Does not replace legal or compliance review — briefings are a starting point for attention, not a substitute for reading the source document on anything that matters.


## 2. Requirements

Functional requirements are written against what the prototype already demonstrates on screen; each maps to a specific round of the interactive mockups built during design exploration. Non-functional requirements come from constraints Jack has stated directly — solo maintenance, a hard cost ceiling, and a standing insistence that AI-generated claims be traceable rather than asserted.

### 2.1 Functional requirements

FR1  The system shall present all 32 Policy Area buckets as an overview grid, each showing a live count of flagged meetings and a recent-activity sparkline once tagging exists for that bucket. Buckets with no tracked bodies yet shall say so plainly rather than show a zero that looks like “nothing happening.”

FR2  Within a policy-area page, bodies shall be organized by tier — federal, state, local — matching the six bodies tracked today and extensible to more without a schema change.

FR3  Each policy-area page shall show a cross-tier snapshot strip: flagged-meeting count, upcoming-meeting count, and body count, per tier.

FR4  Each body's panel shall split meetings into past and upcoming, sorted by date, with past meetings showing what's actually known and upcoming meetings showing the next scheduled date.

FR5  Each meeting shall show a document status for its agenda and minutes independently — not linked, linked, captured, or extracted — and the system shall never display a fabricated summary for a document that has not been extracted.

FR6  Each flagged meeting shall carry a short relevance note (“briefing”) explaining why it matters to NNPH's admin functions, generated from the meeting's actual extracted content once available.

FR7  The system shall support a cross-tier subject drill-down: selecting a Legislative Subject (e.g. Medicaid) shall show what's being discussed about it at every tier, aligned to each relevant body's next meeting date.

FR8  The system shall support user-defined “focus areas” — saved, named groupings of Policy Areas — editable without a code change, surfaced as a filter on the overview grid.

### 2.2 Non-functional requirements

NFR1  Solo-maintainable. One person, part-time, must be able to run and extend the system without a team, a dedicated ops role, or specialized infrastructure knowledge beyond what's already in use (Python, GitHub Actions, SQL).

NFR2  Cost ceiling. New recurring infrastructure cost should stay in the $5–$15/month band (see §9.3 for the estimate) unless Jack explicitly approves more. Today's system costs $0/month because GitHub Pages is static.

NFR3  AI-claim traceability. Every AI-generated field shall carry enough metadata — at minimum, which model produced it and when — that a claim can be checked against its source rather than trusted on faith; a tag confirmed by a human shall be distinguishable from one no one has reviewed.

NFR4  Architectural separation. Pipeline code shall never write HTML directly; template/rendering code shall never contain meeting data directly — carried forward unchanged from the current repo's stated philosophy.

NFR5  Public-data-only scope. The system shall store only public government meeting record — no personal data, no accounts beyond Jack's own operational access, no data requiring privacy handling beyond “this is a public record.”


## 3. Information Architecture & UX Specification

This section formalizes what the interactive mockups demonstrated by example into a specification that doesn't depend on the mockups still existing or being read in a particular order.

### 3.1 Screen inventory

| Screen | Purpose | Primary elements |
| --- | --- | --- |
| Overview | At-a-glance entry point across all 32 Policy Areas. | 32-bucket grid with flagged count + sparkline per bucket<br>Focus-area filter chips (FR8)<br>Global attention strip: most urgent flagged meetings across all areas |
| Policy Area (e.g. Health) | Everything tracked within one Policy Area, organized by tier. | Cross-tier snapshot strip (FR3)<br>Tier tabs (federal / state / local)<br>Per-body panel: past/upcoming split, doc-status badges (FR4, FR5) |
| Subject drill-down (e.g. Medicaid) | One Legislative Subject, traced across every tier at once. | Cross-tier bullet summary aligned to next-meeting dates (FR7)<br>Links back to the source meeting in its tier panel |

### 3.2 Navigation model

Three screens, one-directional drill-down: Overview → Policy Area → Subject, with breadcrumbs back up at every level (the prototype's goto()/renderCrumbs() pattern). A subject is only reachable from a Policy Area page, never linked directly from Overview, because a subject only makes sense in the context of the area it belongs to. There is no separate “body” screen — a body's meetings live inside its tier panel on the Policy Area page, not as their own destination.

### 3.3 Empty & pending states

Every piece of AI-derived or pipeline-dependent content has an explicit not-yet-available state, and the system must show that state rather than omit the element or fake a plausible-looking value. This was a deliberate discipline built into every round of the interactive prototype and is now a requirement, not a style choice.

| Element | States, in order | Rule |
| --- | --- | --- |
| Document status (agenda / minutes) | not linked<br>linked<br>captured<br>extraction pending<br>extracted | Never show a summary before “extracted.” |
| Subject tag on a meeting | untagged<br>ai-tagged (confidence shown)<br>human-confirmed | tagged_by distinguishes the last two (§4). |
| Briefing / relevance note | none yet<br>generated (model + date shown) | Never shown without its model_version. |
| Policy-area bucket with no tracked body | “not yet tracked” label, zero suppressed | A true zero and “nothing tracked” must look different. |

### 3.4 Relationship to the interactive mockups

Three HTML artifacts were built during design exploration and remain useful as interaction references, but none of them is the specification going forward — this document is:

- “Policy Docket” — the click-through mockup of the three screens above, built across five iterations (bucket grid → cross-tier snapshot → past/upcoming split → subject drill-down). Reference for exact layout and interaction feel.

- “Docket Build Map” — a Gantt chart, target folder structure, and navigation guide for the build itself. Superseded by §8 of this document, which carries the same task list forward with more detail.

- “Screen to Source” — a single worked example (the June 25 House E&C meeting) traced from the GUI through an API response, a SQL query, database rows, and back to the pipeline stage that produced each layer, each marked real-today or planned. Reference for how §4–§6 of this document connect to what's on screen.

Where a mockup and this document disagree, this document governs — the mockups were built to explore interaction design against real repo data, not to enumerate every requirement or edge case, and several of the states in §3.3 were formalized after the mockups were built.


## 4. Data Model

Eleven tables. The taxonomy tables (policy areas, subjects, tiers) are mostly static reference data seeded once; the rest track bodies, meetings, documents, and the AI-generated layers on top of them.


Fig. 1 — core schema; boxes are tables, lines are foreign-key relationships

| Table | Purpose | Notable columns |
| --- | --- | --- |
| tiers | Reference table: federal / state / local. | key, label |
| policy_areas | Congress's 32-bucket taxonomy — static reference data, seeded once from Congress.gov. Full list in Appendix B. | name, sort_order |
| legislative_subjects | The tier below policy_areas — Medicaid, Behavioral Health, and so on. | policy_area_id, name |
| bodies | Tracked government bodies — replaces sources.yaml. Full list of the 6 tracked today in Appendix C. | tier_id, scraper_type, scraper_config (json) |
| body_admin_tags | NNPH's own coarse relevance tags per body (budget, hr, it …), carried forward from sources.yaml's relevance_tags. | body_id, tag |
| meetings | One row per meeting occurrence. | body_id, occurred_at, status, external_id |
| meeting_documents | Agenda / minutes / exhibit files per meeting, tracked through capture and extraction as separate states (§3.3). | meeting_id, doc_type, extraction_status |
| meeting_subjects | Many-to-many: which subjects a meeting actually touched. | meeting_id, subject_id, confidence, tagged_by |
| briefings | The relevance note (FR6). | meeting_id, note_text, confidence, model_version |
| focus_areas | User-defined cross-cutting groupings (FR8) — replaces the hardcoded FOCUS_AREAS array in the prototype. | name |
| focus_area_policy_areas | Many-to-many: which policy areas sit inside a focus area. | focus_area_id, policy_area_id |

Two columns exist specifically to satisfy NFR3 (AI-claim traceability): tagged_by on meeting_subjects is either ai or human, so a confirmed tag is distinguishable from an unreviewed one; and model_version on briefings records exactly which model/prompt produced a given note. external_id on meetings (the source system's own event ID, where one exists) is what makes re-running the scrapers idempotent — an upsert keyed on it instead of appending duplicate rows on every refresh.

### 4.1 Column-level detail — the four tables everything else depends on

#### bodies

| Column | Type | Notes |
| --- | --- | --- |
| id | integer, PK | Surrogate key. |
| slug | text, unique | Stable identifier, e.g. nnph-dboh — matches today's sources.yaml id. |
| name | text | Display name. |
| tier_id | FK → tiers | federal / state / local. |
| scraper_type | text | One of the existing scraper modules: congress_api, nelis, legistar, snhd_schedule, generic_html. |
| scraper_config | json | Whatever that scraper needs — committee_system_code, legistar_client, etc. — replaces the per-source extra keys in sources.yaml. |
| watch_url | text | Human-facing link to the body's own meeting page. |
| active | boolean | Lets a body be paused without deleting its history. |

#### meetings

| Column | Type | Notes |
| --- | --- | --- |
| id | integer, PK | Surrogate key. |
| body_id | FK → bodies |  |
| external_id | text, nullable | Source system's own event ID where one exists — the idempotency key for upserts. |
| title | text |  |
| occurred_at | timestamp | Indexed — nearly every query in §6 filters or sorts on this. |
| status | text | scheduled / occurred / cancelled. |
| source_url | text | Link to the meeting's page on the source site. |

#### meeting_documents

| Column | Type | Notes |
| --- | --- | --- |
| id | integer, PK | Surrogate key. |
| meeting_id | FK → meetings |  |
| doc_type | text | agenda / minutes / exhibit. |
| source_file_url | text, nullable | Where the file lives on the source site; null until linked. |
| capture_status | text | not_linked / linked / captured — see §3.3. |
| extraction_status | text | pending / extracted / failed — see §3.3. |
| extracted_text | text, nullable | OCR + LLM output; null until extraction_status = extracted. |

#### meeting_subjects

| Column | Type | Notes |
| --- | --- | --- |
| meeting_id | FK → meetings | Composite PK with subject_id. |
| subject_id | FK → legislative_subjects |  |
| confidence | real, 0–1 | Model's own confidence, null for human-confirmed rows. |
| tagged_by | text | ai / human — see NFR3. |
| tagged_at | timestamp |  |


## 5. System Architecture

Six pipeline stages, each a scheduled job, each writing back to the database. Only the last stage ever talks to a browser — the same separation the current repo already enforces between scrapers, scripts, and templates (§1.2), extended one stage further.


Fig. 2 — the data-collation pipeline, stage by stage

| Stage | Input | Output | Failure handling |
| --- | --- | --- | --- |
| Scrape | sources config (bodies table) | meetings rows (upserted on external_id) | Per-scraper try/catch; a failed source is skipped and logged, not allowed to fail the whole run (§9.1). |
| Capture documents | meeting_documents rows with a source_file_url | Files downloaded to storage; capture_status updated | A 404 or auth wall sets capture_status back to not_linked with a logged reason rather than retrying forever. |
| Extract | Captured files | extracted_text; extraction_status updated | OCR/LLM failure sets extraction_status = failed and leaves the prior state's UI badge in place — never a blank guess. |
| Tag subjects | extracted_text | meeting_subjects rows, tagged_by = ai | Below-threshold confidence is stored, not discarded — surfaced, not hidden, so a human can review it. |
| Generate briefings | extracted_text + meeting_subjects | briefings rows with model_version | Same pattern: a low-confidence or failed generation is a visible state, not a silent skip. |
| Serve | All of the above, via SQL | JSON to the frontend, on request | Standard API error responses (§6); this is the only stage that runs continuously rather than on a schedule. |

### 5.1 Backend recommendation

- Database: start with SQLite. Zero operational overhead, a single file, consistent with the project's current git-repo-as-source-of-truth philosophy. Move to Postgres only if this becomes multi-user or write volume grows meaningfully.

- Framework: Python + FastAPI. The scrapers are already Python, and FastAPI can serve both the JSON API and, paired with Jinja2, the HTML pages themselves — one framework covers both jobs instead of splitting the stack.

- Data access: plain parameterized SQL (sqlite3 / psycopg2) is enough at this schema size; an ORM like SQLAlchemy is a reasonable option but not a requirement.

- Scheduling: keep GitHub Actions cron for the scrape / capture / extract / tag / brief stages — that infrastructure already exists and works.

One real change worth being upfront about: the Serve stage needs a process running continuously to answer API requests, and GitHub Pages only serves static files — it cannot run a backend. That means this design needs somewhere new to live: a small always-on host (Render, Railway, Fly.io, or a cheap VPS), typically $5–$10/month. That is the first recurring cost this project would take on; everything today is free because it is 100% static.


## 6. API Specification

Endpoints map one-to-one to the screens in §3.1 and the render functions already written in the prototype — swapping a hardcoded array for a fetch() call is most of the frontend rewrite (§7).

| Endpoint | Purpose | Key params | Errors |
| --- | --- | --- | --- |
| GET /api/policy-areas | Overview grid: all 32 buckets with live flagged counts + sparkline data (FR1). | focus_area (optional, FR8) | 200 only — empty buckets return zero-state, not an error. |
| GET /api/policy-areas/{slug}/snapshot | Cross-tier snapshot strip for one Policy Area (FR3). | slug | 404 unknown slug |
| GET /api/policy-areas/{slug}/attention | Flagged meetings for one Policy Area, most urgent first. | slug, limit | 404 unknown slug |
| GET /api/policy-areas/{slug}/bodies | Tier panels: bodies, past/upcoming meetings, doc-status (FR2, FR4, FR5). | slug, tier (optional) | 404 unknown slug |
| GET /api/subjects/{slug} | Cross-tier subject drill-down page (FR7). | slug | 404 unknown slug |
| GET /api/focus-areas | List saved focus-area groupings (FR8). | — | — |
| POST /api/focus-areas | Create/edit a focus area — the one write endpoint the frontend needs. | name, policy_area_ids[] | 400 invalid policy_area_ids |

All read endpoints return JSON with a consistent envelope: {data, generated_at}. generated_at lets the frontend show “as of” timestamps honestly rather than implying live data where the underlying pipeline only refreshes weekly. Every field derived from an AI stage (a briefing note, a subject tag's confidence) is nested under its own model_version key rather than flattened, so the frontend can always show its provenance per NFR3.


## 7. Frontend Implementation Approach

A — Server-rendered pages (recommended). FastAPI + Jinja2 render the same three screens already built (§3.1) with the existing vanilla JS handling client-side interaction (tab switches, expand/collapse) against the small API endpoints above for anything genuinely dynamic. This is the path of least redesign: most of the render() functions already written in the prototype become nearly identical, just fetching from an endpoint instead of reading a hardcoded array — consistent with NFR1 (solo-maintainable).

B — A full single-page app (React) calling a JSON API. More moving parts and more to maintain alone; only worth it if this grows into a multi-person tool with substantially more screens than exist today. Not recommended under current constraints.

What carries over directly from the prototype: the information architecture (Overview → Policy Area → Subject), the tier tabs, the past/upcoming split, and the doc-status badge system — none of it needs to change to support any of the above; it only needs a real data source underneath it.


## 8. Build Plan

Ten tasks in four phases, ordered by dependency rather than a fixed calendar. Two tracks run in parallel throughout: the data pipeline and the backend/frontend both only need the schema to exist, so neither has to wait on the other.


Fig. 3 — build order and rough dependency-driven pacing

| # | Task | Phase | Depends on |
| --- | --- | --- | --- |
| 1 | Design & migrate schema (§4) | Foundation | — |
| 2 | Verify Legistar API access (nnph-dboh) | Foundation | — |
| 3 | Harden NELIS scraper selectors | Foundation | — |
| 4 | Provision hosting | Foundation | — |
| 5 | Backend API (§6) | Backend/Frontend | 1 |
| 6 | Document capture pipeline | Data pipeline | 1, 2, 3 |
| 7 | Extraction (OCR + LLM) | Data pipeline | 6 |
| 8 | Subject tagging (LLM) | Data pipeline | 7 |
| 9 | Briefing generation upgrade | Data pipeline | 8 |
| 10 | Frontend cutover to live API | Launch | 5, 9, 4 |

Reading it:

- Schema and access verification (Legistar API, NELIS selectors) come first — everything else depends on knowing the schema shape and whether the two riskiest scrapers actually work.

- Backend API and the document-capture pipeline can start the moment the schema exists and run side by side — neither blocks the other.

- Extraction, subject tagging, and the briefing upgrade are a strict chain — each needs real output from the one before it, which is why they're staggered rather than parallel.

- Hosting setup is deliberately early and short — pure infrastructure provisioning, worth having ready well before anything needs to deploy to it.

- Cutover is last and depends on everything: the frontend, the briefing pipeline, and a place to host it.

The day counts in Fig. 3 are a pacing illustration, not a schedule — they assume roughly one working track of solo, part-time effort. The order (what has to finish before what can start) is the part worth trusting; the durations are worth replacing with real ones once actual weekly hours are known.


## 9. Operational Considerations

### 9.1 Monitoring for silent failures

A scraper that starts returning zero results — because a source site changed its markup, moved a URL, or started blocking automated requests — is the single most likely failure mode, and the most dangerous one precisely because it fails quietly: the dashboard just shows less, and nothing announces that anything is wrong. The scheduled job for each stage should compare its own output count against a short trailing baseline (e.g. the last 4 runs) and flag — not fail the whole run — any source that dropped to zero or fell sharply below that baseline. A single weekly digest (even just an email or a GitHub Issue opened automatically) is enough at this scale; a dedicated monitoring service is not warranted.

### 9.2 Data quality & idempotency

Every scrape re-run upserts on external_id (§4) rather than appending, so re-running a stage is always safe and never produces duplicate meetings. Sources without a stable external ID (the generic_html scraper, notably) should upsert on a computed key — body_id plus a normalized title and date — accepting that this is weaker and occasionally may create a near-duplicate; that's a known, bounded limitation rather than a silent one.

### 9.3 Rough cost estimate

| Item | Estimate | Notes |
| --- | --- | --- |
| Hosting (Serve stage, always-on) | $5–$10/mo | Render, Railway, Fly.io, or a cheap VPS — see §5.1. |
| LLM calls (extraction + tagging + briefings) | Low, usage-based | A few dozen meetings a month across 6 bodies; cost scales with how many Policy Areas get built out beyond Health. |
| Everything else (scraping, storage, GitHub Actions) | $0 | Stays within GitHub's free tier at this volume. |

This is a rough order of magnitude, not a quote — flagged explicitly as an estimate rather than a commitment, consistent with the traceability discipline this whole document applies to AI-generated claims (NFR3): treat it as a planning input to revisit once real usage is measured, not a number to hold anyone to.

### 9.4 Security & privacy

Every piece of data this system stores is public government meeting record — agendas, minutes, hearing schedules — already published by the source bodies themselves. There is no personal data about meeting attendees, no accounts or logins beyond Jack's own operational access to the backend and hosting, and no payment, health, or otherwise sensitive information of any kind in scope (NFR5). The one thing worth protecting operationally is the hosting and repository credentials themselves — standard practice (a password manager, no secrets committed to the repo) is sufficient; no additional privacy program is required for data of this kind.


## 10. Risks & Open Questions

| Risk | Detail | Status |
| --- | --- | --- |
| Legistar API access unconfirmed | legistar.py already contains code to extract EventAgendaFile/EventMinutesFile fields from webapi.legistar.com, but it has never been exercised against live data. Two attempts to test it directly — one from the cloud workspace, one from Jack's own Mac — both returned HTTP 403 from the network proxy before ever reaching Legistar's server. | This is an org-level network/domain-allowlist block on both sides tested so far, not a finding about Legistar itself. Needs testing from a network without that restriction before Task 2 can be marked done. |
| NELIS selectors unverified | nelis.py uses Playwright because the Nevada Legislature's site is JS-rendered; its own docstring marks the CSS selectors as unverified against the live site. | Open — Task 3 in the build plan. |
| LLM tagging accuracy & cost unproven | Subject tagging (stage 4) and briefing generation (stage 5) have not been run against real extracted meeting text yet, so both the accuracy of the tags and the real per-meeting cost are estimates, not measurements. | Open — first real signal arrives once Tasks 6–8 produce real extracted text to tag. |
| Scope risk beyond Health | Only the Health Policy Area has real tracked bodies today; the other 31 buckets in the overview grid are structurally supported but empty. Expanding coverage is a content/sourcing effort (finding and configuring new bodies), separate from and larger than the engineering work in this document. | Explicitly out of scope for this build — noted so it isn't assumed to be included. |


## 11. Appendix

### A. Glossary

| Term | Definition |
| --- | --- |
| Policy Area | One of Congress.gov's 32 standard subject-matter buckets (e.g. Health, Education). The top level of the overview grid. |
| Legislative Subject | A finer-grained topic beneath a Policy Area (e.g. Medicaid, Behavioral Health, within Health). |
| Tier | Federal, State, or Local — the level of government a tracked body sits at. |
| Body | A specific tracked government entity — a committee, board, or commission (e.g. Washoe County District Board of Health). |
| Meeting | One occurrence of a body convening, past or scheduled. |
| Briefing | The short, AI-generated “why this matters to NNPH” note attached to a flagged meeting. |
| Focus Area | A user-defined, named grouping of Policy Areas, used as an overview filter (FR8). |
| tagged_by | Column on meeting_subjects distinguishing an AI-assigned tag from a human-confirmed one. |
| external_id | The source system's own event ID for a meeting, used as the upsert key for idempotent re-scraping. |

### B. Policy Area taxonomy (32, from Congress.gov)

| 1. Agriculture and Food | 17. Government Operations and Politics |
| --- | --- |
| 2. Animals | 18. Health |
| 3. Armed Forces and National Security | 19. Housing and Community Development |
| 4. Arts, Culture, Religion | 20. Immigration |
| 5. Civil Rights and Liberties, Minority Issues | 21. International Affairs |
| 6. Commerce | 22. Labor and Employment |
| 7. Congress | 23. Law |
| 8. Crime and Law Enforcement | 24. Native Americans |
| 9. Economics and Public Finance | 25. Public Lands and Natural Resources |
| 10. Education | 26. Science, Technology, Communications |
| 11. Emergency Management | 27. Social Sciences and History |
| 12. Energy | 28. Social Welfare |
| 13. Environmental Protection | 29. Sports and Recreation |
| 14. Families | 30. Taxation |
| 15. Finance and Financial Sector | 31. Transportation and Public Works |
| 16. Foreign Trade and International Finance | 32. Water Resources Development |

Health (highlighted) is the only Policy Area with tracked bodies today.

### C. Currently tracked bodies (6, from config/sources.yaml)

| id | Name | Tier | Scraper type | Relevance tags |
| --- | --- | --- | --- | --- |
| senate-help | Senate HELP Committee | Federal | congress_api | budget, grants, workforce, hhs-policy |
| house-ec-health | House Energy & Commerce — Health Subcommittee | Federal | congress_api | medicaid, compliance, budget, hhs-policy |
| nv-jisc-hhs | NV Joint Interim Standing Committee on Health & Human Services | State | nelis | legislation, funding, workforce, board-authority |
| nnph-dboh | Washoe County District Board of Health (NNPH) | Local | legistar | budget, hr, contracts, own-board |
| snhd-boh | Southern Nevada Health District Board of Health | Local | snhd_schedule | peer-district |
| carson-boh | Carson City Board of Health | Local | generic_html | peer-district |
