# Health Docket

Tracks government meetings related to health & human services — across
Congress, the Nevada Legislature, and Nevada's local health boards — and
serves a live site organized around Congress.gov's 32 Policy Area buckets:
an Overview grid, a per-Policy-Area page (bodies by tier, past/upcoming
meetings, document status), and a cross-tier Legislative Subject
drill-down (e.g. Medicaid). Only Health has real tracked bodies today —
every other bucket is structurally ready and says so plainly rather than
showing a misleading zero.

Live at **https://health-docket-api.onrender.com**.

This is the second rebuild of the project. The first version lived
entirely as a single hand-edited HTML file, refreshed by an AI assistant
rewriting it from scratch each week. A second version replaced that with
JSON files + a Jinja-rendered static page on GitHub Pages — better, but
JSON files have no query engine, so anything cross-cutting (a subject
spanning tiers, a policy-area snapshot) would have had to be hand-assembled
in template logic. This version (Tasks 1–10 of the build plan below) is a
real SQLite database behind a FastAPI backend, with the same three-screen
design served live from that database instead of a static build.

## Project management

`docs/policy-docket-design-spec.md` is the specification of record for
this rebuild — its own revision history says so explicitly, superseding
the earlier draft kept at `docs/policy-docket-system-design.md` for
reference. The rebuild was broken into 10 dependency-ordered tasks across
4 phases, tracked in `pm/Health_Docket_Rebuild_Gantt.xlsx` — all 10 are
now Done.

**Start every session at `pm/STATUS.md`** for the current state and known
issues, and follow the same workflow there for any future change to this
repo (propose a plan, do the work, update the Gantt's Session Log and
STATUS.md before ending, commit). If this README and `pm/STATUS.md` ever
disagree, `pm/STATUS.md` is right — this is a pointer to it, not a copy.

## How it's structured

```
db/schema.sql            eleven-table schema (see design spec §4) —
                          policy_areas, legislative_subjects, bodies,
                          meetings, meeting_documents, meeting_subjects,
                          briefings, focus_areas, tiers, and their joins
db/migrate.py             ONE-TIME bootstrap: builds a fresh database from
                          schema.sql + config/sources.yaml + data/*.json.
                          Only ever run once per database (locally, or on
                          Render's very first boot) -- re-running it drops
                          and rebuilds everything from scratch, which
                          would wipe every document/tag/briefing the
                          pipeline has since produced. Never re-run it
                          against a database that already has real data.
data/meetings.json,      the ORIGINAL seed data db/migrate.py bootstraps
data/briefing.json        a fresh database from -- not live content, and
                          no longer read by anything except migrate.py.
api/                      FastAPI app: JSON API (design spec §6) + the
                          three HTML pages (§7) + POST /api/admin/refresh
api/main.py                assembles the app, mounts /static, routes
api/db.py                  plain parameterized sqlite3 access, no ORM
api/routes/policy_areas.py  GET /api/policy-areas[/...] (5 endpoints,
                            incl. /subjects, a small Task 10 addition)
api/routes/subjects.py      GET /api/subjects/{slug}
api/routes/focus_areas.py   GET+POST /api/focus-areas
api/routes/health.py        GET /api/health (uptime check)
api/routes/admin.py         POST /api/admin/refresh -- runs the capture/
                            extract/tag/brief pipeline stages against the
                            LIVE database; guarded by X-Refresh-Token
api/routes/pages.py          serves the three Jinja2 page shells below
templates/overview.html.j2      Screen 1: the 32-bucket Overview grid
templates/health.html.j2        Screen 2: one Policy Area, every tier
                                 (generically handles any policy area's
                                 slug, not just Health -- named for the
                                 only one with real data today)
templates/subject.html.j2       Screen 3: one Legislative Subject,
                                 cross-tier
static/docket.css, static/docket.js
                          shared styling and fetch()-based rendering --
                          every real value on every page comes from a
                          fetch() call to the JSON API above, nothing is
                          hardcoded (design spec §7, NFR4)
pipeline/capture_documents.py   downloads linked agenda/minutes files
pipeline/extract_text.py        extracts text from captured documents
pipeline/tag_subjects.py        tags a meeting with Legislative Subjects
                                 via Claude, building the taxonomy as it
                                 goes (no predefined subject list exists)
pipeline/generate_briefings.py  writes the "why this matters to NNPH"
                                 relevance note for admin-relevant meetings
config/sources.yaml       the 6 tracked bodies -- what db/migrate.py
                          seeded `bodies` from; edit here, then re-seed a
                          FRESH database (see below) to add a new one
scrapers/                 one Python module per portal *type* (Legistar,
                          NELIS, Congress.gov, SNHD's PDF schedule, ...)
scripts/run_scrapers.py   writes to data/meetings.json -- KNOWN GAP: this
                          was never rewritten to write to the database
                          directly, so it no longer feeds anything live.
                          See "Known limitations" below.
.github/workflows/weekly-refresh.yml
                          calls POST /api/admin/refresh on a schedule so
                          the live database's documents/tags/briefings
                          stay current for meetings already in it
deploy/render.yaml        Render Blueprint: the live service + its disk
```

