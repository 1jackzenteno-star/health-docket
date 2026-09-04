#!/usr/bin/env python3
"""Finds meetings that don't have a briefing note yet (or whose meeting
data changed since their note was written) and asks Claude for one, scoped
to NNPH's administrative functions. Writes data/briefing.json.

Requires ANTHROPIC_API_KEY in the environment.

Usage:
    python scripts/generate_briefing.py [--days 120] [--max-age-days 90]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT / "config" / "sources.yaml"
MEETINGS_PATH = ROOT / "data" / "meetings.json"
BRIEFING_PATH = ROOT / "data" / "briefing.json"

RELEVANCE_CONTEXT = """\
You are writing a one-paragraph "why this matters" note for a dashboard read
by an administrator at Northern Nevada Public Health (NNPH), a Nevada county
health district. He handles FINANCE, IT/data systems, and HR for the
district — not clinical programs. His board (the Washoe County District
Board of Health) has the same statutory role as the other bodies tracked
here, so anything about board governance, board authority, or funding
mechanisms for local health districts is directly relevant to him even when
framed at the state or federal level.

For the meeting below, decide:
1. Is this genuinely relevant to district-level finance, HR, IT, grants/
   contract compliance, board governance, or general HHS/public-health
   funding policy? If it's purely a clinical/programmatic matter (a specific
   disease program, a treatment protocol) with no funding, staffing, or
   compliance angle, say so plainly rather than stretching for a connection.
2. Write ONE paragraph (2-4 sentences) explaining the connection concretely
   — not generic "this could matter" hedging. If you weren't given the
   actual agenda/hearing content (only a title), say so in the note itself
   and mark confidence "unverified"; if you were given real substance, you
   may mark it "verified".

Respond as JSON only, no other text:
{"relevant": true|false, "confidence": "verified"|"unverified",
 "relevance_tags": ["budget"|"hr"|"it"|"grants"|"compliance"|"board-authority"|"hhs-policy"],
 "note": "..."}

If relevant is false, note should briefly say why this doesn't reach the
admin-relevance bar, and it will be left off the dashboard's briefing tab.
"""


def load_json(path: Path) -> list:
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: list) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def call_claude(client, meeting: dict, source_cfg: dict | None) -> dict | None:
    prompt = (
        RELEVANCE_CONTEXT
        + "\n\nMeeting:\n"
        + json.dumps(
            {
                "title": meeting["title"],
                "date": meeting["date"],
                "note": meeting.get("note"),
                "tier": meeting["tier"],
                "source_relevance_tags": (source_cfg or {}).get("relevance_tags", []),
                "links": meeting.get("links", []),
            },
            indent=2,
        )
    )

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"[warn] could not parse model response as JSON for {meeting['id']}:\n{text}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=120, help="Only consider meetings within this many days of today")
    parser.add_argument("--max-age-days", type=int, default=90, help="Prune briefing entries older than this")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set — skipping briefing generation.", file=sys.stderr)
        sys.exit(1)

    try:
        import anthropic
    except ImportError:
        print("anthropic package not installed — pip install anthropic", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    sources_by_id = {s["id"]: s for s in yaml.safe_load(open(SOURCES_PATH))["sources"]}
    meetings = load_json(MEETINGS_PATH)
    briefing = load_json(BRIEFING_PATH)
    briefed_ids = {b["meeting_id"] for b in briefing}

    today = date.today()
    window_start = today - timedelta(days=args.days)

    candidates = [
        m for m in meetings
        if m["id"] not in briefed_ids
        and window_start.isoformat() <= m["date"] <= today.isoformat()
    ]

    print(f"{len(candidates)} meeting(s) need a briefing note.")

    for meeting in candidates:
        source_cfg = sources_by_id.get(meeting["source_id"])
        result = call_claude(client, meeting, source_cfg)
        if result is None:
            continue
        if not result.get("relevant", False):
            print(f"[skip] {meeting['id']}: not relevant enough — {result.get('note', '')[:80]}")
            continue

        briefing.append({
            "meeting_id": meeting["id"],
            "generated_at": today.isoformat(),
            "confidence": result.get("confidence", "unverified"),
            "relevance_tags": result.get("relevance_tags", []),
            "note": result.get("note", ""),
        })
        print(f"[ok]   {meeting['id']}: added ({result.get('confidence')})")

    # Prune stale entries so the briefing tab stays focused on what's recent.
    cutoff = (today - timedelta(days=args.max_age_days)).isoformat()
    meetings_by_id = {m["id"]: m for m in meetings}
    briefing = [
        b for b in briefing
        if meetings_by_id.get(b["meeting_id"], {}).get("date", "0000-00-00") >= cutoff
    ]

    save_json(BRIEFING_PATH, briefing)
    print(f"\nWrote {len(briefing)} briefing entries to {BRIEFING_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
