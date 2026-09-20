# Health Docket — Status

Read this file first, every session. Then follow these steps in order.

1. Open `pm/Health_Docket_Rebuild_Gantt.xlsx`, "Task Plan" tab.
2. Check for a task already marked **"In progress"** first — if one exists, resume that one. Only if none is in progress, find the first row where Status = "Not started" AND every task listed in Predecessor(s) has Status = "Done". That row is the current task.
3. Read that row's Notes, Files, Design reference, and Verify done columns.
4. Check whether the files it lists already exist in the repo — some may partially exist from earlier work. Don't assume the Gantt is current; the code is the ground truth if the two disagree.
5. Propose a plan for that task before writing or changing anything. Wait for approval.
6. Once approved: do the work, commit, and run the Verify done check yourself before calling it finished.

7. **STOP before writing your final reply to Jack. Do not send it until all of these are already done — not planned, not "I'll do it next time":**
   - Task Plan tab: Status for the task you touched, updated ("In progress" if partial, "Blocked" if stuck and why, "Done" if complete)
   - Task Plan tab: Notes/Files columns updated if anything changed from what was planned
   - Task Plan tab: **a new row added to the Session Log** (bottom of the sheet) — date, what changed, and any task status changes. Never overwrite a prior row.
   - This file's "Current task" and "Last updated" fields, updated
   - "Known issues" below, updated if you found or resolved one

   A session that ends without these edits made has not actually finished, whatever else got done. If you're about to reply to Jack and haven't touched the Gantt file yet, that's the signal you skipped this step — go back and do it first.

8. If every row on the Task Plan tab is "Done," say so and ask what's next — don't invent new tasks.

## Current task

Task 1 — Design & migrate schema: Done.
Task 2 — Verify Legistar API access (nnph-dboh): Done, with one caveat (see below).
Task 3 — Harden NELIS scraper selectors: Done. Jack ran it himself from his own terminal 2026-09-19 — 7 real meetings came back (Jan-Aug 2026, real links), no code changes needed.
Task 4 — Provision hosting: In progress. Jack created the Render account 2026-09-19 (the one step that had to be him). No web service or database created on Render yet. Chosen plan: Hobby workspace ($0) + paid web service ($7/mo) + paid Postgres ($6/mo) ≈ $13/month. Free tier was deliberately ruled out: Render's free Postgres expires 30 days after creation and is permanently deleted 14 days after that — wrong fit for data that needs to persist.
Task 5 — Backend API: Done. All 7 endpoints from spec §6 (GET /api/policy-areas, /{slug}/snapshot, /attention, /bodies, GET /api/subjects/{slug}, GET+POST /api/focus-areas) plus a bonus GET /api/health, built and tested locally 2026-09-19 against a fresh db/migrate.py build. Every endpoint returns the documented {data, generated_at} envelope; 404 confirmed for bad slugs, 400 confirmed for an invalid policy_area_id on POST /api/focus-areas, and the case-insensitive upsert-by-name behavior on that same endpoint confirmed correct. All counts come back zero/empty right now — that's expected, not a bug, since Tasks 6-8 (document capture, extraction, subject tagging) haven't run yet.

**Task 4 is next.** Now that Task 5's code exists, the remaining part of Task 4 — creating the actual Render web service + Postgres database, writing deploy/render.yaml, deploying this API, and running Task 4's own Verify done check (hitting the live URL from an outside network) — can happen. That's the natural next step.

**Task 2's caveat:** the Legistar JSON API returns a server error (500) for the washoe client, confirmed live 2026-09-19 — not usable, matches the scraper's own note that it wasn't reachable when written. The body_name bug is fixed (`config/sources.yaml` now says "Northern Nevada Public Health"), and a live fetch of the actual calendar page confirmed a real meeting is listed under that corrected name. Jack separately confirmed the same site works from his own terminal while testing Task 3, so the earlier concern about legistar.com being unreachable was specific to Claude's own sandboxed tools, not a real-world problem.

Last updated: 2026-09-19 (Task 5 completed)

## Known issues

- `nnph-dboh` body_name mismatch in `config/sources.yaml` — **Fixed 2026-09-19.** Config now says "Northern Nevada Public Health," matching the live Washoe Legistar site.
- `house-ec-health` committee_system_code — config uses `hsif00` (the full Energy & Commerce Committee), but the Health Subcommittee's actual code is very likely `hsif14`. Not confirmed against a live API call (public demo key was rate-limited) — needs a check with the real `CONGRESS_API_KEY`.

## Source of truth for task order

`pm/Health_Docket_Rebuild_Gantt.xlsx`'s task list, phases, and dependencies come from `docs/policy-docket-design-spec.md` §8 "Build Plan" — that document's own revision history declares v1.0 "the specification of record in place of the interactive mockups." Task durations in the Gantt are Claude's estimates, not from the spec.

## Session log

See the Session Log table at the bottom of the Task Plan tab in `pm/Health_Docket_Rebuild_Gantt.xlsx` — this file doesn't duplicate it, to avoid the two going out of sync. Check there for the full history.

- 2026-09-19 — Rebuilt the Task Plan's 10 rows to match the design-spec's §8 Build Plan (was previously based on the outdated "Docket Build Map" artifact). Added Design reference and Verify done columns. Added this Session Log mechanism to both documents. No task status changed.
- 2026-09-19 — Ran `db/migrate.py` for the first time; Task 1 verified and marked Done (see Gantt Session Log for the full check). Also committed a `.gitignore` fix that had been sitting uncommitted since an earlier session.
- 2026-09-19 — Task 2: fixed the nnph-dboh body_name bug, confirmed the Legistar JSON API 500s for this client, confirmed the corrected name matches a real live meeting. Could not run the scraper itself end-to-end (network policy blocks legistar.com from both sandboxes this session) — left a one-line command in Current task for Jack to close that gap himself. Re-ran db/migrate.py so the database picked up the config fix.
- 2026-09-19 — Task 3 recon (task not started, no code changed): confirmed neither sandbox available this session can reach leg.state.nv.us at all (blocked in the cloud workspace; blocked and missing Playwright on Jack's Mac sandbox). Confirmed the real page is JS-rendered (a plain fetch returns zero meetings, matching the scraper's own docstring warning). Left a ready-to-run command in Current task for Jack to test from his own terminal, which has neither restriction.
- 2026-09-19 — Task 3 verified: Jack ran scrapers/nelis.py from his own terminal and got 7 real meetings back, not an empty list. No code changes needed. Task 3 marked Done. Current task section rewritten to flag that Task 4 and Task 5 are both eligible now, and that Task 4 needs Jack's own decision/account, not Claude's work.
- 2026-09-19 — Task 4: Jack created the Render account. Confirmed no service/database created yet. Researched Render's real pricing (verified against the live page, not a third-party summary) and picked Hobby workspace + paid web service + paid Postgres (~$13/mo), ruling out the free tier because its Postgres auto-deletes after ~44 days. Task 4 marked In progress; full completion (deploying, verifying a live URL) waits on Task 5's code existing.
- 2026-09-19 — Task 5: wrote the full Backend API (api/main.py, api/db.py, route modules for policy-areas, subjects, focus-areas, plus a bonus /api/health) per spec §6. Installed fastapi + uvicorn, rebuilt the database, ran the server locally and curled every endpoint end to end including the 404/400 error paths and the focus-area upsert-by-name behavior — all matched the Verify-done check exactly. Committed to git; pushed to GitHub. Task 5 marked Done. Task 4 (actually deploying to Render) is the natural next step now.
