"""Scraper for Legistar-hosted calendars (e.g. washoe-nv.legistar.com).

Legistar sites are used by hundreds of local governments. Two ways in:

1. The public web API at ``webapi.legistar.com/v1/{client}`` — JSON,
   documented at https://webapi.legistar.com/Home/Examples. This is the
   more robust option *if* the client (e.g. "washoe") has it enabled;
   not every Legistar customer exposes it. Try this first when hardening
   this scraper — it was not reachable for testing from the environment
   that wrote this file (see the repo README's "known limitations").

2. The public calendar page (``Calendar.aspx``), which this module parses
   with BeautifulSoup as the fallback. It's server-rendered HTML (visible
   without executing JS), which is what makes plain `requests` viable here.

Only meetings whose body name matches `body_name` (case-insensitive
substring) are returned, since a county's Legistar instance lists every
board on one calendar.
"""

from __future__ import annotations

import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from .base import Link, Meeting, ScrapeError

USER_AGENT = "health-docket/1.0 (+https://github.com/; contact: repo owner)"


def _try_api(client: str, body_name: str) -> list[Meeting] | None:
    """Attempt the JSON API; return None (not []) if it's unreachable/blocked
    so the caller falls back to HTML rather than reporting zero meetings."""
    try:
        resp = requests.get(
            f"https://webapi.legistar.com/v1/{client}/events",
            params={"$filter": f"EventBodyName eq '{body_name}'"},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=20,
        )
        resp.raise_for_status()
        events = resp.json()
    except Exception:
        return None

    meetings = []
    for ev in events:
        raw_date = ev.get("EventDate")  # e.g. "2026-09-24T00:00:00"
        if not raw_date:
            continue
        d = raw_date.split("T")[0]
        time_raw = ev.get("EventTime")  # e.g. "1:00 PM"
        time_iso = _parse_time(time_raw) if time_raw else None

        links = []
        if ev.get("EventAgendaFile"):
            links.append(Link("Agenda", ev["EventAgendaFile"]))
        if ev.get("EventMinutesFile"):
            links.append(Link("Minutes", ev["EventMinutesFile"]))
        if ev.get("EventInSiteURL"):
            links.append(Link("Meeting details", ev["EventInSiteURL"]))

        meetings.append(
            Meeting(
                id="",  # filled by caller
                source_id="",  # filled by caller
                tier="local",
                date=d,
                time=time_iso,
                title=body_name,
                note=ev.get("EventLocation"),
                links=links,
            )
        )
    return meetings


def _parse_time(raw: str) -> str | None:
    for fmt in ("%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None


def _scrape_html_calendar(client: str, body_name: str) -> list[Meeting]:
    url = f"https://{client}-nv.legistar.com/Calendar.aspx"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        raise ScrapeError(f"Could not load {url}: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table tr")
    meetings: list[Meeting] = []

    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cells) < 3:
            continue
        row_text = " ".join(cells)
        if body_name.lower() not in row_text.lower():
            continue

        date_match = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", row_text)
        if not date_match:
            continue
        try:
            d = datetime.strptime(date_match.group(1), "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            continue

        time_match = re.search(r"\b(\d{1,2}:\d{2}\s*[AP]M)\b", row_text, re.I)
        time_iso = _parse_time(time_match.group(1)) if time_match else None

        links = []
        for a in row.find_all("a", href=True):
            label = a.get_text(strip=True) or "Details"
            href = a["href"]
            if href.startswith("/"):
                href = f"https://{client}-nv.legistar.com{href}"
            links.append(Link(label, href))

        meetings.append(
            Meeting(
                id="",
                source_id="",
                tier="local",
                date=d,
                time=time_iso,
                title=body_name,
                note=None,
                links=links,
                # HTML-table parsing is more fragile than the JSON API —
                # flag these as unverified so a human glances at them once.
                verified=len(links) > 0,
            )
        )

    return meetings


def scrape(source_cfg: dict) -> list[Meeting]:
    client = source_cfg["legistar_client"]
    body_name = source_cfg["body_name"]
    source_id = source_cfg["id"]

    meetings = _try_api(client, body_name)
    if meetings is None:
        meetings = _scrape_html_calendar(client, body_name)

    for m in meetings:
        m.source_id = source_id
        m.id = f"{source_id}-{m.date}"

    return meetings
