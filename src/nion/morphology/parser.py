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
               e.id              AS entry_id,
               e.headword,
               e.definition,
               e.pos,
               e.gender          AS entry_gender,
               e.strength,
               e.grammar_ref,
               e.principal_parts,
               e.text_refs,
               e.page_number     AS glossary_page,
               p.page_number     AS grammar_page
        FROM   forms   f
        JOIN   entries   e ON f.entry_id = e.id
        LEFT JOIN paradigms p ON e.paradigm_id = p.id
        WHERE  f.form_normalized = ?
        ORDER  BY e.headword
        """,
        (form_norm,),
    ).fetchall()

    paradigm_results = [{**dict(r), "source": "paradigm"} for r in rows]

    # Always query function_words: if paradigm results exist we still need
    # annotation results whose POS differs (e.g. "ok" is both the past tense
    # of aka/verb and the ubiquitous conjunction — normalization collapses ók→ok).
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

    if not paradigm_results:
        return [{**dict(r), "source": "annotation"} for r in fw_rows]

    # Paradigm results found: append any annotation results with a different POS
    # so that cross-category homographs (ok/conjunction vs ók/verb) are both shown.
    paradigm_pos = {r["pos"] for r in paradigm_results}
    cross_pos = [
        {**dict(r), "source": "annotation"}
        for r in fw_rows
        if dict(r).get("pos") not in paradigm_pos
    ]
    return paradigm_results + cross_pos
