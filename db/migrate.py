#!/usr/bin/env python3
"""Builds db/health_docket.db from schema.sql, then seeds it from the
repo's existing sources of truth: config/sources.yaml (bodies, tiers,
admin tags) and data/meetings.json + data/briefing.json (meetings,
documents, briefings).

This is Task 1 of the build plan (design doc §8) — additive only.
Nothing in scrapers/, scripts/, or templates/ changes or depends on this
yet; config/sources.yaml and the two data/*.json files remain what the
weekly-refresh workflow actually reads and writes until a later task
wires the pipeline to this database instead.

Safe to re-run: it drops and rebuilds db/health_docket.db from scratch
every time, so it never drifts from whatever's currently in sources.yaml
and the JSON files. It does not modify those source files.

Deliberately NOT seeded, because no real data exists yet for them:
  - legislative_subjects (no subject tagging has been built — Task 8)
  - meeting_subjects     (same)
  - focus_areas / focus_area_policy_areas (the prototype's FOCUS_AREAS
    array was illustrative, never a Jack-approved real grouping)

Usage:
    python3 db/migrate.py
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "health_docket.db"
SCHEMA_PATH = ROOT / "db" / "schema.sql"
SOURCES_PATH = ROOT / "config" / "sources.yaml"
MEETINGS_PATH = ROOT / "data" / "meetings.json"
BRIEFING_PATH = ROOT / "data" / "briefing.json"

# The 32 real Congress.gov Policy Area buckets, in their standard order.
# Health is #18 — the only one with real tracked bodies today.
POLICY_AREAS = [
    "Agriculture and Food", "Animals", "Armed Forces and National Security",
    "Arts, Culture, Religion", "Civil Rights and Liberties, Minority Issues",
    "Commerce", "Congress", "Crime and Law Enforcement",
    "Economics and Public Finance", "Education", "Emergency Management",
    "Energy", "Environmental Protection", "Families",
    "Finance and Financial Sector", "Foreign Trade and International Finance",
    "Government Operations and Politics", "Health",
    "Housing and Community Development", "Immigration", "International Affairs",
    "Labor and Employment", "Law", "Native Americans",
    "Public Lands and Natural Resources", "Science, Technology, Communications",
    "Social Sciences and History", "Social Welfare", "Sports and Recreation",
    "Taxation", "Transportation and Public Works", "Water Resources Development",
]

# Fields on a sources.yaml entry that get their own bodies.* column rather
# than being folded into scraper_config.
BODY_TOP_LEVEL_FIELDS = {"id", "name", "tier", "type", "watch_url", "relevance_tags"}


def build_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())


def seed_tiers(conn: sqlite3.Connection, tiers_cfg: dict) -> None:
    rows = [
        (key, cfg.get("index"), cfg["label"], cfg.get("description", "").strip())
        for key, cfg in tiers_cfg.items()
    ]
    conn.executemany(
        "INSERT INTO tiers (key, sort_index, label, description) VALUES (?, ?, ?, ?)",
        rows,
    )
    print(f"  tiers: {len(rows)}")


def seed_policy_areas(conn: sqlite3.Connection) -> None:
    rows = [(name, i + 1) for i, name in enumerate(POLICY_AREAS)]
    conn.executemany(
        "INSERT INTO policy_areas (name, sort_order) VALUES (?, ?)", rows
    )
    print(f"  policy_areas: {len(rows)}")


def seed_bodies(conn: sqlite3.Connection, sources: list[dict]) -> dict[str, int]:
    slug_to_id: dict[str, int] = {}
    for src in sources:
        scraper_config = {k: v for k, v in src.items() if k not in BODY_TOP_LEVEL_FIELDS}
        cur = conn.execute(
            """INSERT INTO bodies (slug, name, tier_key, scraper_type, scraper_config, watch_url, active)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (
                src["id"],
                src["name"],
                src["tier"],
                src["type"],
                json.dumps(scraper_config) if scraper_config else None,
                src.get("watch_url"),
            ),
        )
        slug_to_id[src["id"]] = cur.lastrowid
        for tag in src.get("relevance_tags", []):
            conn.execute(
                "INSERT INTO body_admin_tags (body_id, tag) VALUES (?, ?)",
                (cur.lastrowid, tag),
            )
    print(f"  bodies: {len(slug_to_id)}")
    return slug_to_id


def seed_meetings(conn: sqlite3.Connection, meetings: list[dict], slug_to_id: dict[str, int]) -> dict[str, int]:
    ext_id_to_id: dict[str, int] = {}
    doc_count = 0
    skipped = []
    for m in meetings:
        body_id = slug_to_id.get(m["source_id"])
        if body_id is None:
            skipped.append(m["id"])
            continue
        cur = conn.execute(
            """INSERT INTO meetings
               (body_id, external_id, title, occurred_at, occurred_time, status, note, verified, last_checked)
               VALUES (?, ?, ?, ?, ?, 'scheduled', ?, ?, ?)""",
            (
                body_id, m["id"], m["title"], m["date"], m.get("time"),
                m.get("note"), 1 if m.get("verified") else 0, m.get("last_checked"),
            ),
        )
        meeting_id = cur.lastrowid
        ext_id_to_id[m["id"]] = meeting_id
        for link in m.get("links", []):
            conn.execute(
                """INSERT INTO meeting_documents
                   (meeting_id, label, doc_type, source_file_url, capture_status, extraction_status)
                   VALUES (?, ?, 'unspecified', ?, 'linked', 'pending')""",
                (meeting_id, link.get("label"), link["url"]),
            )
            doc_count += 1
    print(f"  meetings: {len(ext_id_to_id)}" + (f"  (skipped {len(skipped)}, unknown source_id: {skipped})" if skipped else ""))
    print(f"  meeting_documents: {doc_count}")
    return ext_id_to_id


def seed_briefings(conn: sqlite3.Connection, briefings: list[dict], ext_id_to_id: dict[str, int]) -> None:
    n = 0
    skipped = []
    for b in briefings:
        meeting_id = ext_id_to_id.get(b["meeting_id"])
        if meeting_id is None:
            skipped.append(b["meeting_id"])
            continue
        conn.execute(
            """INSERT INTO briefings
               (meeting_id, note_text, confidence, model_version, relevance_tags, generated_at)
               VALUES (?, ?, ?, NULL, ?, ?)""",
            (
                meeting_id, b["note"], b.get("confidence"),
                json.dumps(b.get("relevance_tags", [])), b["generated_at"],
            ),
        )
        n += 1
    print(f"  briefings: {n}" + (f"  (skipped {len(skipped)}, unknown meeting_id: {skipped})" if skipped else ""))


def main() -> None:
    sources_cfg = yaml.safe_load(SOURCES_PATH.read_text())
    meetings = json.loads(MEETINGS_PATH.read_text())
    briefings = json.loads(BRIEFING_PATH.read_text())

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        build_schema(conn)
        print(f"Building {DB_PATH.relative_to(ROOT)} from schema.sql + sources.yaml + meetings.json + briefing.json:")
        seed_tiers(conn, sources_cfg["tiers"])
        seed_policy_areas(conn)
        slug_to_id = seed_bodies(conn, sources_cfg["sources"])
        ext_id_to_id = seed_meetings(conn, meetings, slug_to_id)
        seed_briefings(conn, briefings, ext_id_to_id)
        conn.commit()
    finally:
        conn.close()

    print(f"Done. legislative_subjects, meeting_subjects, and focus_areas were left "
          f"empty — no real data exists for them yet (see module docstring).")


if __name__ == "__main__":
    main()
