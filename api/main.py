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

from fastapi import FastAPI

from api.routes import focus_areas, health, policy_areas, subjects

app = FastAPI(
    title="Health Docket API",
    version="0.1.0",
    description="Serves data/meetings.json + data/briefing.json (via db/health_docket.db) "
    "to the Health Docket frontend. See docs/policy-docket-design-spec.md §6.",
)

app.include_router(health.router)
app.include_router(policy_areas.router)
app.include_router(subjects.router)
app.include_router(focus_areas.router)


@app.get("/")
def root():
    return {"service": "health-docket-api", "docs": "/docs"}
