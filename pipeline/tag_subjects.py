"""Subject tagging pipeline -- Task 8 of the build plan (design doc §8, §5's
pipeline stage table: "Tag subjects").

For every meeting that has real extracted_text (Task 7) but no AI subject
tags yet, asks Claude to identify which legislative_subjects apply and
writes meeting_subjects rows (tagged_by='ai').

legislative_subjects has no predefined taxonomy to seed from. Unlike
policy_areas (Congress's fixed 32-bucket list, Appendix B), the design spec
only defines "Legislative Subject" generically ("a finer-grained topic
beneath a Policy Area, e.g. Medicaid, Behavioral Health") and never points
to an enumerated list for it the way it does for policy_areas -- confirmed
by checking Appendix A/B/C (only the Policy Area taxonomy and the tracked
bodies list are enumerated there) and by api/routes/subjects.py's own
docstring: "legislative_subjects has zero rows today ... no real subject
taxonomy exists until Task 8." The spec's Risks section (§10) says as much
directly: subject-tagging accuracy is explicitly "unproven" and treated as
something to be learned empirically once real extracted text exists to tag
-- which is now, as of Task 7.

So this script creates the taxonomy AS IT TAGS: each call gives the model
the full policy_areas list plus every legislative_subjects row that
already exists (grouped by policy area), and asks it to either reuse an
existing subject by name or, only when nothing existing fits, propose a
new one scoped to a policy area. This converges over time -- earlier
meetings seed subjects like "Medicaid" or "Board Governance", later
meetings in the same policy area reuse them instead of creating near-
duplicate synonyms.

Per spec §5's failure-handling for this stage ("Below-threshold confidence
is stored, not discarded -- surfaced, not hidden, so a human can review
it"), every tag the model returns is stored regardless of confidence. This
script never filters by confidence; it only flags low-confidence tags in
its own printed output so a human skimming the run's log notices them.

A meeting_subjects row a human has already confirmed (tagged_by='human')
is never touched -- only tagged_by='ai' rows are replaced on a re-tag.

Usage:
    python3 pipeline/tag_subjects.py                       # tag every meeting with extracted text and no AI tags yet
    python3 pipeline/tag_subjects.py --force                # also re-tag meetings that already have AI tags
    python3 pipeline/tag_subjects.py --external-id house-ec-health-2026-06-25   # tag one specific meeting (testing)
    python3 pipeline/tag_subjects.py --limit 5               # cap how many meetings are tagged this run (cost control)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.db import ROOT, execute, query  # noqa: E402

MAX_TEXT_CHARS = 15000  # per-meeting extracted text sent to the model; keeps prompts (and cost) bounded
LOW_CONFIDENCE_FLAG = 0.5  # purely for this script's own printed output -- never filters what gets stored

TAGGING_CONTEXT = """\
You are identifying the legislative subjects covered by a government
meeting, for a dashboard that tracks health-policy meetings across
federal, state, and local bodies.

A "Policy Area" is one of Congress's 32 standard subject-matter buckets
(e.g. Health, Education) -- pick from the exact list given below, do not
invent one. A "Legislative Subject" is a finer-grained topic beneath a
Policy Area (e.g. Medicaid, Behavioral Health, Board Governance, within
Health). There is no fixed list of subjects: some already exist (given
below, grouped by policy area) and you should reuse one by its exact
existing name whenever it genuinely fits, rather than inventing a
near-duplicate synonym (e.g. reuse "Medicaid" rather than proposing
"Medicaid Program Integrity" for a meeting about Medicaid fraud oversight).
Only propose a new subject name when nothing existing actually fits.

Given the meeting title and extracted text below, identify 1-4 legislative
subjects it covers. For each one, give your own confidence (0.0-1.0) that
the tag is correct -- a plausible but uncertain guess should still be
included at a low confidence score rather than left out; a human will
review low-confidence tags, they are not discarded.

Respond as JSON only, no other text -- a list of objects:
[{"policy_area": "<exact name from the list>", "subject": "<name>",
  "description": "<one sentence, only when proposing a genuinely new subject; omit or leave blank when reusing an existing one>",
  "confidence": 0.0-1.0}]

