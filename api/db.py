"""Database access for the Health Docket API.

Plain parameterized SQL (sqlite3), per design spec §5.1 -- no ORM needed
at this schema size. Route modules go through the helpers below instead
of opening their own connections.
"""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent

# Overridable so a deployment (Task 4) can point this at a persistent disk
# instead of the repo checkout -- see deploy/render.yaml. Local dev and
# `db/migrate.py` both leave this unset and get the repo-relative default.
DB_PATH = Path(os.environ["DATABASE_PATH"]) if os.environ.get("DATABASE_PATH") else ROOT / "db" / "health_docket.db"


def get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError(
            f"{DB_PATH} does not exist. Run `python3 db/migrate.py` first "
            "(see pm/STATUS.md for the current build-plan task)."
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def query_one(sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
    conn = get_conn()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """For INSERT/UPDATE/DELETE. Returns lastrowid (0 for statements that
    don't insert a row, e.g. a DELETE)."""
    conn = get_conn()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def slugify(name: str) -> str:
    """Deterministic slug derived from a name.

    policy_areas, legislative_subjects and focus_areas don't have a
    persisted `slug` column -- schema.sql (Task 1) predates this API and
    only gave `bodies` one. Rather than adding a migration for three
    tables just to support URL lookups, {slug} routes slugify on the fly
    and scan for a match. At the current table sizes (32 policy areas, a
    handful of subjects/focus areas) that's a full-table scan of a few
    dozen rows per request -- not free, but not worth optimizing until
    it's an actual bottleneck. A future task could add a real `slug`
    column and index it if this ever needs to scale past that.
    """
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def latest_data_timestamp() -> str:
    """The API's `generated_at` value (design spec §6): the most recent
    `last_checked` value across all meetings, i.e. when the scrape
    pipeline actually last ran -- not the current request time. Spec is
    explicit that this must be honest about the weekly-refresh cadence
    (NFR3), not imply live data. Falls back to now() only if the meetings
    table is empty, which shouldn't happen outside a fresh/empty database.
    """
    row = query_one("SELECT MAX(last_checked) AS ts FROM meetings")
    if row and row["ts"]:
        return row["ts"]
    return datetime.now(timezone.utc).isoformat()
