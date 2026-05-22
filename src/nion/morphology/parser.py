"""Parse a surface form and return morphological analyses."""

import sqlite3


def parse_form(form: str, conn: sqlite3.Connection) -> list[dict]:
    """Look up a surface form and return all matching analyses.

    Each result dict contains: headword, definition, pos, case_, number,
    gender, person, mood, tense.
    Not yet implemented.
    """
    raise NotImplementedError
