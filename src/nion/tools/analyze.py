"""Phase 3: analyze an Old Norse text, parsing each word against the database."""

from __future__ import annotations

import re
from pathlib import Path

import click
from rich.console import Console
from rich.text import Text

from nion.db.schema import get_connection
from nion.morphology.parser import parse_form

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
DB_PATH = DATA_DIR / "nion.db"

console = Console()

_POS_STYLE: dict[str, tuple[str, str]] = {
    "noun":        ("noun",  "cyan"),
    "verb":        ("verb",  "green"),
    "adjective":   ("adj",   "yellow"),
    "pronoun":     ("pron",  "magenta"),
    "adverb":      ("adv",   "blue"),
    "preposition": ("prep",  "blue"),
    "conjunction": ("conj",  "blue"),
    "numeral":     ("num",   "blue"),
    "particle":    ("part",  "blue"),
}

_CASE_ORDER = {"nom": 0, "acc": 1, "dat": 2, "gen": 3}
_NUM_ORDER  = {"sg": 0, "pl": 1, "du": 2}


def _tokenize(text: str) -> list[str]:
    tokens = []
    for raw in text.split():
        word = raw.strip(".,;:!?()[]{}\"'—–-«»")
        if word:
            tokens.append(word)
    return tokens


def _format_morphology(r: dict) -> str:
    if r.get("pos") == "verb":
        mood = r.get("mood") or ""
        if mood == "infin":
            return "infin"
        if mood == "past_part":
            return "past.part"
        if mood == "pres_part":
            return "pres.part"
        if mood == "imp":
            num = r.get("number") or ""
            return f"imp.{num}" if num else "imp"
        person = r.get("person") or ""
        number = r.get("number") or ""
        tense  = r.get("tense") or ""
        tag = f"{person}{number}".strip()
        if tense == "past":
            tag += " past"
        elif tense == "pres":
            tag += " pres"
        if mood == "subj":
            tag += ".subj"
        return tag.strip()
    else:
        case   = r.get("case_") or ""
        number = r.get("number") or ""
        gender = r.get("gender") or ""
        morph  = f"{case}.{number}" if (case and number) else case or number
        return f"{morph} {gender}".strip() if gender else morph


def _format_pos(r: dict) -> Text:
    label, color = _POS_STYLE.get(r.get("pos") or "", (r.get("pos") or "?", "white"))
    entry_gender = r.get("entry_gender") or ""
    strength     = r.get("strength") or ""
    qualifier    = " ".join(p for p in (entry_gender, strength) if p)

    t = Text()
    t.append(r["headword"], style="bold")
    t.append(" (")
    t.append(label, style=color)
    if qualifier:
        t.append(f" {qualifier}", style="dim")
    t.append(")")
    return t


def _trim_definition(defn: str) -> str:
    """Keep only the core gloss, cutting before text citations and grammar refs."""
    # Strip leading grammar ref like "(Gr 3.6.6) " or "3.1.8 (9) "
    defn = re.sub(r"^\s*\(?\s*Gr\s+[\d.]+.*?\)\s*", "", defn).strip()
    defn = re.sub(r"^\d+\.\s*", "", defn).strip()  # leading "1. "
    # Cut at first Roman-numeral text citation like "I:1" or "II:82"
    defn = re.sub(r"\s+[IVX]+:\d.*$", "", defn, flags=re.DOTALL).strip()
    # Cut at double-space (glossary uses double-space before notes)
    defn = defn.split("  ")[0].strip()
    # Hard cap
    if len(defn) > 80:
        defn = defn[:77].rstrip() + "..."
    return defn


def _sort_key(r: dict) -> tuple:
    return (
        _CASE_ORDER.get(r.get("case_") or "", 9),
        _NUM_ORDER.get(r.get("number") or "", 9),
        r.get("person") or "",
    )


def _dedupe(results: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in results:
        key = (r["headword"], _format_morphology(r))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _print_token(token: str, results: list[dict]) -> None:
    results = _dedupe(sorted(results, key=_sort_key))

    console.print(Text(token, style="bold white"))

    if not results:
        console.print("  [dim]?  no match[/dim]")
    else:
        for r in results:
            morph = _format_morphology(r)
            defn  = _trim_definition(r.get("definition") or "")

            line = Text("  ")
            line.append_text(_format_pos(r))
            line.append(" — ", style="dim")
            line.append(morph or "—", style="italic")
            line.append(" — ", style="dim")
            line.append(defn or "—", style="dim")
            console.print(line)

    console.print()


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
    tokens = _tokenize(text)
    if not tokens:
        raise click.UsageError("No words found in input.")

    console.print()
    for token in tokens:
        _print_token(token, parse_form(token, conn))


if __name__ == "__main__":
    main()
