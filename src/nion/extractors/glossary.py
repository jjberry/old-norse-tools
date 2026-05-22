"""Extract lexical entries from the Glossary PDF (NION Part III)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import pdfplumber

from nion.encoding import fix_pdf_encoding, normalize_for_search


# ---------------------------------------------------------------------------
# Page range for the main Old Norse glossary (0-indexed)
# Pages 1-5 are front matter; 293+ are East Norse and Runic supplements.
# ---------------------------------------------------------------------------
_GLOSSARY_FIRST_PAGE = 5    # page 6 in human numbering
_GLOSSARY_LAST_PAGE  = 291  # page 292 in human numbering (inclusive)

# ---------------------------------------------------------------------------
# Running page header patterns – filter these out
# ---------------------------------------------------------------------------
_PAGE_HEADER_RE = re.compile(
    r"^\d+\s+A New Introduction to Old Norse$"
    r"|^Glossary and Index(?:\s+of\s+\w+(?:\s+\w+)*)?\s+\d+$",
    re.IGNORECASE,
)


def _is_page_header(text: str) -> bool:
    return bool(_PAGE_HEADER_RE.match(text.strip()))


# ---------------------------------------------------------------------------
# Line-type detection based on x0 position
#
# Two page layouts alternate (inner/outer margin swap for recto/verso):
#   Odd  pages: entry ≈ 51.0, continuation ≈ 59.5
#   Even pages: entry ≈ 62.3, continuation ≈ 70.8
#
# The four bands don't overlap, so a single function handles both:
#   x0 ≤ 56          → odd-page new entry
#   56 < x0 ≤ 61     → odd-page continuation
#   61 < x0 ≤ 66     → even-page new entry
#   x0 > 66          → even-page continuation
# ---------------------------------------------------------------------------

def _is_new_entry(x0: float) -> bool:
    if x0 <= 56:  return True   # odd-page entry  (~51.0)
    if x0 <= 61:  return False  # odd-page continuation (~59.5)
    if x0 <= 66:  return True   # even-page entry (~62.3)
    return False                 # even-page continuation (~70.8)


# ---------------------------------------------------------------------------
# POS abbreviation table
# ---------------------------------------------------------------------------
_POS_MAP: dict[str, tuple[str, Optional[str], Optional[str]]] = {
    # abbr → (canonical_pos, gender, strength)
    "pret.-pres.":   ("verb",        None, None),
    "interrog.":     ("pronoun",     None, None),
    "interjection":  ("particle",    None, None),
    "particle":      ("particle",    None, None),
    "suffix":        ("particle",    None, None),
    "pp.":           ("adjective",   None, None),  # past participle used as headword
    "a.":            ("adjective",   None, None),  # archaic "a." for adjective
    "sm.":         ("noun",        "m",  "strong"),
    "sf.":         ("noun",        "f",  "strong"),
    "sn.":         ("noun",        "n",  "strong"),
    "wm.":         ("noun",        "m",  "weak"),
    "wf.":         ("noun",        "f",  "weak"),
    "wn.":         ("noun",        "n",  "weak"),
    "prep.":       ("preposition", None, None),
    "conj.":       ("conjunction", None, None),
    "pron.":       ("pronoun",     None, None),
    "num.":        ("numeral",     None, None),
    "art.":        ("article",     None, None),
    "adj.":        ("adjective",   None, None),
    "adv.":        ("adverb",      None, None),
    "neg.":        ("particle",    None, None),
    "sv.":         ("verb",        None, "strong"),
    "wv.":         ("verb",        None, "weak"),
    "vb.":         ("verb",        None, None),
    "m.":          ("noun",        "m",  None),
    "f.":          ("noun",        "f",  None),
    "n.":          ("noun",        "n",  None),
}

# Sorted longest-first to avoid partial matches (e.g. "pret.-pres." before "pres.")
_POS_ABBRS = sorted(_POS_MAP.keys(), key=len, reverse=True)

# Quick check: does the text contain any POS marker at all?
_HAS_POS_RE = re.compile(
    r"\b(?:sm\.|sf\.|sn\.|wm\.|wf\.|wn\.|pret\.-pres\.|interrog\.|interjection|"
    r"prep\.|conj\.|pron\.|num\.|art\.|adj\.|adv\.|neg\.|sv\.|wv\.|vb\.|m\.|f\.|n\.)"
)

_TEXT_CITE_RE = re.compile(r"\b[IVX]{1,8}:\d+")  # "I:31", "XXI:47" etc.


def _is_xref(text: str) -> bool:
    """Return True if *text* (with no POS marker) is a cross-reference entry.

    Handles the two cross-reference forms used in this glossary:
    - ``FORM(S) see TARGET``  — target may be multi-word or compound
    - ``FORM = VARIANT``       — variant-spelling pointer (no 'see')
    """
    if _HAS_POS_RE.search(text):
        return False

    # "= VARIANT" entries (may also have trailing text refs: es1 = er1 VIII:5)
    if re.search(r"\s=\s", text):
        # Genuine variant pointer: "= VARIANT" appears before any citations
        eq_m = re.search(r"\s=\s", text)
        pre_eq = text[: eq_m.start()]
        if not _TEXT_CITE_RE.search(pre_eq):
            return True

    # "see TARGET" entries
    see_m = re.search(r"\bsee\b", text)
    if see_m:
        pre_see = text[: see_m.start()]
        # Only a cross-ref if there are no text citations before the "see"
        if not _TEXT_CITE_RE.search(pre_see):
            return True

    return False

# ---------------------------------------------------------------------------
# Verb principal-parts parenthetical (appears immediately after headword,
# before the POS abbreviation; contains pres / past / pp / subj keywords)
# ---------------------------------------------------------------------------
_PRINC_PARTS_RE = re.compile(
    r"^\s*\([^)]*\b(?:pres|past|pp|subj)\b[^)]*\)\s*"
)

# ---------------------------------------------------------------------------
# Grammar cross-reference pattern: "Gr 3.6.9.3 ex. 1" etc.
# ---------------------------------------------------------------------------
_GR_REF_RE = re.compile(
    r"\bGr\s+"
    r"\d+\.\d+(?:\.\d+)*"
    r"(?:\.(?:\(\d+\)|\d+))*"
    r"(?:\s+(?:ex\.?\s*[\d,]+|\(\d+\)))?"
    r"(?:\s*,\s*\d+\.\d+(?:\.\d+)*(?:\s+(?:ex\.?\s*[\d,]+|\(\d+\)))?)*"
)

# ---------------------------------------------------------------------------
# Text citation pattern: "I:31", "XXVI A:14", "XXI:175–80" etc.
# ---------------------------------------------------------------------------
_TEXT_REF_RE = re.compile(
    r"\b([IVX]{1,8}(?:\s+[AB])?:\d+(?:[–\-]\d+)?)"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fix(s: str) -> str:
    return fix_pdf_encoding(s).strip()


def _find_pos(text: str) -> tuple[Optional[str], Optional[str], Optional[str], int]:
    """Scan *text* for the first POS abbreviation outside parentheses.

    Returns ``(canonical_pos, gender, strength, end_index)`` where
    ``end_index`` is the position just after the matched abbreviation.
    If no POS is found, returns ``(None, None, None, len(text))``.
    """
    depth = 0
    i = 0
    while i < len(text):
        c = text[i]
        if c == "(":
            depth += 1
            i += 1
            continue
        if c == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth > 0:
            i += 1
            continue
        # Only try at word-boundary positions (after space or at start)
        if i > 0 and text[i - 1] not in " \t":
            i += 1
            continue
        for abbr in _POS_ABBRS:
            end = i + len(abbr)
            if text[i:end] == abbr:
                pos, gender, strength = _POS_MAP[abbr]
                return pos, gender, strength, end
        i += 1
    return None, None, None, len(text)


# ---------------------------------------------------------------------------
# Entry parser
# ---------------------------------------------------------------------------

def _parse_entry(raw_text: str, page_number: Optional[int] = None) -> Optional[dict]:
    """Parse one glossary entry (all its lines joined) into a structured dict."""
    text = _fix(raw_text)
    if not text:
        return None

    # --- Headword (first non-space token; may start with '-') ---
    hw_m = re.match(r"^(-?[^\s,;(=]+)", text)
    if not hw_m:
        return None
    headword_raw = hw_m.group(1)

    # Strip trailing homonym digit (á1, á2, of1 …); Old Norse words never end in digits
    hw_clean = re.sub(r"\d+$", "", headword_raw)
    headword = _fix(hw_clean) or _fix(headword_raw)

    rest = text[hw_m.end():].strip()

    # --- Cross-reference entries (e.g. "a›ra, a›rar, a›rir see annarr") ---
    if _is_xref(text):
        see_m = re.search(r"\bsee\s+(\S+)", rest)
        target = _fix(see_m.group(1).rstrip(".")) if see_m else ""
        return {
            "headword":            headword,
            "headword_normalized": normalize_for_search(headword),
            "pos":                 "xref",
            "gender":              None,
            "strength":            None,
            "definition":          f"see {target}",
            "grammar_ref":         None,
            "principal_parts":     None,
            "text_refs":           None,
            "page_number":         page_number,
        }

    # --- Normalize rare POS marker typos before searching ---
    # "f," → "f."  (comma instead of period for gender)
    rest = re.sub(r"^([mfn]),(\s)", r"\1.\2", rest)
    # bare "m"/"f"/"n" immediately before a lowercase definition word
    rest = re.sub(r"^([mfn]) ([a-z])", r"\1. \2", rest)
    # "adj " → "adj." before a parenthetical or definition
    rest = re.sub(r"^adj ([(\[A-Za-z])", r"adj. \1", rest)

    # --- Verb principal parts (parenthetical with pres/past/pp keywords) ---
    principal_parts: Optional[str] = None
    pp_m = _PRINC_PARTS_RE.match(rest)
    if pp_m:
        inner = re.sub(r"^\(|\)$", "", pp_m.group(0).strip()).strip()
        principal_parts = _fix(inner)
        rest = rest[pp_m.end():].strip()

    # --- POS marker ---
    pos, gender, strength, pos_end = _find_pos(rest)
    body = rest[pos_end:].strip()

    # --- Grammar cross-references ---
    gr_matches = _GR_REF_RE.findall(body)
    if not gr_matches:
        gr_matches = _GR_REF_RE.findall(text)
    grammar_ref = "; ".join(gr_matches) if gr_matches else None

    # --- Text citations ---
    text_refs = _TEXT_REF_RE.findall(text)

    return {
        "headword":            headword,
        "headword_normalized": normalize_for_search(headword),
        "pos":                 pos or "unknown",
        "gender":              gender,
        "strength":            strength,
        "definition":          body,
        "grammar_ref":         grammar_ref,
        "principal_parts":     principal_parts,
        "text_refs":           json.dumps(text_refs) if text_refs else None,
        "page_number":         page_number,
    }


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def _iter_entry_texts(pdf_path: Path):
    """Yield (raw_text, page_number) tuples by grouping lines from glossary pages.

    page_number is the 1-based physical PDF page where the entry begins.
    """
    current_lines: list[str] = []
    current_page: int = 0

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[_GLOSSARY_FIRST_PAGE : _GLOSSARY_LAST_PAGE + 1]
        for page in pages:
            raw_lines = page.extract_text_lines(x_tolerance=2, y_tolerance=3) or []
            for ln in raw_lines:
                line_text = ln.get("text", "").strip()
                if not line_text or _is_page_header(line_text):
                    continue
                chars = ln.get("chars", [])
                x0 = chars[0]["x0"] if chars else 99.0

                if _is_new_entry(x0):
                    if current_lines:
                        yield " ".join(current_lines), current_page
                    current_lines = [line_text]
                    current_page = page.page_number
                else:
                    current_lines.append(line_text)

    if current_lines:
        yield " ".join(current_lines), current_page


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_entries(pdf_path: Path) -> list[dict]:
    """Parse the glossary PDF and return a list of entry dicts.

    Each dict has keys matching the ``entries`` table schema.
    """
    entries: list[dict] = []
    for raw_text, page_number in _iter_entry_texts(pdf_path):
        entry = _parse_entry(raw_text, page_number)
        if entry is not None:
            entries.append(entry)
    return entries
