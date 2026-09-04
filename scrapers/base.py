"""Shared types for every scraper module.

A scraper module exposes one function:

    def scrape(source_cfg: dict) -> list[Meeting]

`source_cfg` is the source's own entry from config/sources.yaml (already
resolved to a dict), so a scraper for a given `type` can serve multiple
sources with different parameters (e.g. two different Legistar clients).

Return only meetings you're confident are real and correctly dated. It's
always fine to return fewer than expected; it is never fine to invent a
date. scripts/run_scrapers.py upserts by `id` and will happily leave last
week's entry alone if this week's scrape comes back empty or fails.
"""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Link:
    label: str
    url: str

    def to_dict(self) -> dict:
        return {"label": self.label, "url": self.url}


@dataclass
class Meeting:
    id: str                # stable id, convention: f"{source_id}-{date}"
    source_id: str
    tier: str               # "federal" | "state" | "local"
    date: str                # ISO "YYYY-MM-DD" — required, never guessed
    title: str
    time: str | None = None  # "HH:MM" 24h, or None if unknown
    note: str | None = None
    links: list[Link] = field(default_factory=list)
    verified: bool = True    # False = scraper found a mention but isn't
                              # confident about the date/details; the
                              # renderer will visually flag these

    def to_dict(self, last_checked: str) -> dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "tier": self.tier,
            "date": self.date,
            "time": self.time,
            "title": self.title,
            "note": self.note,
            "links": [l.to_dict() if isinstance(l, Link) else l for l in self.links],
            "verified": self.verified,
            "last_checked": last_checked,
        }


class ScrapeError(Exception):
    """Raised by a scraper when it can't get a trustworthy result — the
    orchestrator logs this and moves on rather than failing the whole run."""
