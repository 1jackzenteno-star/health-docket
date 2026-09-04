# Health Docket

Tracks government meetings related to health & human services — across
Congress, the Nevada Legislature, and Nevada's local health boards — and
publishes a dashboard (calendar + an "Impact Briefing" for NNPH's admin
functions) that refreshes on its own every week.

This replaces an earlier version of the project that lived entirely as a
single hand-edited HTML file, refreshed by an AI assistant rewriting it from
scratch each week. That worked but didn't scale: no diff history, no way to
add a tracked body without editing code, and the "research" step depended on
generic fetch-and-summarize calls against sites that don't summarize well
(PDFs, JS-rendered calendars). This version fixes all three.

## How it's structured

```
config/sources.yaml     the list of tracked bodies — THIS is what you edit
                         to add or remove a focus area
data/meetings.json       structured meeting records — the single source of
                         truth, tracked in git so every change has a diff
data/briefing.json       "why this matters to NNPH" notes, one per meeting,
                         written by Claude via the Anthropic API
scrapers/                one Python module per portal *type* (Legistar,
                         NELIS, Congress.gov, SNHD's PDF schedule, ...)
scripts/run_scrapers.py  reads sources.yaml, runs the right scraper for each
                         source, upserts results into meetings.json
scripts/generate_briefing.py
                         finds meetings without a briefing note yet, asks
                         Claude for one, writes briefing.json
scripts/render_site.py   renders templates/dashboard.html.j2 from the two
                         JSON files into site/index.html — this is the only
                         thing that touches the page's HTML/CSS/JS
templates/dashboard.html.j2
                         the calendar + tabs UI (same design as the
                         Cowork Artifact version), now templated instead of
                         hand-edited
.github/workflows/weekly-refresh.yml
                         runs the three scripts above on a schedule, commits
                         the results, and publishes site/ to GitHub Pages
```

Nothing in `scripts/` or `scrapers/` ever edits HTML directly, and nothing
in `templates/` ever contains meeting data. That split is what makes this
durable: the data has a real history, and the page is always a deterministic
build artifact of that data.

## Adding or removing a focus area

Edit `config/sources.yaml`. Each entry needs an `id`, `name`, `tier`
(`federal` / `state` / `local`), a `type` matching one of the scrapers in
`scrapers/`, whatever fields that scraper type needs, and `relevance_tags`
(used both for display and to steer the briefing prompt). No other file
needs to change for a source whose `type` already has a scraper.

Adding a genuinely new *kind* of source (a portal type not yet supported)
means writing a new `scrapers/<type>.py` with a `scrape(source_cfg) ->
list[Meeting]` function — see `scrapers/base.py` for the `Meeting` shape —
and registering it in `scripts/run_scrapers.py`'s `SCRAPER_REGISTRY`.

## Running it

**Locally**, once dependencies are installed (`pip install -r
requirements.txt`; `playwright install chromium` if you'll run the NELIS
scraper):

```
python scripts/run_scrapers.py
python scripts/generate_briefing.py   # needs ANTHROPIC_API_KEY set
python scripts/render_site.py
```

Each step reads/writes the JSON files in `data/`, so you can run them
independently, inspect the diff (`git diff data/`), and only commit once
it looks right.

**On GitHub Actions**, `.github/workflows/weekly-refresh.yml` runs all
three every Monday, commits the changes, and deploys `site/` to GitHub
Pages. You need two repo secrets:

- `ANTHROPIC_API_KEY` — from console.anthropic.com, for the briefing notes.
- `CONGRESS_API_KEY` — a free key from https://api.congress.gov/sign-up,
  for the federal-tier scraper (Congress.gov's official API — scraping
  congress.gov's HTML directly isn't done here since their robots.txt
  disallows it).

Enable GitHub Pages for the repo (Settings → Pages → Source: GitHub
Actions) after the first successful run.

## Known limitations, honestly

- **The NELIS scraper (Nevada Legislature) is the least tested.** Their
  meeting pages render client-side, so `scrapers/nelis.py` uses Playwright
  (a real headless browser) rather than a plain HTTP request. This is the
  scraper most likely to need adjustment on its first real run — NELIS's
  page structure isn't documented anywhere, so the selectors here were
  written from manual inspection, not a spec.
- **None of the scrapers were execution-tested against the live sites from
  the environment that built this repo** — that sandbox's network is
  allowlisted to a small set of domains and couldn't reach any of these
  sites directly (only a separate fetch tool could, and that tool isn't
  something a plain Python script can call). Treat the first Actions run
  as the real first test, and check its output before trusting it blindly.
- **SNHD's schedule PDF changes structure year to year** (their own
  schedule doc is literally re-approved and re-published annually) — the
  parser in `scrapers/snhd.py` handles the 2026 format; expect to revisit
  it around when the 2027 schedule is published.
- The Legistar scraper is parsing the public calendar HTML, not an
  authenticated API — Legistar does expose a JSON API at
  `webapi.legistar.com` for many municipal clients, which would be more
  robust if it works for Washoe County's client key. Worth checking first
  if the HTML scraper gets brittle.

## Data schema

`data/meetings.json` — a list of:

```json
{
  "id": "nnph-dboh-2026-09-24",
  "source_id": "nnph-dboh",
  "tier": "local",
  "date": "2026-09-24",
  "time": "13:00",
  "title": "Washoe County District Board of Health (NNPH)",
  "note": "Washoe Co. Admin Complex, Commission Chambers",
  "links": [{"label": "Legistar", "url": "https://washoe-nv.legistar.com/"}],
  "verified": true,
  "last_checked": "2026-09-04"
}
```

`data/briefing.json` — a list of:

```json
{
  "meeting_id": "house-ec-oversight-2026-06-25",
  "generated_at": "2026-09-04",
  "confidence": "verified",
  "relevance_tags": ["finance", "grants"],
  "note": "Congressional Medicaid-integrity scrutiny tends to precede tighter federal audit and documentation requirements..."
}
```

`confidence` is either `"verified"` (Claude read real agenda/hearing
content) or `"unverified"` (title/topic only — rendered as a "check
source" note on the page rather than a confident claim).
