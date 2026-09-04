#!/usr/bin/env python3
"""Reads config/sources.yaml, runs the matching scraper for each source,
and upserts the results into data/meetings.json.

Upsert rule: match on `id`. A re-scraped meeting overwrites time/title/note/
links/verified but never removes a meeting that this run's scraper simply
didn't happen to return (a source being briefly unreachable shouldn't erase
history) — deletions only happen if you remove the source from meetings.json
by hand, or add a --prune-missing flag call yourself when you're confident.

Usage:
    python scripts/run_scrapers.py [--source SOURCE_ID ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.base import ScrapeError  # noqa: E402
from scrapers import legistar, congress, nelis, snhd, generic_html  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT / "config" / "sources.yaml"
MEETINGS_PATH = ROOT / "data" / "meetings.json"

SCRAPER_REGISTRY = {
    "legistar": legistar.scrape,
    "congress_api": congress.scrape,
    "nelis": nelis.scrape,
    "snhd_schedule": snhd.scrape,
    "generic_html": generic_html.scrape,
}


def load_sources() -> list[dict]:
    with open(SOURCES_PATH) as f:
        return yaml.safe_load(f)["sources"]


def load_meetings() -> list[dict]:
    if not MEETINGS_PATH.exists():
        return []
    with open(MEETINGS_PATH) as f:
        return json.load(f)


def save_meetings(meetings: list[dict]) -> None:
    meetings.sort(key=lambda m: m["date"])
    with open(MEETINGS_PATH, "w") as f:
        json.dump(meetings, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="append", help="Only run these source ids")
    args = parser.parse_args()

    sources = load_sources()
    if args.source:
        sources = [s for s in sources if s["id"] in args.source]

    existing = {m["id"]: m for m in load_meetings()}
    today = date.today().isoformat()

    for source_cfg in sources:
        scraper_type = source_cfg["type"]
        scraper_fn = SCRAPER_REGISTRY.get(scraper_type)
        if scraper_fn is None:
            print(f"[skip] {source_cfg['id']}: no scraper registered for type '{scraper_type}'")
            continue

        print(f"[run]  {source_cfg['id']} ({scraper_type})...")
        try:
            found = scraper_fn(source_cfg)
        except ScrapeError as e:
            print(f"[fail] {source_cfg['id']}: {e}")
            continue
        except Exception as e:  # noqa: BLE001 — never let one bad source kill the run
            print(f"[error] {source_cfg['id']}: unexpected error: {e}")
            continue

        for meeting in found:
            existing[meeting.id] = meeting.to_dict(last_checked=today)

        print(f"       -> {len(found)} meeting(s) found")

    save_meetings(list(existing.values()))
    print(f"\nWrote {len(existing)} total meetings to {MEETINGS_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
