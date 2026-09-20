"""Briefing generation pipeline -- Task 9 of the build plan (design doc §8,
§5's pipeline stage table: "Generate briefings").

The prototype's scripts/generate_briefing.py wrote a "why this matters"
note from just a meeting's title, date, and a source-level relevance tag
list -- it never had real agenda/minutes content to work from, because
Task 6 (capture) and Task 7 (extraction) didn't exist yet. That gap is
exactly what the schema's own comment on `briefings.model_version` flags:
"a real gap against NFR3, not a migration artifact." This script closes
it: for every meeting that has real extracted_text (Task 7) and at least
one subject tag (Task 8), it asks Claude to write a note grounded in the
actual captured document content, and records model_version so the note
is traceable to a specific model/run (NFR3).

Relevance gating is unchanged from the prototype's approach, because the
schema still doesn't have anywhere to record "checked, not relevant" --
`briefings` has no boolean column for it, and GET /api/policy-areas/{slug}
/attention (api/routes/policy_areas.py) filters on `br.id IS NOT NULL`,
i.e. a meeting shows up there exactly when it has a briefings row and not
otherwise. So a meeting judged not relevant to NNPH's admin functions
(finance, HR, IT/data systems, grants & contract compliance, board
governance) simply gets no row, same as before -- it isn't written and
then hidden, there's nothing to hide.

Confidence carries real signal now, not just a constant. Task 6's own
finding (pm/STATUS.md Known issues) was that Southern Nevada Health
District's and Senate HELP Committee's captured documents are a generic
meetings-listing page, not a page specific to any one meeting -- so
extracted_text can be real, substantive prose that is nonetheless NOT
actually about the meeting it's attached to. The model is asked to
notice this (the text won't mention this meeting's specific date/agenda
items) and mark confidence 'unverified' when it does, same as the
prototype marked 'unverified' for a title-only note -- the reason changes
(generic source document vs. no document at all) but the signal means the
same thing: "don't take this note as reflecting real per-meeting detail."

Usage:
    python3 pipeline/generate_briefings.py                    # generate for every eligible meeting without a briefing yet
    python3 pipeline/generate_briefings.py --force              # also regenerate meetings that already have one
    python3 pipeline/generate_briefings.py --external-id house-ec-health-2026-06-25   # one meeting (testing)
    python3 pipeline/generate_briefings.py --limit 5             # cap how many meetings run this call (cost control)
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
MODEL = "claude-sonnet-4-5"

BRIEFING_CONTEXT = """\
You are writing a one-paragraph "why this matters" note for a dashboard
read by an administrator at Northern Nevada Public Health (NNPH), a
Nevada county health district. He handles FINANCE, IT/data systems, and
HR for the district -- not clinical programs. His board (the Washoe
County District Board of Health) has the same statutory role as the
other bodies tracked here, so anything about board governance, board
authority, or funding mechanisms for local health districts is directly
relevant to him even when framed at the state or federal level.

You are given the meeting's real captured document text below, plus the
legislative subjects it's already been tagged with. For this meeting,
make TWO SEPARATE judgments -- do not let one influence the other:

1. RELEVANCE: is this meeting's topic -- judged from its title, body,
   tier, and tagged subjects -- genuinely about district-level finance,
   HR, IT, grants/contract compliance, board governance, or general
   HHS/public-health funding policy? Judge this the same way whether or
   not the captured text turned out to be specific to this meeting -- a
   meeting on a genuinely relevant topic stays relevant even when the
   only document available is a generic committee page, exactly as it
   would if you had no document at all and only a title to go on. Only
   mark not-relevant when the TOPIC itself doesn't reach the bar (a
   purely clinical/programmatic matter with no funding, staffing, or
   compliance angle) -- never because the source document was generic.
2. CONFIDENCE: separately, judge the TEXT itself -- does it actually read
   like content specific to THIS meeting (real agenda items, real
   discussion, a real date match), or does it read like a generic page
   (e.g. a standing meetings-listing or committee homepage) that doesn't
   describe this particular meeting's business? Mark "verified" only for
   genuinely meeting-specific text; mark "unverified" for a generic page
   -- but still write your best-effort note from whatever signal is
   available (title, date, tagged subjects) when it's relevant, and say
   in the note that the underlying document wasn't meeting-specific.

Write ONE paragraph (2-4 sentences) for the note, explaining the
connection concretely -- cite something specific from the actual text
when it's genuinely meeting-specific; when the text is only generic,
reason instead from the meeting's title/body/committee/tagged subjects,
same as you would from a title alone.

Respond as JSON only, no other text:
{"relevant": true|false, "confidence": "verified"|"unverified",
 "relevance_tags": ["budget"|"hr"|"it"|"grants"|"compliance"|"board-authority"|"hhs-policy"],
 "note": "..."}

