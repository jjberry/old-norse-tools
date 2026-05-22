"""
PDF font artifact correction and search normalization for Old Norse text.

These PDFs (VSNR A New Introduction to Old Norse) use a custom font where:
  ›  (U+203A)  →  ð  (eth,      U+00F0)
  ƒ  (U+0192)  →  ǫ  (o-ogonek, U+01EB)
  fl (f+l)     →  þ  (thorn,    U+00FE)  — context-dependent, see fix_pdf_encoding()

The fl→þ mapping is ambiguous because Old Norse has genuine fl- words (fljótr, flokk,
etc.). Word-initial "fl" before consonant clusters impossible for fl (e.g. flr-, flv-,
fln-) are safe to convert; other cases are resolved during glossary parsing using the
headword's English definition as context.
"""

import unicodedata
import re

# Characters that are unambiguously wrong in Old Norse text
_DEFINITE: dict[str, str] = {
    "›": "ð",  # › (U+203A) → ð (eth)
    "ƒ": "ǫ",  # ƒ (U+0192) → ǫ (o with ogonek)
    "‡": "ý",  # ‡ (U+2021) → ý (y with acute) — grammar PDF artifact
    "¯": "",   # macron artifact — strip
    "": "",   # Apple private-use glyph — strip
}

# fl- prefixes that cannot be genuine fl- clusters in Old Norse
# (because the following consonant makes fl+C impossible)
_FL_THORN_PATTERN = re.compile(r"\bfl([rnvgk])", re.UNICODE)

# Known real fl- headwords that must not be converted to þ-
_REAL_FL_WORDS: frozenset[str] = frozenset(
    [
        "fla",
        "flá",
        "flaga",
        "flasa",
        "flat",   # note: in context flat=þat; this is resolved per-entry
        "fljótr",
        "flokk",
        "flokkr",
        "flótta",
        "flótti",
        "flugr",
        "flyja",
        "flýja",
    ]
)


def fix_pdf_encoding(text: str) -> str:
    """Convert PDF font artifacts to canonical Old Norse Unicode.

    Safe to call on any extracted text. Applies definite replacements first,
    then heuristic fl→þ for unambiguous consonant clusters.
    """
    for bad, good in _DEFINITE.items():
        text = text.replace(bad, good)

    # fl + impossible-cluster consonant → þ + that consonant
    text = _FL_THORN_PATTERN.sub(lambda m: "þ" + m.group(1), text)

    return text


# Characters that don't decompose via NFD and need explicit mapping for search
_SEARCH_MAP: dict[str, str] = {
    "þ": "th",
    "Þ": "th",
    "ð": "d",
    "Ð": "d",
    "ǫ": "o",
    "æ": "ae",
    "Æ": "ae",
    "œ": "oe",
    "Œ": "oe",
    "ø": "o",
    "Ø": "o",
}


def normalize_for_search(text: str) -> str:
    """Strip diacritics and fold case for fuzzy / case-insensitive lookup.

    á→a, é→e, ó→o, ú→u, ý→y (via NFD decomposition + strip combining marks)
    þ→th, ð→d, ǫ→o, æ→ae, œ→oe, ø→o   (via explicit map)
    """
    for char, replacement in _SEARCH_MAP.items():
        text = text.replace(char, replacement)

    # NFD decomposition strips combining diacritics (acute, umlaut, etc.)
    nfd = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in nfd if unicodedata.category(c) != "Mn")

    return stripped.lower()
