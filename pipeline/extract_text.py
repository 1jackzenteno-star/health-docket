"""Extraction pipeline -- Task 7 of the build plan (design doc §8, §5's
pipeline stage table: "Extract").

For every meeting_documents row that's been captured (Task 6) but not yet
extracted, reads the actual file under data/documents/ and fills in
extracted_text + extraction_status:
  - 'extracted' when real text was pulled out of the file
  - 'failed'    when it couldn't be, with the reason printed and the prior
    state left alone (spec §5: "leaves the prior state's UI badge in
    place -- never a blank guess")

Two file types are handled, matching what Task 6 actually captures:

  .html / .htm  -- parsed with BeautifulSoup, visible text pulled out with
                   whitespace collapsed. This is the common case today: all
                   25 documents Task 6 captured are HTML (see pm/STATUS.md's
                   note on the two sources whose captures are a generic
                   listing page rather than a per-meeting page -- this
                   script still extracts real text from those, it just
                   won't be meeting-specific text; that's Task 6's finding,
                   not something this script can fix).

  .pdf          -- read with pdfplumber (already a project dependency),
                   concatenating each page's embedded text layer.

What this script deliberately does NOT do yet: OCR a scanned/image-only PDF
(one with no embedded text layer). The design spec's pipeline table calls
this stage "Extract (OCR + LLM)" and the natural way to add OCR here, given
this project's existing conventions, is Claude's vision API (the same
anthropic dependency scripts/generate_briefing.py already uses) rather than
a new local OCR toolchain -- but no document in the corpus today is
actually a scanned image (every captured PDF-shaped case in testing has an
embedded text layer, and today's real captures are all HTML), so there is
nothing real to build and verify that fallback against yet. Rather than
ship an OCR code path that has never been exercised against a real scanned
document, a PDF with no extractable text is treated as a clean 'failed'
case with that reason logged -- exactly the spec's own failure-handling
rule -- and the OCR fallback is left as a documented next step (see
pm/STATUS.md Known issues) for whenever a real scanned document shows up.

Usage:
    python3 pipeline/extract_text.py            # extract every 'pending' captured row
    python3 pipeline/extract_text.py --force     # also re-extract 'extracted'/'failed' rows
"""
from __future__ import annotations

import argparse
from pathlib import Path

from bs4 import BeautifulSoup

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.db import ROOT, execute, query  # noqa: E402

DOCUMENTS_DIR = ROOT / "data" / "documents"
MIN_PDF_TEXT_CHARS = 20  # below this, treat a PDF as having no real embedded text


def _find_captured_file(external_id: str, doc_id: int) -> Path | None:
    """capture_documents.py doesn't record a path column -- files live at a
    known convention (data/documents/<external_id>/<doc_id>.<ext>), so find
    whichever extension actually got captured."""
    matches = list((DOCUMENTS_DIR / external_id).glob(f"{doc_id}.*")) if (DOCUMENTS_DIR / external_id).exists() else []
    return matches[0] if matches else None


def _extract_html(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    if not text:
        return "failed", "HTML parsed but no visible text found"
    return "extracted", text


def _extract_pdf(path: Path) -> tuple[str, str]:
    try:
        import pdfplumber
    except ImportError:
        return "failed", "pdfplumber not installed -- pip install pdfplumber"

    try:
        with pdfplumber.open(path) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
    except Exception as e:
        return "failed", f"could not open/parse PDF: {e}"

    text = "\n\n".join(p.strip() for p in pages if p.strip())
    if len(text) < MIN_PDF_TEXT_CHARS:
        return "failed", (
            "no embedded text layer found (likely a scanned image PDF) -- "
            "OCR fallback not yet implemented, see pm/STATUS.md Known issues"
        )
    return "extracted", text


def _extract_one(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower().lstrip(".")
    if ext in ("html", "htm"):
        return _extract_html(path)
    if ext == "pdf":
        return _extract_pdf(path)
    return "failed", f"unsupported file type for extraction: .{ext}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="also re-extract rows already 'extracted' or 'failed'")
    args = parser.parse_args()

    statuses = ["pending"] + (["extracted", "failed"] if args.force else [])
    placeholders = ",".join("?" for _ in statuses)

    rows = query(
        f"""
        SELECT md.id AS doc_id, m.external_id AS external_id
        FROM meeting_documents md
        JOIN meetings m ON m.id = md.meeting_id
        WHERE md.capture_status = 'captured' AND md.extraction_status IN ({placeholders})
        ORDER BY md.id
        """,
        statuses,
    )

    if not rows:
        print("No captured meeting_documents rows to extract (nothing in states: " + ", ".join(statuses) + ").")
        return

    extracted = failed = 0
    for row in rows:
        path = _find_captured_file(row["external_id"], row["doc_id"])
        if path is None:
            status, payload = "failed", f"no captured file found under data/documents/{row['external_id']}/{row['doc_id']}.*"
        else:
            # payload is the extracted text on success, or a failure reason string on failure
            status, payload = _extract_one(path)

        extracted_text = payload if status == "extracted" else None
        log_line = f"{len(payload)} chars from {path.relative_to(ROOT)}" if status == "extracted" else payload

        execute(
            "UPDATE meeting_documents SET extraction_status = ?, extracted_text = ? WHERE id = ?",
            (status, extracted_text, row["doc_id"]),
        )
        tag = "OK" if status == "extracted" else "FAILED"
        print(f"  [{tag}] doc {row['doc_id']} ({row['external_id']}): {log_line}")
        if status == "extracted":
            extracted += 1
        else:
            failed += 1

    print(f"Done. {extracted} extracted, {failed} failed, out of {len(rows)} attempted.")


if __name__ == "__main__":
    main()
