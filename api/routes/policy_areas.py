"""Policy Area endpoints -- design spec §6, rows 1-4.

    GET /api/policy-areas
    GET /api/policy-areas/{slug}/snapshot
    GET /api/policy-areas/{slug}/attention
    GET /api/policy-areas/{slug}/bodies

All 32 policy_areas rows exist (seeded by db/migrate.py, Task 1), but
meeting_subjects -- the table linking a meeting to a subject to a policy
area -- is deliberately empty until Task 8 (subject tagging) is built.
So every count below is correctly zero right now, for every area except
none: that's the honest empty state the spec calls for ("empty buckets
return zero-state, not an error"), not a bug in this endpoint. It will
start returning real numbers the moment Task 8 populates that table,
with no code change needed here.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.db import latest_data_timestamp, query, query_one, slugify

router = APIRouter(prefix="/api/policy-areas", tags=["policy-areas"])


def _find_policy_area(slug: str):
    for row in query("SELECT id, name, sort_order FROM policy_areas"):
        if slugify(row["name"]) == slug:
            return row
    return None


def _find_focus_area(slug: str):
    for row in query("SELECT id, name FROM focus_areas"):
        if slugify(row["name"]) == slug:
            return row
    return None


def _weekly_counts(policy_area_id: int, weeks: int = 8) -> list[int]:
    """Real meeting counts for this policy area, bucketed into the last
    `weeks` calendar weeks. All zero until Task 8 populates
    meeting_subjects -- see module docstring."""
    rows = query(
        """SELECT m.occurred_at AS occurred_at
           FROM meetings m
           JOIN meeting_subjects ms ON ms.meeting_id = m.id
           JOIN legislative_subjects ls ON ls.id = ms.subject_id
           WHERE ls.policy_area_id = ?""",
        (policy_area_id,),
    )
    today = datetime.now(timezone.utc).date()
    buckets = [0] * weeks
    for r in rows:
        try:
            d = datetime.fromisoformat(r["occurred_at"]).date()
        except ValueError:
            continue
        weeks_ago = (today - d).days // 7
        if 0 <= weeks_ago < weeks:
            buckets[weeks - 1 - weeks_ago] += 1
    return buckets


@router.get("")
def list_policy_areas(
    focus_area: Optional[str] = Query(
        None, description="Focus-area slug to filter by (FR8)"
    )
):
    focus_area_id = None
    if focus_area is not None:
        fa = _find_focus_area(focus_area)
        if fa is None:
            # Spec: this endpoint is "200 only" -- an unknown focus_area
            # filters to an empty result rather than a 404.
            return {"data": [], "generated_at": latest_data_timestamp()}
        focus_area_id = fa["id"]

    areas = query("SELECT id, name, sort_order FROM policy_areas ORDER BY sort_order")
    if focus_area_id is not None:
        allowed_ids = {
            r["policy_area_id"]
            for r in query(
                "SELECT policy_area_id FROM focus_area_policy_areas WHERE focus_area_id = ?",
                (focus_area_id,),
            )
        }
        areas = [a for a in areas if a["id"] in allowed_ids]

    data = []
    for area in areas:
        flagged = query_one(
            """SELECT COUNT(DISTINCT ms.meeting_id) AS n
               FROM meeting_subjects ms
               JOIN legislative_subjects ls ON ls.id = ms.subject_id
               WHERE ls.policy_area_id = ?""",
            (area["id"],),
        )["n"]
        data.append(
            {
                "slug": slugify(area["name"]),
                "name": area["name"],
                "flagged_count": flagged,
                "sparkline": _weekly_counts(area["id"]),
            }
        )
    return {"data": data, "generated_at": latest_data_timestamp()}


@router.get("/{slug}/snapshot")
def policy_area_snapshot(slug: str):
    area = _find_policy_area(slug)
    if area is None:
        raise HTTPException(status_code=404, detail=f"Unknown policy area slug: {slug}")

    tiers = query("SELECT key, label FROM tiers ORDER BY sort_index")
    snapshot = []
    for tier in tiers:
        n = query_one(
            """SELECT COUNT(DISTINCT m.id) AS n
               FROM meetings m
               JOIN bodies b ON b.id = m.body_id
               JOIN meeting_subjects ms ON ms.meeting_id = m.id
               JOIN legislative_subjects ls ON ls.id = ms.subject_id
               WHERE ls.policy_area_id = ? AND b.tier_key = ?""",
            (area["id"], tier["key"]),
        )["n"]
        snapshot.append({"tier": tier["key"], "label": tier["label"], "meeting_count": n})

    return {
        "data": {"slug": slug, "name": area["name"], "tiers": snapshot},
        "generated_at": latest_data_timestamp(),
    }


@router.get("/{slug}/attention")
def policy_area_attention(slug: str, limit: int = Query(20, ge=1, le=100)):
    area = _find_policy_area(slug)
    if area is None:
        raise HTTPException(status_code=404, detail=f"Unknown policy area slug: {slug}")

    rows = query(
        """SELECT m.id, m.title, m.occurred_at, m.status, b.name AS body_name, b.tier_key,
                  br.note_text, br.confidence, br.model_version, br.relevance_tags,
                  br.generated_at AS briefing_generated_at
           FROM meetings m
           JOIN bodies b ON b.id = m.body_id
           JOIN meeting_subjects ms ON ms.meeting_id = m.id
           JOIN legislative_subjects ls ON ls.id = ms.subject_id
           LEFT JOIN briefings br ON br.meeting_id = m.id
           WHERE ls.policy_area_id = ? AND br.id IS NOT NULL
           ORDER BY (m.occurred_at >= date('now')) DESC, m.occurred_at ASC
           LIMIT ?""",
        (area["id"], limit),
    )
    data = []
    for r in rows:
        data.append(
            {
                "meeting_id": r["id"],
                "title": r["title"],
                "occurred_at": r["occurred_at"],
                "status": r["status"],
                "body_name": r["body_name"],
                "tier": r["tier_key"],
                # AI-derived fields nested under their own model_version,
                # per NFR3 -- never flattened into the meeting itself.
                "briefing": {
                    "note": r["note_text"],
                    "confidence": r["confidence"],
                    "model_version": r["model_version"],
                    "relevance_tags": json.loads(r["relevance_tags"]) if r["relevance_tags"] else [],
                    "generated_at": r["briefing_generated_at"],
                },
            }
        )
    return {"data": data, "generated_at": latest_data_timestamp()}


@router.get("/{slug}/bodies")
def policy_area_bodies(slug: str, tier: Optional[str] = Query(None)):
    area = _find_policy_area(slug)
    if area is None:
        raise HTTPException(status_code=404, detail=f"Unknown policy area slug: {slug}")

    sql = """
        SELECT DISTINCT b.id, b.slug, b.name, b.tier_key, b.watch_url
        FROM bodies b
        JOIN meetings m ON m.body_id = b.id
        JOIN meeting_subjects ms ON ms.meeting_id = m.id
        JOIN legislative_subjects ls ON ls.id = ms.subject_id
        WHERE ls.policy_area_id = ?
    """
    params: list = [area["id"]]
    if tier:
        sql += " AND b.tier_key = ?"
        params.append(tier)
    bodies = query(sql, params)

    today = date.today().isoformat()
    data = []
    for body in bodies:
        meetings = query(
            "SELECT id, title, occurred_at, status FROM meetings WHERE body_id = ? ORDER BY occurred_at DESC",
            (body["id"],),
        )
        past, upcoming = [], []
        for m in meetings:
            m_dict = dict(m)
            docs = query(
                "SELECT doc_type, capture_status, extraction_status FROM meeting_documents WHERE meeting_id = ?",
                (m["id"],),
            )
            m_dict["documents"] = [dict(d) for d in docs]
            # occurred_at, not the (currently always-'scheduled') status
            # column, is what actually determines past vs. upcoming --
            # see db/migrate.py, which hardcodes status regardless of date.
            (past if m["occurred_at"] < today else upcoming).append(m_dict)

        data.append(
            {
                "slug": body["slug"],
                "name": body["name"],
                "tier": body["tier_key"],
                "watch_url": body["watch_url"],
                "past_meetings": past,
                "upcoming_meetings": upcoming,
            }
        )

    return {"data": data, "generated_at": latest_data_timestamp()}


@router.get("/{slug}/subjects")
def policy_area_subjects(slug: str):
    """Distinct legislative_subjects tagged under this policy area, each
    with how many meetings carry it -- added in Task 10 (frontend
    cutover). Not one of design spec §6's original 7 endpoints: the spec's
    own nav model (§3.2) says "a subject is only reachable from a Policy
    Area page," but none of the 7 endpoints actually lists a policy
    area's subjects, so there was no real way to build that link. This is
    the minimal addition needed to make FR7's drill-down navigable, in
    the same spirit as §6's other endpoints (same envelope, same 404
    behavior) -- not a new capability, just the missing edge in an
    existing relationship.
    """
    area = _find_policy_area(slug)
    if area is None:
        raise HTTPException(status_code=404, detail=f"Unknown policy area slug: {slug}")

    rows = query(
        """SELECT ls.id, ls.name, COUNT(DISTINCT ms.meeting_id) AS meeting_count
           FROM legislative_subjects ls
           JOIN meeting_subjects ms ON ms.subject_id = ls.id
           WHERE ls.policy_area_id = ?
           GROUP BY ls.id, ls.name
           ORDER BY meeting_count DESC, ls.name""",
        (area["id"],),
    )
    data = [
        {"slug": slugify(r["name"]), "name": r["name"], "meeting_count": r["meeting_count"]}
        for r in rows
    ]
    return {"data": data, "generated_at": latest_data_timestamp()}
