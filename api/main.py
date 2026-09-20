"""Health Docket API -- FastAPI app, Task 5 of the build plan (design doc §6).

Serves the 7 endpoints spec'd in §6, plus /api/health for uptime checks
(see api/routes/health.py). Needs db/health_docket.db to already exist --
run `python3 db/migrate.py` first if it doesn't.

Run locally:

    pip install -r requirements.txt
    uvicorn api.main:app --reload

Then e.g. curl http://127.0.0.1:8000/api/health
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.routes import admin, focus_areas, health, pages, policy_areas, subjects

ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(
    title="Health Docket API",
    version="0.2.0",
    description="Serves the live Health Docket site (Task 10) plus its JSON API, "
    "both backed by db/health_docket.db. See docs/policy-docket-design-spec.md §6-7.",
)

app.include_router(health.router)
app.include_router(policy_areas.router)
app.include_router(subjects.router)
app.include_router(focus_areas.router)
app.include_router(admin.router)

app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

# Page routes (Task 10) mounted last so they don't shadow /api/* or /static/*.
app.include_router(pages.router)
