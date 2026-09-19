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

Task 1 — Design & migrate schema: Done (2026-09-19). Verified: ran `db/migrate.py`, row counts matched meetings.json/briefing.json exactly (0 skipped), PRAGMA foreign_key_check clean.

No task is currently "In progress." Next eligible per the rule in step 2 above: Task 2 — Verify Legistar API access (nnph-dboh). Not started — do not begin it without proposing a plan first, per step 5. Task 2 is directly tied to the nnph-dboh body_name bug in Known issues below.

Last updated: 2026-09-19

## Known issues

- `nnph-dboh` body_name mismatch in `config/sources.yaml` — config says "District Board of Health," the live Washoe Legistar site says "Northern Nevada Public Health." Found 2026-09-19. **Fixed?: no, not yet applied to the file.**
  (This is exactly what Task 2's Verify done check will surface — fixing it is likely part of Task 2, not a separate task.)
- `house-ec-health` committee_system_code — config uses `hsif00` (the full Energy & Commerce Committee), but the Health Subcommittee's actual code is very likely `hsif14`. Not confirmed against a live API call (public demo key was rate-limited) — needs a check with the real `CONGRESS_API_KEY`.

## Source of truth for task order

`pm/Health_Docket_Rebuild_Gantt.xlsx`'s task list, phases, and dependencies come from `docs/policy-docket-design-spec.md` §8 "Build Plan" — that document's own revision history declares v1.0 "the specification of record in place of the interactive mockups." Task durations in the Gantt are Claude's estimates, not from the spec.

## Session log

See the Session Log table at the bottom of the Task Plan tab in `pm/Health_Docket_Rebuild_Gantt.xlsx` — this file doesn't duplicate it, to avoid the two going out of sync. Check there for the full history.

- 2026-09-19 — Rebuilt the Task Plan's 10 rows to match the design-spec's §8 Build Plan (was previously based on the outdated "Docket Build Map" artifact). Added Design reference and Verify done columns. Added this Session Log mechanism to both documents. No task status changed.
- 2026-09-19 — Ran `db/migrate.py` for the first time; Task 1 verified and marked Done (see Gantt Session Log for the full check). Also committed a `.gitignore` fix that had been sitting uncommitted since an earlier session.
