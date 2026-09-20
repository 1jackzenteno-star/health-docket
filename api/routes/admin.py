"""POST /api/admin/refresh -- Task 10 addition (design doc §5.1, §8 Task 10).

Design spec §5.1 says to "keep GitHub Actions cron for the scrape /
capture / extract / tag / brief stages -- that infrastructure already
exists and works." But once the frontend cutover moves serving to a
live Render-hosted database (a file on Render's persistent disk), a
GitHub Actions runner has no network path to that disk -- it can't just
open the file and write to it the way scripts/run_scrapers.py and
db/migrate.py could when everything lived in the git repo. This
endpoint is the bridge: GitHub Actions (.github/workflows/weekly-refresh.yml)
calls it on a schedule with a shared secret, and the actual pipeline
stages run right here, in-process on the Render dyno, against the disk
this service already has open.

Deliberately runs only the four DB-native, already-idempotent stages --
capture_documents.py, extract_text.py, tag_subjects.py,
generate_briefings.py (Tasks 6-9) -- each safe to re-run because it
only processes rows that need it unless --force is passed, which this
endpoint never passes. It does NOT run scripts/run_scrapers.py or
db/migrate.py:

  - run_scrapers.py still only knows how to write to data/meetings.json,
    a git-tracked file -- it was never rewritten to write meetings/bodies
    rows directly to the database (no task in the build plan covered
    that rewrite; see pm/STATUS.md Known issues).
  - db/migrate.py drops and rebuilds the ENTIRE database from schema.sql
    + sources.yaml + those same JSON files every time it runs -- exactly
    the destructive-rebuild behavior pm/STATUS.md already flags as a
    known issue. Calling it here would silently wipe every
    legislative_subjects/meeting_subjects/briefings row Tasks 8-9
    produced. Never call it from a recurring job until that's fixed.

Net effect, honestly stated: this keeps the live database's documents,
subject tags, and briefings current for whatever meetings already exist
in it. Getting NEW meetings into the live database at all is still an
unsolved gap -- tracked in pm/STATUS.md, not silently absorbed into
this task.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException

ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE = ROOT / "pipeline"

router = APIRouter(prefix="/api/admin", tags=["admin"])

STAGES = [
    ("capture_documents", PIPELINE / "capture_documents.py", []),
    ("extract_text", PIPELINE / "extract_text.py", []),
    ("tag_subjects", PIPELINE / "tag_subjects.py", []),
    ("generate_briefings", PIPELINE / "generate_briefings.py", []),
]

STAGE_TIMEOUT_SECONDS = 600  # generous -- a handful of LLM calls per meeting, not a bulk job


def _run_stage(name: str, script: Path, extra_args: list[str]) -> dict:
    try:
        result = subprocess.run(
            [sys.executable, str(script), *extra_args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=STAGE_TIMEOUT_SECONDS,
            env=os.environ.copy(),
        )
        return {
            "stage": name,
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-2000:],
            "stderr_tail": result.stderr[-2000:],
        }
    except subprocess.TimeoutExpired:
        return {"stage": name, "ok": False, "returncode": None, "error": f"timed out after {STAGE_TIMEOUT_SECONDS}s"}
    except Exception as e:  # noqa: BLE001 -- one stage's crash should never block the rest (§9.1 philosophy)
        return {"stage": name, "ok": False, "returncode": None, "error": str(e)}


@router.post("/refresh")
def refresh(x_refresh_token: str | None = Header(default=None)):
    expected = os.environ.get("REFRESH_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="REFRESH_TOKEN is not configured on this deployment")
    if not x_refresh_token or x_refresh_token != expected:
        raise HTTPException(status_code=401, detail="missing or invalid X-Refresh-Token header")

    results = [_run_stage(name, script, args) for name, script, args in STAGES]
    overall_ok = all(r["ok"] for r in results)
    return {"ok": overall_ok, "stages": results}
