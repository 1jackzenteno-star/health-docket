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

No task is currently "In progress." **Two tasks are now eligible at once** (both have every predecessor Done) — read both before picking:

- **Task 4 — Provision hosting.** Foundation phase, no predecessors. This is the one task in the whole plan that isn't Claude's to do: it means Jack picking a host (Render, Railway, Fly.io, or a cheap VPS — spec estimates ~$5-10/mo) and creating the account themselves, since it needs Jack's own billing info. Claude can help pick and can write the config file once Jack has an account, but can't sign up for one.
- **Task 5 — Backend API.** Backend/Frontend phase, needs only Task 1 (Done). This is real coding work Claude can start right now, independent of Task 4 — seven endpoints, spec'd in full detail in §6 of the design doc. Doesn't need to wait on hosting to be built and tested locally.

Practical read: don't get stuck waiting on Task 4 just because it's listed first. If Jack hasn't picked a host yet, propose starting Task 5 instead and come back to Task 4 whenever Jack's ready to decide.

**Task 2's caveat:** the Legistar JSON API returns a server error (500) for the washoe client, confirmed live 2026-09-19 — not usable, matches the scraper's own note that it wasn't reachable when written. The body_name bug is fixed (`config/sources.yaml` now says "Northern Nevada Public Health"), and a live fetch of the actual calendar page confirmed a real meeting is listed under that corrected name. Jack separately confirmed the same site works from his own terminal while testing Task 3, so the earlier concern about legistar.com being unreachable was specific to Claude's own sandboxed tools, not a real-world problem.

Last updated: 2026-09-19

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
