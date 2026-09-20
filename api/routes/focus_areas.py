"""GET+POST /api/focus-areas -- design spec §6 (FR8). The one write endpoint.

Spec describes this as "Create/edit a focus area" via a single POST, so
POST here is an upsert keyed on name (case-insensitive): posting a name
that already exists replaces that focus area's policy_area_ids instead
of creating a duplicate. This is a design decision the spec left
implicit -- documented here since it isn't spelled out in §6 itself.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.db import execute, latest_data_timestamp, query, query_one, slugify

router = APIRouter(prefix="/api/focus-areas", tags=["focus-areas"])


class FocusAreaIn(BaseModel):
    name: str = Field(..., min_length=1)
    policy_area_ids: list[int] = Field(..., min_length=1)


def _serialize(area_id: int, name: str) -> dict:
    pa_rows = query(
        """SELECT pa.id, pa.name FROM focus_area_policy_areas fap
           JOIN policy_areas pa ON pa.id = fap.policy_area_id
           WHERE fap.focus_area_id = ?
           ORDER BY pa.sort_order""",
        (area_id,),
    )
    return {
        "id": area_id,
        "slug": slugify(name),
        "name": name,
        "policy_areas": [
            {"id": r["id"], "name": r["name"], "slug": slugify(r["name"])} for r in pa_rows
        ],
    }


@router.get("")
def list_focus_areas():
    areas = query("SELECT id, name FROM focus_areas ORDER BY name")
    data = [_serialize(a["id"], a["name"]) for a in areas]
    return {"data": data, "generated_at": latest_data_timestamp()}


@router.post("", status_code=201)
def create_or_edit_focus_area(payload: FocusAreaIn):
    valid_ids = {r["id"] for r in query("SELECT id FROM policy_areas")}
    bad_ids = [i for i in payload.policy_area_ids if i not in valid_ids]
    if bad_ids:
        raise HTTPException(status_code=400, detail=f"Invalid policy_area_ids: {bad_ids}")

    existing = query_one(
        "SELECT id FROM focus_areas WHERE lower(name) = lower(?)", (payload.name,)
    )
    if existing is not None:
        area_id = existing["id"]
        execute("DELETE FROM focus_area_policy_areas WHERE focus_area_id = ?", (area_id,))
    else:
        area_id = execute("INSERT INTO focus_areas (name) VALUES (?)", (payload.name,))

    for pa_id in payload.policy_area_ids:
        execute(
            "INSERT INTO focus_area_policy_areas (focus_area_id, policy_area_id) VALUES (?, ?)",
            (area_id, pa_id),
        )

    return {"data": _serialize(area_id, payload.name), "generated_at": latest_data_timestamp()}
