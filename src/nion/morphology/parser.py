"""Parse a surface form and return morphological analyses."""

from __future__ import annotations

import sqlite3

from nion.encoding import normalize_for_search


def parse_form(form: str, conn: sqlite3.Connection) -> list[dict]:
    """Look up *form* and return all morphological analyses.

    Queries the paradigm-generated forms table first.  If nothing is found,
    falls back to the function_words table (seeded from reader annotations).

    Each result dict has: headword, definition, pos, entry_gender, strength,
    form, case_, number, gender, person, mood, tense, source.
    source is 'paradigm' or 'annotation'.
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

    if rows:
        return [{**dict(r), "source": "paradigm"} for r in rows]

    # Fallback: function words and forms from reader annotations.
    fw_rows = conn.execute(
        """
        SELECT form, case_, number, gender, person, mood, tense,
               headword, gloss AS definition, pos,
               NULL AS entry_gender, NULL AS strength
        FROM   function_words
        WHERE  form_normalized = ?
        ORDER  BY headword
        """,
        (form_norm,),
    ).fetchall()

    return [{**dict(r), "source": "annotation"} for r in fw_rows]
