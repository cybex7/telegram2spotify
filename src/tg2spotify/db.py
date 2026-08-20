"""SQLite state. Stdlib, one file, so every stage is resumable and auditable."""

import sqlite3
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
  msg_id            INTEGER PRIMARY KEY,
  date              TEXT,
  file              TEXT,
  file_present      INTEGER NOT NULL DEFAULT 0,
  mime              TEXT,
  duration_tg       INTEGER,
  tg_performer      TEXT,
  tg_title          TEXT,
  caption           TEXT,
  id3_artist        TEXT,
  id3_title         TEXT,
  id3_length_ms     INTEGER,
  clean_artist      TEXT,
  clean_title       TEXT,
  rules             TEXT,
  status            TEXT NOT NULL DEFAULT 'ingested',
  spotify_uri       TEXT,
  match_score       REAL,
  match_reason      TEXT
);
CREATE TABLE IF NOT EXISTS hypotheses (
  msg_id      INTEGER NOT NULL,
  rank        INTEGER NOT NULL,
  artist      TEXT,
  title       TEXT,
  source      TEXT,
  confidence  REAL,
  searched    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (msg_id, rank)
);
CREATE TABLE IF NOT EXISTS excluded (
  msg_id  INTEGER PRIMARY KEY,
  reason  TEXT,
  detail  TEXT
);
CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);
"""


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con
