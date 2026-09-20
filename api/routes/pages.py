"""HTML page routes -- Task 10 of the build plan (design doc §7, Approach A).

Serves the three screens from §3.1 (Overview, Policy Area, Subject) as
Jinja2-rendered shells. Per NFR4 ("template/rendering code shall never
contain meeting data directly"), these templates carry NO meeting data
at render time -- each one is close to static HTML+CSS, plus a small
inline script that hands the page's own URL parameter (a slug, which is
routing information, not meeting data) to static/docket.js, which then
fetches everything real from the JSON API in the browser. That fetch is
exactly what the Gantt's own verify-done check looks for: a Network-tab
request to e.g. /api/subjects/medicaid, not a hardcoded array.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def overview_page(request: Request):
    return templates.TemplateResponse(request, "overview.html.j2", {})


@router.get("/policy-areas/{slug}", response_class=HTMLResponse)
def policy_area_page(request: Request, slug: str):
    return templates.TemplateResponse(request, "health.html.j2", {"slug": slug})


@router.get("/subjects/{slug}", response_class=HTMLResponse)
def subject_page(request: Request, slug: str):
    return templates.TemplateResponse(request, "subject.html.j2", {"slug": slug})
