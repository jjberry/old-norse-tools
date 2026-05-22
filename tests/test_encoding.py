"""Tests for PDF encoding correction and search normalization."""

import pytest
from nion.encoding import fix_pdf_encoding, normalize_for_search


class TestFixPdfEncoding:
    def test_eth_replacement(self):
        assert fix_pdf_encoding("haf›i") == "hafði"

    def test_o_ogonek_replacement(self):
        assert fix_pdf_encoding("kƒllum") == "kǫllum"

    def test_macron_stripped(self):
        assert fix_pdf_encoding("a¯b") == "ab"

    def test_private_use_stripped(self):
        assert fix_pdf_encoding("ab") == "ab"

    def test_thorn_before_impossible_cluster_r(self):
        # flr- cannot be a genuine fl- cluster; must be þr-
        assert fix_pdf_encoding("flrífr") == "þrífr"

    def test_thorn_before_impossible_cluster_n(self):
        assert fix_pdf_encoding("flná") == "þná"

    def test_thorn_before_impossible_cluster_v(self):
        assert fix_pdf_encoding("flvert") == "þvert"

    def test_genuine_fl_word_untouched(self):
        # "aflat" has a genuine fl cluster after a vowel — must not be converted
        assert fix_pdf_encoding("aflat") == "aflat"

    def test_multiple_replacements(self):
        result = fix_pdf_encoding("á›r ok kƒllum")
        assert result == "áðr ok kǫllum"

    def test_plain_ascii_untouched(self):
        assert fix_pdf_encoding("konungr") == "konungr"


class TestNormalizeForSearch:
    @pytest.mark.parametrize("input_, expected", [
        ("þ",  "th"),
        ("ð",  "d"),
        ("ǫ",  "o"),
        ("æ",  "ae"),
        ("œ",  "oe"),
        ("ø",  "o"),
        ("á",  "a"),
        ("é",  "e"),
        ("í",  "i"),
        ("ó",  "o"),
        ("ú",  "u"),
        ("ý",  "y"),
        ("Þ",  "th"),
        ("Ð",  "d"),
        ("Æ",  "ae"),
    ])
    def test_single_character(self, input_, expected):
        assert normalize_for_search(input_) == expected

    def test_whole_word(self):
        assert normalize_for_search("þrífr") == "thrifr"

    def test_case_folded(self):
        assert normalize_for_search("Konungr") == "konungr"

    def test_mixed_word(self):
        assert normalize_for_search("áðr") == "adr"  # á→a, ð→d, r→r

    def test_idempotent(self):
        once = normalize_for_search("kǫllum")
        twice = normalize_for_search(once)
        assert once == twice
