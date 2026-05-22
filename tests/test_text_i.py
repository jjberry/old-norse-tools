"""Tests using Text I (Hrólfs saga kraka) annotations as ground truth.

Each test case comes directly from the NION reader's word-by-word gloss of
Text I.  The annotations record the surface form as it appears in the text,
the expected headword, and the morphological analysis.  We use these as an
independent oracle: if parse_form() disagrees with the textbook, something
in our pipeline is wrong.
"""

import pytest

from nion.morphology.parser import parse_form


# ---------------------------------------------------------------------------
# Noun forms
# ---------------------------------------------------------------------------
# (surface_form, expected_headword, expected_case, expected_number)
# number is None where the annotation does not specify it.

_NOUN_CASES = [
    ("konungs",      "konungr",    "gen", None),
    ("hest",         "hestr",      "acc", None),
    ("hestum",       "hestr",      "dat", None),
    ("stað",         "staðr",      "dat", "sg"),
    ("vatns",        "vatn",       "gen", None),
    ("hǫgg",         "hǫgg",       "nom", None),
    ("hǫggum",       "hǫgg",       "dat", None),
    ("maðr",         "maðr",       "nom", None),
    ("mat",          "matr",       "acc", None),
    ("drykk",        "drykkr",     "acc", None),
    ("atsetu",       "atseta",     "gen", None),
    ("gaum",         "gaumr",      "acc", None),
    ("rúms",         "rúm",        "gen", None),
    ("liðr",         "liðr",       "nom", "sg"),
    ("bekk",         "bekkr",      "acc", None),
    ("tillit",       "tillit",     "acc", None),
    ("skjaldborg",   "skjaldborg", "acc", None),
    ("skjaldborgar", "skjaldborg", "gen", None),
]


class TestNounForms:
    @pytest.mark.parametrize("surface,headword,case_,number", _NOUN_CASES)
    def test_parse_returns_expected_headword(self, conn, surface, headword, case_, number):
        results = parse_form(surface, conn)
        assert results, f"No results for '{surface}'"
        headwords = {r["headword"] for r in results}
        assert headword in headwords, (
            f"'{surface}': expected headword '{headword}', got {sorted(headwords)}"
        )

    @pytest.mark.parametrize("surface,headword,case_,number", _NOUN_CASES)
    def test_parse_returns_expected_case(self, conn, surface, headword, case_, number):
        results = parse_form(surface, conn)
        assert results, f"No results for '{surface}'"
        matching = [r for r in results if r["headword"] == headword]
        assert matching, f"No results with headword '{headword}' for '{surface}'"
        cases = {r["case_"] for r in matching}
        assert case_ in cases, (
            f"'{surface}' ({headword}): expected case '{case_}', got {cases}"
        )

    @pytest.mark.parametrize("surface,headword,case_,number", [
        (s, h, c, n) for s, h, c, n in _NOUN_CASES if n is not None
    ])
    def test_parse_returns_expected_number(self, conn, surface, headword, case_, number):
        results = parse_form(surface, conn)
        matching = [r for r in results if r["headword"] == headword and r["case_"] == case_]
        assert matching, f"No {case_} results for '{surface}' ({headword})"
        numbers = {r["number"] for r in matching}
        assert number in numbers, (
            f"'{surface}' ({headword} {case_}): expected number '{number}', got {numbers}"
        )


# ---------------------------------------------------------------------------
# Verb forms (weak verbs — present and past forms we generate)
# ---------------------------------------------------------------------------
# (surface_form, expected_headword, expected_tense_or_mood, expected_number, expected_person)
# None values are not checked.

_VERB_CASES = [
    ("leiðir",  "leiða",   "pres", "sg", "3"),
    ("spyrr",   "spyrja",  "pres", "sg", "3"),
    ("svarar",  "svara",   "pres", "sg", "3"),
    ("segir",   "segja",   "pres", "sg", "3"),
    ("hnykkir", "hnykkja", "pres", "sg", "3"),
    ("setr",    "setja",   "pres", "sg", "3"),
    ("kveldar", "kvelda",  "pres", "sg", "3"),
    ("mælir",   "mæla",    "pres", "sg", "3"),
    ("kasta",   "kasta",   "pres", "pl", "3"),
    ("ætlaða",  "ætla",    "past", "sg", "1"),
    ("svarat",  "svara",   None,   "sg", None),   # past participle
    ("ætlat",   "ætla",    None,   "sg", None),   # past participle
]


class TestVerbForms:
    @pytest.mark.parametrize("surface,headword,tense,number,person", _VERB_CASES)
    def test_parse_returns_expected_headword(self, conn, surface, headword, tense, number, person):
        results = parse_form(surface, conn)
        assert results, f"No results for '{surface}'"
        headwords = {r["headword"] for r in results}
        assert headword in headwords, (
            f"'{surface}': expected headword '{headword}', got {sorted(headwords)}"
        )

    @pytest.mark.parametrize("surface,headword,tense,number,person", [
        t for t in _VERB_CASES if t[2] is not None
    ])
    def test_parse_returns_expected_tense(self, conn, surface, headword, tense, number, person):
        results = parse_form(surface, conn)
        matching = [r for r in results if r["headword"] == headword]
        assert matching, f"No results with headword '{headword}' for '{surface}'"
        tenses = {r["tense"] for r in matching}
        assert tense in tenses, (
            f"'{surface}' ({headword}): expected tense '{tense}', got {tenses}"
        )


# ---------------------------------------------------------------------------
# Noun coverage: at least 70% of Text I nouns with grammatical tags parse
# ---------------------------------------------------------------------------

class TestNounCoverage:
    def test_text_i_noun_coverage(self, conn):
        """At least 70% of Text I annotated nouns return a parse result."""
        rows = conn.execute(
            """
            SELECT surface_form FROM annotations
            WHERE text_id = 'I' AND pos = 'noun' AND grammatical_tags IS NOT NULL
            """
        ).fetchall()
        assert rows, "No Text I noun annotations found"

        hits = sum(1 for r in rows if parse_form(r["surface_form"], conn))
        rate = hits / len(rows)
        assert rate >= 0.70, (
            f"Text I noun coverage {hits}/{len(rows)} ({rate:.0%}) is below 70%"
        )
