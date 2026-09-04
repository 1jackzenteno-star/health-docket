"""Scraper for U.S. House/Senate committee meetings, via the official
Congress.gov API (api.congress.gov) rather than scraping congress.gov's own
HTML — their robots.txt disallows automated fetching of the committee
schedule pages, and there's a proper API for exactly this data.

Requires a free API key from https://api.congress.gov/sign-up, set as the
CONGRESS_API_KEY environment variable (a repo secret in GitHub Actions).

API docs: https://gpo.congress.gov/#/committee-meeting — the exact response
shape may drift over time; this module was written from the documented
schema, not verified against a live call (see repo README limitations).
"""

from __future__ import annotations

import os

import requests

from .base import Link, Meeting, ScrapeError

API_BASE = "https://api.congress.gov/v3"
CURRENT_CONGRESS = 119  # 119th Congress: 2025-2027. Bump every odd year.


def scrape(source_cfg: dict) -> list[Meeting]:
    api_key = os.environ.get("CONGRESS_API_KEY")
    if not api_key:
        raise ScrapeError(
            "CONGRESS_API_KEY not set — get a free key at "
            "https://api.congress.gov/sign-up and add it as a repo secret."
        )

    chamber = source_cfg["chamber"]  # "house" | "senate"
    committee_code = source_cfg["committee_system_code"]
    source_id = source_cfg["id"]

    try:
        resp = requests.get(
            f"{API_BASE}/committee-meeting/{CURRENT_CONGRESS}/{chamber}",
            params={"api_key": api_key, "format": "json", "limit": 50},
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        raise ScrapeError(f"Congress.gov API request failed: {e}") from e

    meetings: list[Meeting] = []
    for item in payload.get("committeeMeetings", []):
        committees = item.get("committees", [])
        if not any(committee_code.lower() in (c.get("systemCode") or "").lower() for c in committees):
            continue

        raw_date = item.get("date")  # expected "YYYY-MM-DD" or similar
        if not raw_date:
            continue
        d = raw_date[:10]

        title = item.get("title") or f"{source_cfg['name']} meeting"
        links = []
        if item.get("meetingDocuments"):
            for doc in item["meetingDocuments"][:3]:
                if doc.get("url"):
                    links.append(Link(doc.get("documentType", "Document"), doc["url"]))
        if item.get("url"):
            links.append(Link("Congress.gov record", item["url"]))

        meetings.append(
            Meeting(
                id=f"{source_id}-{d}",
                source_id=source_id,
                tier="federal",
                date=d,
                title=title,
                links=links,
                # API data is structured/authoritative; still worth a
                # second look until this scraper has a few clean runs.
                verified=False,
            )
        )

    return meetings
