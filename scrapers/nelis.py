"""Scraper for the Nevada Legislature's NELIS system (leg.state.nv.us).

NELIS's meeting-list pages render their content client-side — a plain
`requests.get()` returns mostly navigation chrome, no meeting rows (this
was confirmed while building this repo: see README "known limitations").
So this module drives a real headless browser with Playwright instead.

This is the least-tested scraper in the repo — the environment that wrote
it couldn't reach leg.state.nv.us at all (sandboxed network), so the CSS
selectors below are a best guess from the page's visible structure, not a
verified spec. Expect to open the page's dev tools and adjust selectors
after the first real run.

Setup: `pip install playwright` then `playwright install chromium`.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from .base import Link, Meeting, ScrapeError

BASE = "https://www.leg.state.nv.us"


def scrape(source_cfg: dict) -> list[Meeting]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ScrapeError(
            "playwright not installed — pip install playwright && "
            "playwright install chromium"
        ) from e

    interim = source_cfg["interim"]
    committee_id = source_cfg["committee_id"]
    source_id = source_cfg["id"]
    url = f"{BASE}/App/InterimCommittee/REL/{interim}/Committee/{committee_id}/Meetings"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, timeout=30000, wait_until="networkidle")
            html = page.content()
            browser.close()
    except Exception as e:
        raise ScrapeError(f"Playwright navigation to {url} failed: {e}") from e

    soup = BeautifulSoup(html, "html.parser")
    meetings: list[Meeting] = []

    # NELIS meeting rows are typically links whose text is a date like
    # "Tuesday, August 11, 2026 9:00 AM" pointing at a /Meeting/<id> page.
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/Meeting/" not in href:
            continue
        text = a.get_text(strip=True)
        d = _parse_nelis_date(text)
        if not d:
            continue

        full_url = href if href.startswith("http") else f"{BASE}{href}"
        meetings.append(
            Meeting(
                id=f"{source_id}-{d}",
                source_id=source_id,
                tier="state",
                date=d,
                title=source_cfg["name"],
                links=[Link("Agenda / minutes / exhibits", full_url)],
                verified=False,  # selectors unverified — see module docstring
            )
        )

    return meetings


def _parse_nelis_date(text: str) -> str | None:
    """Parse strings like 'Tuesday, August 11, 2026 9:00 AM' -> '2026-08-11'."""
    import re
    from datetime import datetime

    match = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None
