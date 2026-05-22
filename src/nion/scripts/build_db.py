"""Orchestrate all extractors to build the SQLite database from PDFs."""

import click
from pathlib import Path

from nion.db.schema import get_connection

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
PDF_DIR = DATA_DIR / "pdfs"
DB_PATH = DATA_DIR / "nion.db"


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

    click.echo(f"Building database at {db_path} ...")
    conn = get_connection(db_path)

    click.echo("  [1/3] Extracting grammar paradigms ...")
    # TODO: from nion.extractors.grammar import extract_paradigms

    click.echo("  [2/3] Extracting glossary entries ...")
    # TODO: from nion.extractors.glossary import extract_entries

    click.echo("  [3/3] Extracting reader annotations ...")
    # TODO: from nion.extractors.reader import extract_annotations

    click.echo("Done.")


if __name__ == "__main__":
    main()
