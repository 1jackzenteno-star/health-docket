#!/usr/bin/env python3
"""Renders templates/dashboard.html.j2 from data/meetings.json,
data/briefing.json, and config/sources.yaml into site/index.html.

This is the ONLY script that touches the page's HTML. If you want to change
the page's design, edit the template; if you want to change what's on it,
edit the data files or sources.yaml — never hand-edit site/index.html, it
gets overwritten every run.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT / "config" / "sources.yaml"
MEETINGS_PATH = ROOT / "data" / "meetings.json"
BRIEFING_PATH = ROOT / "data" / "briefing.json"
TEMPLATE_DIR = ROOT / "templates"
OUTPUT_PATH = ROOT / "site" / "index.html"

TIER_PILL_CLASS = {"federal": "pill-federal", "state": "pill-recurring", "local": "pill-upcoming"}
TIER_DOT_CLASS = {"federal": "dot-federal", "state": "dot-state", "local": "dot-local"}
TIER_DISPLAY = {"federal": "Federal", "state": "NV Legislature", "local": "NV local"}


def load_json(path: Path) -> list:
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def main() -> None:
    config = yaml.safe_load(open(SOURCES_PATH))
    sources = config["sources"]
    tiers_cfg = config["tiers"]
    meetings = load_json(MEETINGS_PATH)
    briefing = load_json(BRIEFING_PATH)

    sources_by_id = {s["id"]: s for s in sources}
    meetings_by_id = {m["id"]: m for m in meetings}

    # --- Calendar tab: sources grouped by tier, each with its own meetings ---
    tiers = []
    for tier_key in ("federal", "state", "local"):
        tier_sources = []
        for s in sources:
            if s["tier"] != tier_key:
                continue
            own_meetings = sorted(
                (m for m in meetings if m["source_id"] == s["id"]),
                key=lambda m: m["date"],
            )
            tier_sources.append({**s, "meetings": own_meetings})
        tiers.append({**tiers_cfg[tier_key], "key": tier_key, "sources": tier_sources})

    # --- Impact Briefing tab: briefing entries joined with their meeting ---
    today = date.today()
    briefing_items = []
    for b in briefing:
        meeting = meetings_by_id.get(b["meeting_id"])
        if not meeting:
            continue  # meeting was removed since the note was written
        briefing_items.append({**b, "meeting": meeting})
    briefing_items.sort(key=lambda b: b["meeting"]["date"], reverse=True)

    # NB: key is "entries", not "items" — Jinja's dot-access on a dict
    # resolves to dict.items() (the builtin method) before falling back to
    # a same-named key, so `tier.items` here would silently be a method
    # object, not the list. Learned that one from render_site.py's first run.
    briefing_tiers = []
    for tier_key in ("federal", "state", "local"):
        entries = [b for b in briefing_items if b["meeting"]["tier"] == tier_key]
        briefing_tiers.append({**tiers_cfg[tier_key], "key": tier_key, "entries": entries})

    # --- JS calendar data: same shape the hand-authored version used ---
    calendar_meetings = [
        {
            "date": m["date"],
            "tier": m["tier"],
            "title": m["title"],
            "note": m.get("note"),
            "links": m.get("links", []),
        }
        for m in meetings
    ]

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
    env.filters["tojson_safe"] = lambda v: json.dumps(v)
    template = env.get_template("dashboard.html.j2")

    html = template.render(
        generated_at=today.strftime("%b %-d, %Y") if hasattr(today, "strftime") else str(today),
        tiers=tiers,
        briefing_tiers=briefing_tiers,
        calendar_meetings_json=json.dumps(calendar_meetings, indent=2),
        tier_pill_class=TIER_PILL_CLASS,
        tier_dot_class=TIER_DOT_CLASS,
        tier_display=TIER_DISPLAY,
    )

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(html)
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
