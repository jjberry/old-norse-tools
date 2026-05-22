"""SQLite schema definition and connection helper."""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Numbered paradigm tables extracted from the grammar PDF
CREATE TABLE IF NOT EXISTS paradigms (
    id               INTEGER PRIMARY KEY,
    paradigm_number  TEXT NOT NULL,   -- e.g. "11"
    section          TEXT NOT NULL,   -- e.g. "3.1.7"
    pos              TEXT NOT NULL,   -- noun | verb | adjective | pronoun | adverb
    gender           TEXT,            -- m | f | n
    strength         TEXT,            -- strong | weak
    example_word     TEXT,            -- e.g. "laug"
    example_gloss    TEXT             -- e.g. "bath"
);

-- Individual cells of a paradigm table
CREATE TABLE IF NOT EXISTS paradigm_forms (
    id           INTEGER PRIMARY KEY,
    paradigm_id  INTEGER NOT NULL REFERENCES paradigms(id),
    case_        TEXT,    -- nom | acc | gen | dat
    number       TEXT,    -- sg | pl
    gender       TEXT,    -- m | f | n  (adjectives only)
    person       TEXT,    -- 1 | 2 | 3  (verbs only)
    mood         TEXT,    -- indic | subj | imp  (verbs only)
    tense        TEXT,    -- pres | past  (verbs only)
    form         TEXT NOT NULL
);

-- Glossary headwords linked to paradigms
CREATE TABLE IF NOT EXISTS entries (
    id                  INTEGER PRIMARY KEY,
    headword            TEXT NOT NULL,
    headword_normalized TEXT NOT NULL,   -- search-normalized (ascii, lowercase)
    pos                 TEXT NOT NULL,
    gender              TEXT,
    strength            TEXT,
    paradigm_id         INTEGER REFERENCES paradigms(id),
    definition          TEXT NOT NULL,
    grammar_ref         TEXT,            -- raw Gr reference string e.g. "Gr 3.1.8 (1)"
    principal_parts     TEXT,            -- JSON array for verbs
    text_refs           TEXT             -- JSON array of text+line refs e.g. ["I:31", "VI:5"]
);

CREATE INDEX IF NOT EXISTS idx_entries_headword_normalized
    ON entries(headword_normalized);

-- Pre-generated inflected form → entry lookup table
CREATE TABLE IF NOT EXISTS forms (
    id      INTEGER PRIMARY KEY,
    form    TEXT NOT NULL,
    form_normalized TEXT NOT NULL,
    entry_id INTEGER NOT NULL REFERENCES entries(id),
    case_   TEXT,
    number  TEXT,
    gender  TEXT,
    person  TEXT,
    mood    TEXT,
    tense   TEXT
);

CREATE INDEX IF NOT EXISTS idx_forms_form_normalized
    ON forms(form_normalized);

-- Gold-standard morphological annotations from Reader Text I
CREATE TABLE IF NOT EXISTS annotations (
    id               INTEGER PRIMARY KEY,
    text_id          TEXT NOT NULL,        -- e.g. "I"
    line_number      INTEGER,
    surface_form     TEXT NOT NULL,
    headword         TEXT,
    pos              TEXT,
    grammatical_tags TEXT,                 -- JSON object
    gloss            TEXT,
    grammar_ref      TEXT
);

-- Lookup table for function words and irregular forms not covered by paradigm
-- generation.  Seeded from reader annotations; can be supplemented by hand.
CREATE TABLE IF NOT EXISTS function_words (
    id               INTEGER PRIMARY KEY,
    form             TEXT NOT NULL,
    form_normalized  TEXT NOT NULL,
    headword         TEXT,
    pos              TEXT,
    case_            TEXT,
    number           TEXT,
    gender           TEXT,
    person           TEXT,
    mood             TEXT,
    tense            TEXT,
    gloss            TEXT,
    source           TEXT NOT NULL DEFAULT 'annotation'  -- annotation | manual
);

CREATE INDEX IF NOT EXISTS idx_function_words_normalized
    ON function_words(form_normalized);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Return a UTF-8 connection with foreign keys and WAL enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    _ensure_meta(conn)
    return conn


def _ensure_meta(conn: sqlite3.Connection) -> None:
    existing = conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