If relevant is false, note should briefly say why this doesn't reach the
admin-relevance bar; it will not be shown on the dashboard's attention
list, since a meeting with no briefings row doesn't appear there.
"""


def _meeting_text(meeting_id: int) -> str:
    docs = query(
        """SELECT label, extracted_text FROM meeting_documents
           WHERE meeting_id = ? AND extraction_status = 'extracted' AND extracted_text IS NOT NULL""",
        (meeting_id,),
    )
    chunks = [f"[{d['label'] or 'document'}]\n{d['extracted_text']}" for d in docs]
    return "\n\n".join(chunks)[:MAX_TEXT_CHARS]


def _meeting_subjects(meeting_id: int) -> list[str]:
    rows = query(
        """SELECT ls.name, pa.name AS policy_area, ms.confidence
           FROM meeting_subjects ms
           JOIN legislative_subjects ls ON ls.id = ms.subject_id
           JOIN policy_areas pa ON pa.id = ls.policy_area_id
           WHERE ms.meeting_id = ?
           ORDER BY ms.confidence DESC""",
        (meeting_id,),
    )
    return [f"{r['name']} ({r['policy_area']})" for r in rows]


def _call_claude(client, meeting: dict) -> dict | None:
    prompt = (
        BRIEFING_CONTEXT
        + "\n\nMeeting:\n"
        + json.dumps(
            {
                "title": meeting["title"],
                "date": meeting["occurred_at"],
                "body": meeting["body_name"],
                "tier": meeting["tier_key"],
                "tagged_subjects": meeting["subjects"],
            },
            indent=2,
        )
        + "\n\nCaptured document text:\n"
        + (meeting["text"] or "(no extracted text available)")
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"[warn] could not parse model response as JSON for {meeting['external_id']}:\n{raw}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="also regenerate meetings that already have a briefing")
    parser.add_argument("--external-id", help="generate for only this one meeting (by meetings.external_id), for testing")
    parser.add_argument("--limit", type=int, help="cap how many meetings are processed this run")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set -- skipping briefing generation.", file=sys.stderr)
        sys.exit(1)
    try:
        import anthropic
    except ImportError:
        print("anthropic package not installed -- pip install anthropic", file=sys.stderr)
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key)

    where = [
        "m.id IN (SELECT meeting_id FROM meeting_documents WHERE extraction_status = 'extracted' AND extracted_text IS NOT NULL)",
        "m.id IN (SELECT meeting_id FROM meeting_subjects)",
    ]
    params: list = []
    if args.external_id:
        where.append("m.external_id = ?")
        params.append(args.external_id)
    if not args.force:
        where.append("m.id NOT IN (SELECT meeting_id FROM briefings)")

    meetings = query(
        f"""SELECT DISTINCT m.id, m.external_id, m.title, m.occurred_at, b.name AS body_name, b.tier_key
            FROM meetings m
            JOIN bodies b ON b.id = m.body_id
            WHERE {' AND '.join(where)}
            ORDER BY m.id""",
        params,
    )
    if args.limit:
        meetings = meetings[: args.limit]

    if not meetings:
        print("No meetings need a briefing (nothing eligible " + ("" if args.force else "and without one yet ") + "matches).")
        return

    print(f"{len(meetings)} meeting(s) to brief.\n")

    written = skipped_not_relevant = skipped_no_parse = 0
    for m in meetings:
        text = _meeting_text(m["id"])
        subjects = _meeting_subjects(m["id"])
        result = _call_claude(
            client,
            {
                "external_id": m["external_id"],
                "title": m["title"],
                "occurred_at": m["occurred_at"],
                "body_name": m["body_name"],
                "tier_key": m["tier_key"],
                "subjects": subjects,
                "text": text,
            },
        )
        if result is None:
            skipped_no_parse += 1
            continue
        if not result.get("relevant", False):
            print(f"  [skip] {m['external_id']}: not relevant enough -- {result.get('note', '')[:80]}")
            skipped_not_relevant += 1
            if args.force:
                execute("DELETE FROM briefings WHERE meeting_id = ?", (m["id"],))
            continue

        if args.force:
            execute("DELETE FROM briefings WHERE meeting_id = ?", (m["id"],))

        now = datetime.now(timezone.utc).isoformat()
        execute(
            """INSERT INTO briefings (meeting_id, note_text, confidence, model_version, relevance_tags, generated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                m["id"],
                result.get("note", ""),
                result.get("confidence", "unverified"),
                MODEL,
                json.dumps(result.get("relevance_tags", [])),
                now,
            ),
        )
        print(f"  [ok]   {m['external_id']}: added ({result.get('confidence')})")
        written += 1

    print(
        f"\nDone. {written} briefing(s) written, {skipped_not_relevant} skipped as not relevant, "
        f"{skipped_no_parse} skipped on a bad model response, out of {len(meetings)} meeting(s) attempted."
    )


if __name__ == "__main__":
    main()
