"""Capture documents -- Task 6 of the build plan (design doc §8, §5's
pipeline stage table: "Capture documents").

For every meeting_documents row with a source_file_url, downloads whatever
is actually at that URL and updates capture_status:
  - 'captured'   on a successful download
  - 'not_linked' on a 404, auth wall, or any other failure -- per spec §5's
    failure-handling rule for this stage: log the reason and move on,
    never retry forever. (A later scrape re-linking the source can flip a
    row back to 'linked' for this script to try again.)

Storage location is a call this task had to make: the design spec's
pipeline table only says "Files downloaded to storage," with no backend
named. This project already treats schema/config/data as git-repo-as-
source-of-truth (§5.1), and NFR2's cost estimate lumps "storage" into the
same $0 GitHub-free-tier bucket as everything else -- so captured files
are committed to the repo under data/documents/, not a separate cloud
storage account. If the corpus outgrows what's comfortable to commit,
moving to real object storage is a deliberate future step, not a default
this script takes on its own.

What "capture" means here, concretely: some source_file_url values point
straight at a PDF; others point at an HTML meeting-detail page instead of
a document, since the scrapers that produced them don't always
distinguish the two (see schema.sql's note on meeting_documents.doc_type).
This script downloads and stores whatever is actually there and records
its real content type in the filename's extension -- it does NOT parse an
HTML page looking for a nested PDF link. Teaching doc_type to split into a
real agenda/minutes/exhibit distinction depends on actually reading each
captured file, which is Task 7 (Extraction), not this one.

Usage:
    python3 pipeline/capture_documents.py               # capture every 'linked' row not yet captured
    python3 pipeline/capture_documents.py --retry-failed # also retry rows currently 'not_linked'
    python3 pipeline/capture_documents.py --force        # re-download even already-'captured' rows
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.db import ROOT, execute, query  # noqa: E402

USER_AGENT = "health-docket/1.0"
DOCUMENTS_DIR = ROOT / "data" / "documents"
TIMEOUT = 30

# Mapped by substring match against the response's Content-Type header.
# Order matters: checked top to bottom, first match wins.
EXTENSION_BY_CONTENT_TYPE = [
    ("pdf", "pdf"),
    ("html", "html"),
    ("plain", "txt"),
    ("msword", "doc"),
    ("wordprocessingml", "docx"),
]


def _extension_for(content_type: str, url: str) -> str:
    content_type = (content_type or "").lower()
    for needle, ext in EXTENSION_BY_CONTENT_TYPE:
        if needle in content_type:
            return ext
    # Fall back to whatever extension (if any) the URL itself ends in.
    path_ext = Path(urlparse(url).path).suffix.lstrip(".")
    if re.fullmatch(r"[a-zA-Z0-9]{1,5}", path_ext or ""):
        return path_ext.lower()
    return "bin"  # unknown binary -- still saved, just not sniffable by extension


def _capture_one(doc_id: int, url: str, dest_dir: Path) -> tuple[str, str]:
    """Attempt one download. Returns (new_capture_status, human-readable reason)."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as e:
        return "not_linked", f"request failed: {e}"

    if resp.status_code == 404:
        return "not_linked", "404 not found"
    if resp.status_code in (401, 403):
        return "not_linked", f"auth wall ({resp.status_code})"
    if not resp.ok:
        return "not_linked", f"HTTP {resp.status_code}"

    ext = _extension_for(resp.headers.get("Content-Type", ""), url)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{doc_id}.{ext}"
    dest_path.write_bytes(resp.content)
    return "captured", f"saved {dest_path.relative_to(ROOT)} ({len(resp.content)} bytes, {ext})"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--retry-failed", action="store_true", help="also retry rows currently 'not_linked'")
    parser.add_argument("--force", action="store_true", help="re-download even already-'captured' rows")
    args = parser.parse_args()

    statuses = ["linked"]
    if args.retry_failed:
        statuses.append("not_linked")
    if args.force:
        statuses.append("captured")
    placeholders = ",".join("?" for _ in statuses)

    rows = query(
        f"""
        SELECT md.id AS doc_id, md.source_file_url AS url, md.capture_status AS status,
               m.external_id AS external_id
        FROM meeting_documents md
        JOIN meetings m ON m.id = md.meeting_id
        WHERE md.capture_status IN ({placeholders})
        ORDER BY md.id
        """,
        statuses,
    )

    if not rows:
        print("No meeting_documents rows to process (nothing in states: " + ", ".join(statuses) + ").")
        return

    captured = failed = 0
    for row in rows:
        dest_dir = DOCUMENTS_DIR / row["external_id"]
        new_status, reason = _capture_one(row["doc_id"], row["url"], dest_dir)
        execute("UPDATE meeting_documents SET capture_status = ? WHERE id = ?", (new_status, row["doc_id"]))
        tag = "OK" if new_status == "captured" else "FAILED"
        print(f"  [{tag}] doc {row['doc_id']} ({row['external_id']}): {reason}")
        if new_status == "captured":
            captured += 1
        else:
            failed += 1

    print(f"Done. {captured} captured, {failed} not_linked, out of {len(rows)} attempted.")


if __name__ == "__main__":
    main()
