-- Health Docket database schema — Task 1 of the build plan (design doc §4, §8).
-- SQLite. This is purely additive: nothing in config/, scrapers/, scripts/,
-- or templates/ reads from or writes to this yet. sources.yaml and the two
-- data/*.json files stay the live source of truth for the weekly-refresh
-- workflow until a later task (§8, Task 6+) actually wires the pipeline to
-- this database. db/health_docket.db itself is gitignored — every
-- environment (or CI) rebuilds it by running db/migrate.py against the
-- files already in the repo.

PRAGMA foreign_keys = ON;

CREATE TABLE tiers (
  key         TEXT PRIMARY KEY,      -- federal / state / local
  sort_index  TEXT,                  -- "I." / "II." / "III." from sources.yaml
  label       TEXT NOT NULL,
  description TEXT
);

CREATE TABLE policy_areas (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL UNIQUE,
  sort_order INTEGER NOT NULL
);

CREATE TABLE legislative_subjects (
  id             INTEGER PRIMARY KEY,
  policy_area_id INTEGER NOT NULL REFERENCES policy_areas(id),
  name           TEXT NOT NULL,
  description    TEXT,
  UNIQUE (policy_area_id, name)
);

CREATE TABLE bodies (
  id             INTEGER PRIMARY KEY,
  slug           TEXT NOT NULL UNIQUE,     -- matches sources.yaml's `id` today
  name           TEXT NOT NULL,
  tier_key       TEXT NOT NULL REFERENCES tiers(key),
  scraper_type   TEXT NOT NULL,            -- matches sources.yaml's `type`
  scraper_config TEXT,                     -- JSON: the type-specific fields
                                            -- (committee_system_code, legistar_client, etc.)
  watch_url      TEXT,
  active         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE body_admin_tags (
  body_id INTEGER NOT NULL REFERENCES bodies(id),
  tag     TEXT NOT NULL,
  PRIMARY KEY (body_id, tag)
);

CREATE TABLE meetings (
  id            INTEGER PRIMARY KEY,
  body_id       INTEGER NOT NULL REFERENCES bodies(id),
  -- NOTE: today's meetings.json `id` (e.g. "nv-jisc-hhs-2026-01-06") is a
  -- locally-constructed slug (source_id + date), not a source system's own
  -- event ID. It's stored here as external_id because it's the only stable
  -- per-meeting identifier that exists today, and it's what makes this
  -- migration idempotent to re-run. It is NOT yet what design doc §4
  -- described (a Legistar/NELIS/Congress.gov event ID) — that upgrade
  -- happens if/when a scraper starts returning one.
  external_id   TEXT NOT NULL UNIQUE,
  title         TEXT NOT NULL,
  occurred_at   TEXT NOT NULL,             -- ISO date (meetings.json `date`)
  occurred_time TEXT,                      -- meetings.json `time`, nullable
  status        TEXT NOT NULL DEFAULT 'scheduled',
  note          TEXT,                      -- meetings.json `note`
  verified      INTEGER NOT NULL DEFAULT 0,
  last_checked  TEXT
);

CREATE TABLE meeting_documents (
  id                INTEGER PRIMARY KEY,
  meeting_id        INTEGER NOT NULL REFERENCES meetings(id),
  label             TEXT,                  -- today's links[].label as scraped
  -- NOTE: current data does not actually distinguish agenda vs. minutes as
  -- separate documents — most sources publish one combined link ("Agenda /
  -- minutes / exhibits"). doc_type stays 'unspecified' for migrated rows
  -- rather than guessing a split the source data doesn't support; a real
  -- agenda/minutes split becomes possible once Task 6 (document capture)
  -- actually fetches and looks at what's behind each link.
  doc_type          TEXT NOT NULL DEFAULT 'unspecified',
  source_file_url   TEXT NOT NULL,
  capture_status    TEXT NOT NULL DEFAULT 'linked',   -- these rows already have a URL
  extraction_status TEXT NOT NULL DEFAULT 'pending',
  extracted_text    TEXT
);

CREATE TABLE meeting_subjects (
  meeting_id INTEGER NOT NULL REFERENCES meetings(id),
  subject_id INTEGER NOT NULL REFERENCES legislative_subjects(id),
  confidence REAL,
  tagged_by  TEXT NOT NULL DEFAULT 'ai',
  tagged_at  TEXT,
  PRIMARY KEY (meeting_id, subject_id)
);

CREATE TABLE briefings (
  id             INTEGER PRIMARY KEY,
  meeting_id     INTEGER NOT NULL REFERENCES meetings(id),
  note_text      TEXT NOT NULL,
  -- NOTE: design doc §4 specified confidence as REAL (0-1). Real
  -- briefing.json data stores a categorical string ("unverified") instead
  -- — every existing row says the same thing, so there's no real 0-1
  -- signal to migrate. Kept as TEXT here rather than force-converting to a
  -- number that would imply precision the current briefings don't have.
  confidence     TEXT,
  -- NOTE: model_version was specified in §4 for exactly this purpose (NFR3,
  -- AI-claim traceability) but scripts/generate_briefing.py does not
  -- currently record which model/prompt produced a note — only
  -- generated_at. All migrated rows have model_version = NULL. This is a
  -- real gap against NFR3, not a migration artifact; closing it means
  -- updating generate_briefing.py to start writing it going forward.
  model_version  TEXT,
  relevance_tags TEXT,                     -- JSON array, e.g. ["compliance","medicaid"]
  generated_at   TEXT NOT NULL
);

CREATE TABLE focus_areas (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE focus_area_policy_areas (
  focus_area_id  INTEGER NOT NULL REFERENCES focus_areas(id),
  policy_area_id INTEGER NOT NULL REFERENCES policy_areas(id),
  PRIMARY KEY (focus_area_id, policy_area_id)
);

CREATE INDEX idx_meetings_body_occurred    ON meetings(body_id, occurred_at);
CREATE INDEX idx_meeting_documents_meeting ON meeting_documents(meeting_id);
CREATE INDEX idx_briefings_meeting         ON briefings(meeting_id);
CREATE INDEX idx_meeting_subjects_subject  ON meeting_subjects(subject_id);
