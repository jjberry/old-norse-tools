"""Orchestrate all extractors to build the SQLite database from PDFs."""

import sqlite3

import click
from pathlib import Path

from nion.db.schema import get_connection
from nion.extractors.grammar import extract_paradigms
from nion.extractors.glossary import extract_entries
from nion.extractors.reader import extract_annotations

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
PDF_DIR = DATA_DIR / "pdfs"
DB_PATH = DATA_DIR / "nion.db"


def _insert_paradigms(conn: sqlite3.Connection, paradigms: list[dict]) -> None:
    cur = conn.cursor()
    for p in paradigms:
        cur.execute(
            """
            INSERT INTO paradigms
                (paradigm_number, section, pos, gender, strength, example_word, example_gloss)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p["paradigm_number"],
                p["section"],
                p["pos"],
                p.get("gender"),
                p.get("strength"),
                p.get("example_word"),
                p.get("example_gloss"),
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
             definition, grammar_ref, principal_parts, text_refs)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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


@click.command()
@click.option("--db", default=str(DB_PATH), show_default=True, help="Output database path")
@click.option("--pdfs", default=str(PDF_DIR), show_default=True, help="Directory containing PDFs")
def main(db: str, pdfs: str) -> None:
    """Build the Old Norse database from the three NION PDFs."""
    db_path = Path(db)
    pdf_dir = Path(pdfs)

    grammar_pdf = pdf_dir / "grammar.pdf"
    glossary_pdf = pdf_dir / "glossary.pdf"
    reader_pdf = pdf_dir / "reader.pdf"

    for pdf in (grammar_pdf, glossary_pdf, reader_pdf):
        if not pdf.exists():
            raise click.ClickException(
                f"{pdf} not found. Run `make download` first."
            )

    db_path.parent.mkdir(parents=True, exist_ok=True)
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

    click.echo("Done.")


if __name__ == "__main__":
    main()
