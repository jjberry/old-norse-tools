"""Orchestrate all extractors to build the SQLite database from PDFs."""

import json
import re
import sqlite3
from pathlib import Path

import click

from nion.db.schema import get_connection
from nion.extractors.grammar import extract_paradigms
from nion.extractors.glossary import extract_entries
from nion.extractors.reader import extract_annotations
from nion.morphology.generator import generate_forms, generate_strong_verb_forms

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
PDF_DIR  = DATA_DIR / "pdfs"
DB_PATH  = DATA_DIR / "nion.db"

# ---------------------------------------------------------------------------
# Phase 1 helpers
# ---------------------------------------------------------------------------

def _insert_paradigms(conn: sqlite3.Connection, paradigms: list[dict]) -> None:
    cur = conn.cursor()
    for p in paradigms:
        cur.execute(
            """
            INSERT INTO paradigms
                (paradigm_number, section, pos, gender, strength,
                 example_word, example_gloss, page_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p["paradigm_number"],
                p["section"],
                p.get("pos"),
                p.get("gender"),
                p.get("strength"),
                p.get("example_word"),
                p.get("example_gloss"),
                p.get("page_number"),
            ),
        )
        paradigm_id = cur.lastrowid
        for f in p.get("forms", []):
            cur.execute(
                """
                INSERT INTO paradigm_forms
                    (paradigm_id, case_, number, gender, person, mood, tense, form)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    paradigm_id,
                    f.get("case_"),
                    f.get("number"),
                    f.get("gender"),
                    f.get("person"),
                    f.get("mood"),
                    f.get("tense"),
                    f["form"],
                ),
            )
    conn.commit()


def _insert_entries(conn: sqlite3.Connection, entries: list[dict]) -> None:
    conn.executemany(
        """
        INSERT INTO entries
            (headword, headword_normalized, pos, gender, strength,
             definition, grammar_ref, principal_parts, text_refs, page_number)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                e["headword"],
                e["headword_normalized"],
                e["pos"],
                e.get("gender"),
                e.get("strength"),
                e.get("definition", ""),
                e.get("grammar_ref"),
                e.get("principal_parts"),
                e.get("text_refs"),
                e.get("page_number"),
            )
            for e in entries
        ],
    )
    conn.commit()


def _insert_annotations(conn: sqlite3.Connection, annotations: list[dict]) -> None:
    conn.executemany(
        """
        INSERT INTO annotations
            (text_id, line_number, surface_form, headword, pos,
             grammatical_tags, gloss, grammar_ref)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                a["text_id"],
                a.get("line_number"),
                a["surface_form"],
                a.get("headword"),
                a.get("pos"),
                a.get("grammatical_tags"),
                a.get("gloss"),
                a.get("grammar_ref"),
            )
            for a in annotations
        ],
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Phase 2 helpers: link entries to paradigms
# ---------------------------------------------------------------------------

# Patterns that extract an explicit paradigm-table number from a grammar_ref.
# The number appears in parentheses directly after the section, e.g.:
#   "3.1.8 (9)"   "3.1.8.(30)"   "3.3.9 (10)"
_NOUN_PARADIGM_RE = re.compile(r"3\.1\.8\s*[.(]\s*(\d+)\s*\)")
_ADJ_PARADIGM_RE  = re.compile(r"3\.3\.9\s*[.(]\s*(\d+)\s*\)")


def _infer_noun_paradigm(
    headword: str,
    gender: str | None,
    by_example: dict[tuple, int],
) -> int | None:
    """Guess paradigm id for a noun without an explicit grammar_ref number.

    Uses headword ending + gender to pick the most common paradigm for that
    inflection class.  Irregular nouns will get wrong forms, but this still
    produces useful output for the majority of regular words.
    """
    if gender == "m":
        if headword.endswith("i"):
            return by_example.get(("noun", "bardagi"))   # weak m
        if headword.endswith("r"):
            return by_example.get(("noun", "hestr"))     # strong m (most common)
    elif gender == "f":
        if headword.endswith("a"):
            return by_example.get(("noun", "saga"))      # weak f
        if headword.endswith("r"):
            return by_example.get(("noun", "heiðr"))     # strong f -r ending
        return by_example.get(("noun", "laug"))           # strong f zero ending
    elif gender == "n":
        if headword.endswith("a"):
            return by_example.get(("noun", "auga"))      # weak n
        return by_example.get(("noun", "orð"))            # strong n (most common)
    return None


