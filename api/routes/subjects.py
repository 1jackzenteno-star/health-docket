"""GET /api/subjects/{slug} -- design spec §6, cross-tier subject drill-down (FR7).

legislative_subjects has zero rows today (db/migrate.py deliberately
doesn't seed it -- no real subject taxonomy exists until Task 8), so
every slug currently 404s. That's correct: there is nothing yet to find.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.db import latest_data_timestamp, query, query_one, slugify

router = APIRouter(prefix="/api/subjects", tags=["subjects"])


def _find_subject(slug: str):
    for row in query("SELECT id, name, policy_area_id FROM legislative_subjects"):
        if slugify(row["name"]) == slug:
            return row
    return None


@router.get("/{slug}")
def subject_detail(slug: str):
    subject = _find_subject(slug)
    if subject is None:
        raise HTTPException(status_code=404, detail=f"Unknown subject slug: {slug}")

    policy_area = query_one(
        "SELECT name FROM policy_areas WHERE id = ?", (subject["policy_area_id"],)
    )

    rows = query(
        """SELECT m.id, m.title, m.occurred_at, b.name AS body_name, b.tier_key,
                  ms.confidence, ms.tagged_by
           FROM meeting_subjects ms
           JOIN meetings m ON m.id = ms.meeting_id
           JOIN bodies b ON b.id = m.body_id
           WHERE ms.subject_id = ?
           ORDER BY m.occurred_at DESC""",
        (subject["id"],),
    )

    data = {
        "slug": slug,
        "name": subject["name"],
        "policy_area": policy_area["name"] if policy_area else None,
        "meetings": [dict(r) for r in rows],
    }
    return {"data": data, "generated_at": latest_data_timestamp()}
