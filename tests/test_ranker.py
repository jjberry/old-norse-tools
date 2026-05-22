"""Tests for the preposition-driven analysis ranker."""

import pytest
from nion.morphology.ranker import rank_analyses


def _make(case_: str | None, number: str = "sg") -> dict:
    return {"case_": case_, "number": number, "pos": "noun"}


class TestRankAnalyses:
    def test_no_preceding_token_unchanged(self):
        results = [_make("nom"), _make("acc"), _make("dat")]
        assert rank_analyses(results) == results

    def test_unknown_preceding_token_unchanged(self):
        results = [_make("nom"), _make("acc"), _make("dat")]
        assert rank_analyses(results, "ok") == results

    def test_til_boosts_gen(self):
        results = [_make("nom"), _make("acc"), _make("gen"), _make("dat")]
        ranked = rank_analyses(results, "til")
        assert ranked[0]["case_"] == "gen"

    def test_um_boosts_acc(self):
        results = [_make("nom"), _make("acc", "sg"), _make("acc", "pl"), _make("dat")]
        ranked = rank_analyses(results, "um")
        assert ranked[0]["case_"] == "acc"
        assert ranked[1]["case_"] == "acc"
        assert ranked[2]["case_"] in ("nom", "dat")

    def test_af_boosts_dat(self):
        results = [_make("nom"), _make("acc"), _make("dat")]
        ranked = rank_analyses(results, "af")
        assert ranked[0]["case_"] == "dat"

    def test_fra_boosts_dat(self):
        """frá normalises to 'fra' — should still match."""
        results = [_make("nom"), _make("gen"), _make("dat")]
        ranked = rank_analyses(results, "frá")
        assert ranked[0]["case_"] == "dat"

    def test_relative_order_within_boosted_preserved(self):
        sg  = _make("acc", "sg")
        pl  = _make("acc", "pl")
        nom = _make("nom")
        ranked = rank_analyses([nom, sg, pl], "um")
        assert ranked == [sg, pl, nom]

    def test_relative_order_within_rest_preserved(self):
        nom = _make("nom")
        dat = _make("dat")
        gen = _make("gen")
        ranked = rank_analyses([nom, dat, gen], "um")   # um→acc, none match
        assert ranked == [nom, dat, gen]

    def test_empty_results_unchanged(self):
        assert rank_analyses([], "til") == []

    def test_ambiguous_prep_not_in_table(self):
        """í governs both acc and dat — should not be in the table."""
        results = [_make("nom"), _make("acc"), _make("dat")]
        assert rank_analyses(results, "í") == results

    @pytest.mark.parametrize("prep,case_", [
        ("til",    "gen"),
        ("utan",   "gen"),
        ("milli",  "gen"),
        ("af",     "dat"),
        ("at",     "dat"),
        ("hjá",    "dat"),
        ("úr",     "dat"),
        ("um",     "acc"),
        ("gegnum", "acc"),
    ])
    def test_prep_governs_expected_case(self, prep, case_):
        results = [_make("nom"), _make("acc"), _make("gen"), _make("dat")]
        ranked = rank_analyses(results, prep)
        assert ranked[0]["case_"] == case_, f"{prep} should boost {case_}"