If nothing in the text supports any real subject tag, respond with [].
"""


def _load_context():
    policy_areas = query("SELECT id, name FROM policy_areas ORDER BY sort_order")
    subjects = query(
        """SELECT ls.id, ls.name, ls.description, pa.name AS policy_area
           FROM legislative_subjects ls
           JOIN policy_areas pa ON pa.id = ls.policy_area_id
           ORDER BY pa.sort_order, ls.name"""
    )
    by_area: dict[str, list[str]] = {}
    for s in subjects:
        by_area.setdefault(s["policy_area"], []).append(s["name"] + (f" -- {s['description']}" if s["description"] else ""))
    existing_block = "\n".join(f"  {area}: {', '.join(names)}" for area, names in by_area.items()) or "  (none yet -- you are tagging the very first meeting)"
    areas_block = ", ".join(p["name"] for p in policy_areas)
    return policy_areas, areas_block, existing_block


def _meeting_text(meeting_id: int) -> str:
    docs = query(
        """SELECT label, extracted_text FROM meeting_documents
           WHERE meeting_id = ? AND extraction_status = 'extracted' AND extracted_text IS NOT NULL""",
        (meeting_id,),
    )
    chunks = [f"[{d['label'] or 'document'}]\n{d['extracted_text']}" for d in docs]
    text = "\n\n".join(chunks)
    return text[:MAX_TEXT_CHARS]


def _call_claude(client, title: str, text: str, areas_block: str, existing_block: str) -> list[dict] | None:
    prompt = (
        TAGGING_CONTEXT
        + f"\n\nValid Policy Areas (pick from these exactly): {areas_block}\n"
        + f"\nExisting Legislative Subjects by Policy Area (reuse these by exact name when they fit):\n{existing_block}\n"
        + f"\n\nMeeting title: {title}\n\nExtracted text:\n{text}\n"
    )
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[warn] could not parse model response as JSON:\n{raw}")
        return None
    if not isinstance(result, list):
        print(f"[warn] expected a JSON list, got: {raw}")
        return None
    return result


def _resolve_policy_area(name: str, policy_areas: list) -> int | None:
    for p in policy_areas:
        if p["name"].strip().lower() == (name or "").strip().lower():
            return p["id"]
    return None


def _resolve_subject(policy_area_id: int, name: str, description: str | None) -> int:
    name = name.strip()
    existing = query(
        "SELECT id FROM legislative_subjects WHERE policy_area_id = ? AND lower(name) = lower(?)",
        (policy_area_id, name),
    )
    if existing:
        return existing[0]["id"]
    return execute(
        "INSERT INTO legislative_subjects (policy_area_id, name, description) VALUES (?, ?, ?)",
        (policy_area_id, name, description or None),
    )


def _tag_meeting(client, meeting: dict, policy_areas: list, areas_block: str, existing_block: str) -> tuple[int, int]:
    tags = _call_claude(client, meeting["title"], meeting["text"], areas_block, existing_block)
    if tags is None:
        return 0, 0
    if not tags:
        print(f"  [{meeting['external_id']}] model found no subject to tag")
        return 0, 0

    # Re-tagging: clear this meeting's prior AI tags so a changed answer
    # doesn't leave stale rows alongside the new ones. Human-confirmed
    # tags (tagged_by='human') are never touched.
    execute(
        "DELETE FROM meeting_subjects WHERE meeting_id = ? AND tagged_by = 'ai'",
        (meeting["id"],),
    )

    now = datetime.now(timezone.utc).isoformat()
    stored = skipped = 0
    for tag in tags:
        area_id = _resolve_policy_area(tag.get("policy_area", ""), policy_areas)
        if area_id is None:
            print(f"  [warn] {meeting['external_id']}: model returned unknown policy_area {tag.get('policy_area')!r}, skipping this tag")
            skipped += 1
            continue
        subject_name = (tag.get("subject") or "").strip()
        if not subject_name:
            print(f"  [warn] {meeting['external_id']}: model returned an empty subject name, skipping this tag")
            skipped += 1
            continue
        subject_id = _resolve_subject(area_id, subject_name, tag.get("description"))

        # Never overwrite a human-confirmed tag for this (meeting, subject) pair.
        human_row = query(
            "SELECT 1 FROM meeting_subjects WHERE meeting_id = ? AND subject_id = ? AND tagged_by = 'human'",
            (meeting["id"], subject_id),
        )
        if human_row:
            print(f"  [skip] {meeting['external_id']}: {subject_name!r} already human-confirmed, leaving it alone")
            skipped += 1
            continue

        confidence = tag.get("confidence")
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = None

        execute(
            """INSERT OR REPLACE INTO meeting_subjects (meeting_id, subject_id, confidence, tagged_by, tagged_at)
               VALUES (?, ?, ?, 'ai', ?)""",
            (meeting["id"], subject_id, confidence, now),
        )
        flag = " [LOW CONFIDENCE]" if confidence is not None and confidence < LOW_CONFIDENCE_FLAG else ""
        print(f"  [ok] {meeting['external_id']}: {tag.get('policy_area')} / {subject_name} (confidence={confidence}){flag}")
        stored += 1

    return stored, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="also re-tag meetings that already have AI subject tags")
    parser.add_argument("--external-id", help="tag only this one meeting (by meetings.external_id), for testing")
    parser.add_argument("--limit", type=int, help="cap how many meetings are tagged this run")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set -- skipping subject tagging.", file=sys.stderr)
        sys.exit(1)
    try:
        import anthropic
    except ImportError:
        print("anthropic package not installed -- pip install anthropic", file=sys.stderr)
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key)

    where = ["md.extraction_status = 'extracted'", "md.extracted_text IS NOT NULL"]
    params: list = []
    if args.external_id:
        where.append("m.external_id = ?")
        params.append(args.external_id)
    if not args.force:
        where.append(
            "m.id NOT IN (SELECT meeting_id FROM meeting_subjects WHERE tagged_by = 'ai')"
        )

    meetings = query(
        f"""SELECT DISTINCT m.id, m.external_id, m.title
            FROM meetings m
            JOIN meeting_documents md ON md.meeting_id = m.id
            WHERE {' AND '.join(where)}
            ORDER BY m.id""",
        params,
    )
    if args.limit:
        meetings = meetings[: args.limit]

    if not meetings:
        print("No meetings need subject tagging (nothing with extracted text " + ("" if args.force else "and no AI tags yet ") + "matches).")
        return

    policy_areas, areas_block, existing_block = _load_context()
    print(f"{len(meetings)} meeting(s) to tag.\n")

    total_stored = total_skipped = 0
    for m in meetings:
        text = _meeting_text(m["id"])
        if not text:
            print(f"  [skip] {m['external_id']}: no extracted text found")
            continue
        stored, skipped = _tag_meeting(
            client,
            {"id": m["id"], "external_id": m["external_id"], "title": m["title"], "text": text},
            policy_areas,
            areas_block,
            existing_block,
        )
        total_stored += stored
        total_skipped += skipped
        # Refresh the existing-subjects context after each meeting so later
        # meetings in this same run see subjects just created by earlier ones.
        _, areas_block, existing_block = _load_context()

    print(f"\nDone. {total_stored} subject tag(s) stored, {total_skipped} skipped, across {len(meetings)} meeting(s).")


if __name__ == "__main__":
    main()