def _infer_weak_verb_paradigm(
    headword: str,
    by_example: dict[tuple, int],
) -> int | None:
    """Guess paradigm id for a weak verb from its infinitive ending."""
    if headword.endswith("ja"):
        return by_example.get(("verb", "berja"))   # class 1: -ja infinitive
    if headword.endswith("na"):
        return by_example.get(("verb", "brenna"))  # class 3: -na infinitive
    if headword.endswith("a"):
        return by_example.get(("verb", "flakka"))  # class 2: -a infinitive (most common)
    return None


def _link_entries_to_paradigms(conn: sqlite3.Connection) -> int:
    """Set entries.paradigm_id using three strategies in priority order:

    1. Direct headword match against paradigms.example_word (reliable for the
       grammar's own example verbs/nouns like berja, flakka, hestr, …).
    2. Explicit paradigm-table number extracted from grammar_ref
       (e.g. "Gr 3.1.8 (9)" → paradigm 9 of section 3.1.8).
    3. Heuristic based on pos/gender/headword ending for entries with no
       explicit reference.

    Returns the number of entries that received a paradigm_id.
    """
    # Build lookup tables from the paradigms already in the DB.
    by_section_num: dict[tuple, int] = {}   # (section, paradigm_number) → id
    by_example: dict[tuple, int] = {}       # (pos, example_word) → id

    for row in conn.execute(
        "SELECT id, section, paradigm_number, pos, example_word FROM paradigms"
    ):
        by_section_num[(row["section"], row["paradigm_number"])] = row["id"]
        if row["example_word"]:
            by_example[(row["pos"], row["example_word"])] = row["id"]

    linked = 0
    for entry in conn.execute(
        "SELECT id, headword, pos, gender, strength, grammar_ref FROM entries"
    ):
        headword = entry["headword"]
        pos      = entry["pos"]
        gender   = entry["gender"]
        strength = entry["strength"]
        ref      = entry["grammar_ref"] or ""

        paradigm_id: int | None = None

        # Strategy 1: direct example-word match (covers the grammar's own entries)
        paradigm_id = by_example.get((pos, headword))

        # Strategy 2: explicit paradigm number in grammar_ref
        if not paradigm_id:
            m = _NOUN_PARADIGM_RE.search(ref)
            if m:
                paradigm_id = by_section_num.get(("3.1.8", m.group(1)))

        if not paradigm_id:
            m = _ADJ_PARADIGM_RE.search(ref)
            if m:
                paradigm_id = by_section_num.get(("3.3.9", m.group(1)))

        # Strategy 3: heuristic by pos/gender/headword ending
        if not paradigm_id:
            if pos == "noun":
                paradigm_id = _infer_noun_paradigm(headword, gender, by_example)
            elif pos == "verb" and strength == "weak":
                paradigm_id = _infer_weak_verb_paradigm(headword, by_example)

        if paradigm_id is not None:
            conn.execute(
                "UPDATE entries SET paradigm_id = ? WHERE id = ?",
                (paradigm_id, entry["id"]),
            )
            linked += 1

    conn.commit()
    return linked


# ---------------------------------------------------------------------------
# Phase 2 helpers: generate and insert inflected forms
# ---------------------------------------------------------------------------

