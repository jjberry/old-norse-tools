"""Parse a surface form and return morphological analyses."""

from __future__ import annotations

import sqlite3

from nion.encoding import normalize_for_search


def parse_form(form: str, conn: sqlite3.Connection) -> list[dict]:
    """Look up *form* in the pre-generated forms table.

    Returns a list of analysis dicts, one per matching entry.  Each dict has:
    headword, definition, pos, entry_gender, strength, form, case_, number,
    gender, person, mood, tense.
    """
    form_norm = normalize_for_search(form)
    rows = conn.execute(
        """
        SELECT f.form,
               f.case_,
               f.number,
               f.gender,
               f.person,
               f.mood,
               f.tense,
               e.headword,
               e.definition,
               e.pos,
               e.gender   AS entry_gender,
               e.strength
        FROM   forms   f
        JOIN   entries e ON f.entry_id = e.id
        WHERE  f.form_normalized = ?
        ORDER  BY e.headword
        """,
        (form_norm,),
    ).fetchall()
    return [dict(r) for r in rows]
