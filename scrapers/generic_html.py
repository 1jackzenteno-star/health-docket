"""Fallback scraper for a source with no dedicated module yet.

Fetches `watch_url` and looks for date-shaped text near the word "board" or
"meeting", purely as a low-confidence signal that *something* is postable.
Everything this returns is `verified=False` — it exists so a new focus area
can be added to config/sources.yaml immediately (type: generic_html) and
get a placeholder card on the dashboard pointing at the source, rather than
nothing at all, while a real scraper is written for it.
"""

from __future__ import annotations

import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from .base import Link, Meeting, ScrapeError

USER_AGENT = "health-docket/1.0"
DATE_RE = re.compile(r"([A-Z][a-z]+ \d{1,2},? \d{4})")


def scrape(source_cfg: dict) -> list[Meeting]:
    source_id = source_cfg["id"]
    url = source_cfg["watch_url"]

    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        raise ScrapeError(f"Could not load {url}: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    meetings = []
    seen_dates = set()
    for match in DATE_RE.finditer(text):
        raw = match.group(1).replace(",", "")
        try:
            d = datetime.strptime(raw, "%B %d %Y").strftime("%Y-%m-%d")
        except ValueError:
            continue
        if d in seen_dates:
            continue
        seen_dates.add(d)
        meetings.append(
            Meeting(
                id=f"{source_id}-{d}",
                source_id=source_id,
                tier=source_cfg["tier"],
                date=d,
                title=source_cfg["name"],
                links=[Link("Source page", url)],
                verified=False,
            )
        )

    return meetings