def _generate_all_forms(conn: sqlite3.Connection) -> int:
    """Generate forms for every entry that has a paradigm_id.

    Clears the forms table first so this step is safe to re-run.
    Returns the total number of form rows inserted.
    """
    conn.execute("DELETE FROM forms")
    conn.commit()

    # Fetch all paradigm data up front to avoid repeated per-entry queries.
    paradigm_forms: dict[int, list[dict]] = {}
    for row in conn.execute("SELECT * FROM paradigm_forms ORDER BY paradigm_id, id"):
        paradigm_forms.setdefault(row["paradigm_id"], []).append(dict(row))

    paradigms: dict[int, dict] = {}
    for row in conn.execute("SELECT * FROM paradigms"):
        p = dict(row)
        p["forms"] = paradigm_forms.get(p["id"], [])
        paradigms[p["id"]] = p

    inserted = 0
    for entry in conn.execute(
        "SELECT id, headword, paradigm_id FROM entries WHERE paradigm_id IS NOT NULL"
    ):
        paradigm = paradigms.get(entry["paradigm_id"])
        if paradigm is None:
            continue

        forms = generate_forms(entry["headword"], paradigm)
        if not forms:
            continue

        conn.executemany(
            """
            INSERT INTO forms
                (form, form_normalized, entry_id, case_, number, gender, person, mood, tense)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f["form"],
                    f["form_normalized"],
                    entry["id"],
                    f.get("case_"),
                    f.get("number"),
                    f.get("gender"),
                    f.get("person"),
                    f.get("mood"),
                    f.get("tense"),
                )
                for f in forms
            ],
        )
        inserted += len(forms)

    conn.commit()

    # Strong verbs: generate from principal parts (past tense + full present).
    # This covers verbs not linked to a paradigm, and adds past forms to those
    # that are (paradigm generation only produces present forms for strong verbs).
    _INSERT_FORMS_SQL = """
        INSERT INTO forms
            (form, form_normalized, entry_id, case_, number, gender, person, mood, tense)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    sv_inserted = 0
    for entry in conn.execute(
        "SELECT id, headword, principal_parts FROM entries "
        "WHERE pos='verb' AND strength='strong' AND principal_parts IS NOT NULL"
    ):
        forms = generate_strong_verb_forms(entry["headword"], entry["principal_parts"])
        if not forms:
            continue
        conn.executemany(
            _INSERT_FORMS_SQL,
            [
                (
                    f["form"], f["form_normalized"], entry["id"],
                    f.get("case_"), f.get("number"), f.get("gender"),
                    f.get("person"), f.get("mood"), f.get("tense"),
                )
                for f in forms
            ],
        )
        sv_inserted += len(forms)

    conn.commit()
    inserted += sv_inserted
    return inserted


# ---------------------------------------------------------------------------
# Phase 2 helpers: function word table
# ---------------------------------------------------------------------------

# Annotations store mood="indic" for indicative forms, but our forms table
# (and function_words table) use mood=NULL for indicative — it's the default.
_MOOD_MAP = {"indic": None}


def _populate_function_words(conn: sqlite3.Connection) -> int:
    """Seed function_words from reader annotations.

    Deduplicates on (form_normalized, pos, case_, number, gender, person,
    mood, tense) — the full morphological fingerprint — keeping the entry
    with a headword when available.  Only inserts forms not already covered
    by the paradigm-generated forms table.

    Returns the number of rows inserted.
    """
    from nion.encoding import normalize_for_search

    conn.execute("DELETE FROM function_words")
    conn.commit()

    # Forms already covered by paradigm generation — skip those.
    # Coverage is keyed on (form_normalized, pos) so that a verb form covering
    # "ok" (normalized ók) does not suppress the conjunction "ok".
    covered = {
        (row["form_normalized"], row["pos"])
        for row in conn.execute(
            "SELECT DISTINCT f.form_normalized, e.pos "
            "FROM forms f JOIN entries e ON f.entry_id = e.id"
        )
    }

    # Collect annotations, deduplicate, prefer entries with headwords.
    seen: dict[tuple, dict] = {}

    for row in conn.execute(
        "SELECT surface_form, headword, pos, grammatical_tags, gloss FROM annotations"
    ):
        form     = row["surface_form"]
        form_norm = normalize_for_search(form)

        if (form_norm, row["pos"]) in covered:
            continue

        tags: dict = {}
        if row["grammatical_tags"]:
            try:
                tags = json.loads(row["grammatical_tags"])
            except json.JSONDecodeError:
                pass

        case_   = tags.get("case")
        number  = tags.get("number")
        gender  = tags.get("gender")
        person  = tags.get("person")
        raw_mood = tags.get("mood")
        mood    = _MOOD_MAP.get(raw_mood, raw_mood)
        tense   = tags.get("tense")

        key = (form_norm, row["pos"], case_, number, gender, person, mood, tense)

        existing = seen.get(key)
        if existing is None or (not existing["headword"] and row["headword"]):
            seen[key] = {
                "form":           form,
                "form_normalized": form_norm,
                "headword":       row["headword"],
                "pos":            row["pos"],
                "case_":          case_,
                "number":         number,
                "gender":         gender,
                "person":         person,
                "mood":           mood,
                "tense":          tense,
                "gloss":          row["gloss"],
            }

    if not seen:
        return 0

    conn.executemany(
        """
        INSERT INTO function_words
            (form, form_normalized, headword, pos,
             case_, number, gender, person, mood, tense, gloss)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                e["form"], e["form_normalized"], e["headword"], e["pos"],
                e["case_"], e["number"], e["gender"], e["person"],
                e["mood"], e["tense"], e["gloss"],
            )
            for e in seen.values()
        ],
    )
    conn.commit()
    return len(seen)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.command()
@click.option("--db",   default=str(DB_PATH),  show_default=True, help="Output database path")
@click.option("--pdfs", default=str(PDF_DIR),  show_default=True, help="Directory containing PDFs")
def main(db: str, pdfs: str) -> None:
    """Build the Old Norse database from the three NION PDFs."""
    db_path  = Path(db)
    pdf_dir  = Path(pdfs)

    grammar_pdf  = pdf_dir / "grammar.pdf"
    glossary_pdf = pdf_dir / "glossary.pdf"
    reader_pdf   = pdf_dir / "reader.pdf"

    for pdf in (grammar_pdf, glossary_pdf, reader_pdf):
        if not pdf.exists():
            raise click.ClickException(
                f"{pdf} not found. Run `make download` first."
            )

    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Always start fresh so schema changes take effect without manual migration.
    for suffix in ("", "-shm", "-wal"):
        p = db_path.with_suffix(db_path.suffix + suffix)
        p.unlink(missing_ok=True)
    click.echo(f"Building database at {db_path} ...")
    conn = get_connection(db_path)

    click.echo("  [1/3] Extracting grammar paradigms ...")
    paradigms = extract_paradigms(grammar_pdf)
    _insert_paradigms(conn, paradigms)
    click.echo(f"        {len(paradigms)} paradigms inserted.")

    click.echo("  [2/3] Extracting glossary entries ...")
    entries = extract_entries(glossary_pdf)
    _insert_entries(conn, entries)
    click.echo(f"        {len(entries)} entries inserted.")

    click.echo("  [3/3] Extracting reader annotations ...")
    annotations = extract_annotations(reader_pdf)
    _insert_annotations(conn, annotations)
    click.echo(f"        {len(annotations)} annotations inserted.")

    click.echo("  [4/5] Linking entries to paradigms and generating forms ...")
    linked = _link_entries_to_paradigms(conn)
    click.echo(f"        {linked} entries linked to paradigms.")
    total_forms = _generate_all_forms(conn)
    click.echo(f"        {total_forms} inflected forms generated (incl. strong verbs from principal parts).")

    click.echo("  [5/5] Populating function word fallback table ...")
    fw_count = _populate_function_words(conn)
    click.echo(f"        {fw_count} function word entries inserted.")

    click.echo("Done.")


if __name__ == "__main__":
    main()
