"""Scraper for Southern Nevada Health District's Board of Health.

SNHD publishes one PDF per year with the full meeting schedule (e.g.
boh-meeting-schedule-2026.pdf), approved by the board the prior October.
This module downloads that PDF and regex-parses date/time lines out of it,
then separately checks their agendas/minutes index page for links that can
be matched to those dates.

Expect to update `schedule_pdf_url_pattern` in config/sources.yaml (or this
module, if the naming convention changes) once SNHD publishes each year's
schedule — historically approved in October for the following year.
"""

from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO

import requests
from bs4 import BeautifulSoup

from .base import Link, Meeting, ScrapeError

USER_AGENT = "health-docket/1.0"

# Matches lines like "January 22, 2026 at 9:00 a.m." or "November 19, 2026, 11:00 a.m."
DATE_TIME_RE = re.compile(
    r"([A-Z][a-z]+ \d{1,2}, \d{4})[,\s]+(?:at\s+)?(\d{1,2}:\d{2}\s*[ap]\.?m\.?)",
    re.IGNORECASE,
)


def _extract_schedule_pdf(pdf_bytes: bytes) -> list[tuple[str, str]]:
    """Returns list of (iso_date, iso_time) pairs found in the PDF text."""
    try:
        import pdfplumber
    except ImportError as e:
        raise ScrapeError("pdfplumber not installed — pip install pdfplumber") from e

    results = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    for date_str, time_str in DATE_TIME_RE.findall(text):
        try:
            d = datetime.strptime(date_str, "%B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            continue
        time_str = time_str.replace(".", "").strip().upper().replace(" ", "")
        try:
            t = datetime.strptime(time_str, "%I:%M%p").strftime("%H:%M")
        except ValueError:
            t = None
        results.append((d, t))

    return results


def _fetch_minutes_index(index_url: str) -> dict[str, str]:
    """Best-effort map of ISO date -> a page URL that likely covers it,
    based on link text containing a matching month/day/year. Returns {}
    on any failure rather than raising, since this is a nice-to-have."""
    try:
        resp = requests.get(index_url, headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
    except Exception:
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    mapping = {}
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        match = re.search(r"([A-Z][a-z]+ \d{1,2},? \d{4})", text)
        if not match:
            continue
        try:
            d = datetime.strptime(match.group(1).replace(",", ""), "%B %d %Y").strftime("%Y-%m-%d")
            mapping[d] = a["href"]
        except ValueError:
            continue
    return mapping


def scrape(source_cfg: dict) -> list[Meeting]:
    source_id = source_cfg["id"]
    year = datetime.now().year
    pdf_url = source_cfg["schedule_pdf_url_pattern"].format(year=year)

    try:
        resp = requests.get(pdf_url, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        raise ScrapeError(f"Could not download schedule PDF {pdf_url}: {e}") from e

    dated_times = _extract_schedule_pdf(resp.content)
    minutes_map = _fetch_minutes_index(source_cfg.get("minutes_index_url", ""))
    default_link = source_cfg.get("minutes_index_url")

    meetings = []
    for d, t in dated_times:
        links = []
        if d in minutes_map:
            links.append(Link("Meeting page", minutes_map[d]))
        elif default_link:
            links.append(Link("Agendas / minutes", default_link))

        meetings.append(
            Meeting(
                id=f"{source_id}-{d}",
                source_id=source_id,
                tier="local",
                date=d,
                time=t,
                title=source_cfg["name"],
                links=links,
            )
        )

    return meetings
