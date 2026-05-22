"""Phase 3: analyze an Old Norse text, parsing each word against the database."""

import click
from pathlib import Path

from nion.db.schema import get_connection

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
DB_PATH = DATA_DIR / "nion.db"


@click.command()
@click.argument("text", required=False)
@click.option("--db", default=str(DB_PATH), show_default=True, help="Database path")
@click.option("--file", "input_file", type=click.Path(exists=True), help="Read text from file")
def main(text: str | None, db: str, input_file: str | None) -> None:
    """Parse an Old Norse text and display word-by-word morphological analysis."""
    if input_file:
        text = Path(input_file).read_text(encoding="utf-8")
    elif not text:
        raise click.UsageError("Provide TEXT argument or --file.")

    db_path = Path(db)
    if not db_path.exists():
        raise click.ClickException(f"Database not found at {db_path}. Run `nion-build` first.")

    conn = get_connection(db_path)

    # TODO: tokenize text, call parser.parse_form() on each token, display with rich
    click.echo("Analysis not yet implemented.")


if __name__ == "__main__":
    main()