Nothing in `pipeline/`, `scrapers/`, or `scripts/` ever edits HTML
directly, and nothing in `templates/` ever contains meeting data — the
templates are close to static shells; every real value reaches the page
through a `fetch()` call in `static/docket.js` (NFR4).

## Adding or removing a tracked body

Edit `config/sources.yaml` the same as before (`id`, `name`, `tier`,
`type` matching a `scrapers/` module, whatever fields that scraper needs,
`relevance_tags`). **The honest catch:** `bodies` only gets (re)seeded by
`db/migrate.py`, which rebuilds the ENTIRE database from scratch and would
discard every document, subject tag, and briefing the pipeline has
produced since the last rebuild. Until the scrape stage is rewritten to
upsert into the database directly (see "Known limitations"), adding a
body to a database that already has real pipeline data means adding the
`bodies`/`meetings` rows by hand (a short `INSERT` against
`db/health_docket.db` — or, on Render, the disk-backed one) rather than
re-running migrate.py.

## Running it

**Locally**, once dependencies are installed (`pip install -r
requirements.txt`):

```
python3 db/migrate.py                  # ONCE, only for a database that doesn't exist yet
uvicorn api.main:app --reload
```

Then open `http://127.0.0.1:8000/` for the site, or
`http://127.0.0.1:8000/docs` for the interactive API docs. To run a
pipeline stage by hand against your local database:

```
python3 pipeline/capture_documents.py
python3 pipeline/extract_text.py
python3 pipeline/tag_subjects.py          # needs ANTHROPIC_API_KEY set
python3 pipeline/generate_briefings.py    # needs ANTHROPIC_API_KEY set
```

Each of these only processes meetings/documents that need it unless you
pass `--force`, so they're safe to re-run.

**In production**, the live service is a single Render web service
(`deploy/render.yaml`) serving both the site and the API from
`db/health_docket.db` on a persistent disk. `.github/workflows/weekly-refresh.yml`
calls `POST /api/admin/refresh` on that live service every Monday, which
runs the four pipeline scripts above in-process against the live
database. Two secrets are required, entered directly wherever they're
used (never through an AI assistant — see `pm/STATUS.md` for why this
matters):

- On **Render** (Dashboard → the service → Environment): `ANTHROPIC_API_KEY`
  (from console.anthropic.com) and `REFRESH_TOKEN` (any random string you
  generate yourself, e.g. `openssl rand -hex 32`).
- On **GitHub** (repo Settings → Secrets and variables → Actions): a
  `REFRESH_TOKEN` secret with the *identical* value you set on Render.

## Known limitations, honestly

- **New meetings don't reach the live database automatically.** The
  "Scrape" pipeline stage (design spec §5.1) was never rewritten to write
  `meetings`/`bodies` rows to the database directly — `scripts/run_scrapers.py`
  still only writes to `data/meetings.json`, a file nothing live reads
  anymore. The only path from that JSON into the database is
  `db/migrate.py`, and it's a destructive full rebuild, not a safe
  incremental upsert. Until that gap is closed, new meetings need to be
  added to the live database by hand. `POST /api/admin/refresh` (and the
  weekly GitHub Actions run) only cover the four stages downstream of
  that — capture, extract, tag, brief — which are all genuinely safe to
  re-run.
- **The NELIS scraper (Nevada Legislature) is the least tested** —
  client-side rendered pages, Playwright-based, selectors written from
  manual inspection rather than a documented API.
- **Legistar API access (`webapi.legistar.com`) is unconfirmed** —
  `scrapers/legistar.py` has the code to use it, but every attempt to
  reach it (from this environment and from a Mac on a different network)
  returned a 403 from an intermediate network proxy before reaching
  Legistar itself. Needs testing from an unrestricted network.
- **SNHD's schedule PDF changes structure year to year** — the parser in
  `scrapers/snhd.py` handles the 2026 format; expect to revisit around
  when the 2027 schedule is published.
- **OCR isn't implemented** — `pipeline/extract_text.py` reads real text
  layers (via `pdfplumber`) but has no fallback for a scanned/image-only
  PDF; one hasn't shown up in the tracked corpus yet.
- **The Overview page's "not yet tracked" check and global attention
  strip both fan out into several small API calls per page load** (one
  `/bodies` lookup per policy area, one `/attention` lookup per flagged
  area) rather than the API exposing that directly. Fine at this
  project's scale (32 policy areas, a handful of bodies); worth folding
  into `GET /api/policy-areas` itself if this ever needs to be faster.
- Only Health has tracked bodies today (Appendix C of the design spec);
  expanding to other Policy Areas is a content/sourcing effort, out of
  scope for the engineering work described here.

## Data model

See `docs/policy-docket-design-spec.md` §4 for the full eleven-table
schema and §6 for the complete API specification (7 original endpoints +
the `/subjects` and `/admin/refresh` additions from Task 10).
