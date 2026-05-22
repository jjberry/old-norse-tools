"""Extract morphological annotations from the Reader PDF (NION Part II).

Text I (Hrólfs saga kraka) has comprehensive word-by-word grammatical
commentary on pages 46-57 (0-indexed 45-56) that serves as a
gold-standard validation corpus.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import pdfplumber

from nion.encoding import fix_pdf_encoding

# ---------------------------------------------------------------------------
# Page range for Text I comprehensive commentary (0-indexed)
# ---------------------------------------------------------------------------
_ANNO_FIRST_PAGE = 45   # page 46 in human numbering
_ANNO_LAST_PAGE  = 56   # page 57 in human numbering (inclusive)

# Font size threshold: annotation text ≈ 8pt, saga text ≈ 10pt
_ANNO_FONT_SIZE = 9.0

# ---------------------------------------------------------------------------
# Quote characters used in the PDF for glosses
# ---------------------------------------------------------------------------
_Q  = r"[‘’']"   # opening or closing single quote (curly or straight)
_QO = r"[‘']"          # opening quote
_QC = r"[’']"          # closing quote

# ---------------------------------------------------------------------------
# POS abbreviations in reader annotations (longest first for safe matching)
# ---------------------------------------------------------------------------
_POS_ABBRS = [
    "pret.-pres.", "REFL. POSS.", "interrog.", "particle",
    "prep.", "conj.", "pron.", "num.", "art.",
    "adj.", "adv.", "neg.",
    "sm.", "sf.", "sn.", "wm.", "wf.", "wn.",
    "sv.", "wv.", "vb.", "pp.",
    "m.", "f.", "n.",
]

# Canonical form: raw abbr → (pos, gender, strength)
_ANNO_POS_MAP: dict[str, tuple[str, Optional[str], Optional[str]]] = {
    "sm.":         ("noun",        "m",  "strong"),
    "sf.":         ("noun",        "f",  "strong"),
    "sn.":         ("noun",        "n",  "strong"),
    "wm.":         ("noun",        "m",  "weak"),
    "wf.":         ("noun",        "f",  "weak"),
    "wn.":         ("noun",        "n",  "weak"),
    "m.":          ("noun",        "m",  None),
    "f.":          ("noun",        "f",  None),
    "n.":          ("noun",        "n",  None),
    "sv.":         ("verb",        None, "strong"),
    "wv.":         ("verb",        None, "weak"),
    "vb.":         ("verb",        None, None),
    "pret.-pres.": ("verb",        None, None),
    "adj.":        ("adjective",   None, None),
    "adv.":        ("adverb",      None, None),
    "prep.":       ("preposition", None, None),
    "conj.":       ("conjunction", None, None),
    "pron.":       ("pronoun",     None, None),
    "num.":        ("numeral",     None, None),
    "art.":        ("article",     None, None),
    "neg.":        ("particle",    None, None),
    "particle":    ("particle",    None, None),
    "pp.":         ("adjective",   None, None),
    "interrog.":   ("pronoun",     None, None),
    "REFL. POSS.": ("pronoun",     None, None),
}

_POS_ALT = "|".join(re.escape(p) for p in _POS_ABBRS)

# Pattern to find annotation entry starts with finditer over the full text.
# Requires: SURFACE_FORM  POS_ABBR  [footnote-digit]  [+POS]  [parens]  quote
_ANNO_ENTRY_FIND_RE = re.compile(
    r"(\S+)\s+(" + _POS_ALT + r")"
    r"(?:\s+\d+)?"                  # optional footnote superscript digit
    r"(?:\s+\+\s+\S+)?"            # optional compound POS: "+ art."
    r"(?:\s+\([^)]*\))?"           # optional parenthetical before gloss
    r"\s+" + _QO,                   # opening quote starts the gloss
    re.UNICODE,
)

# ---------------------------------------------------------------------------
# Extraction patterns
# ---------------------------------------------------------------------------
_GLOSS_RE    = re.compile(_QO + r"([^" + "‘’'" + r"]+)" + _QC, re.UNICODE)
_GR_REF_RE   = re.compile(r"\((\d+\.\d+(?:\.\d+)*(?:[,;]\s*\d+\.\d+(?:\.\d+)*)*)\)")
# Match "of HEADWORD" only when a grammatical tag precedes it and the
# headword is followed by a parenthetical, period, or end (not English prose).
_HEADWORD_RE = re.compile(
    r"\b(?:nom|acc|gen|dat|sg|pl|1st|2nd|3rd|pres|past|indic|subj|imp)\S*\s+of\s+"
    r"([^\s(,;.:]+)"
    r"(?=\s*(?:[\(\.;,]|\Z))"
)

# Grammatical tags from description
_CASE_RE   = re.compile(r"\b(nom|acc|gen|dat)\b")
_NUMBER_RE = re.compile(r"\b(sg|pl)\b")
_GEND_RE   = re.compile(r"(?<!\w)([mfn])\.(?=\s|$)")
_PERSON_RE = re.compile(r"\b(1st|2nd|3rd)\b")
_TENSE_RE  = re.compile(r"\b(pres|past)\b")
_MOOD_RE   = re.compile(r"\b(indic|subj|imper?)\b")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _avg_font_size(chars: list[dict]) -> float:
    sizes = [c.get("size", 0.0) for c in chars if c.get("size")]
    return sum(sizes) / len(sizes) if sizes else 0.0


def _parse_tags(desc: str) -> dict:
    tags: dict = {}
    m = _CASE_RE.search(desc)
    if m:
        tags["case"] = m.group(1)
    m = _NUMBER_RE.search(desc)
    if m:
        tags["number"] = m.group(1)
    m = _GEND_RE.search(desc)
    if m:
        tags["gender"] = m.group(1)
    m = _PERSON_RE.search(desc)
    if m:
        tags["person"] = m.group(1)[0]   # "3rd" → "3"
    m = _TENSE_RE.search(desc)
    if m:
        tags["tense"] = m.group(1)
    m = _MOOD_RE.search(desc)
    if m:
        raw = m.group(1)
        tags["mood"] = "imp" if raw.startswith("imp") else raw
    return tags


# ---------------------------------------------------------------------------
# Entry splitting and parsing
# ---------------------------------------------------------------------------

def _split_entries(text: str) -> list[str]:
    """Locate entry starts via regex and return slices of *text* between them."""
    matches = list(_ANNO_ENTRY_FIND_RE.finditer(text))
    if not matches:
        return []
    entries = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        entries.append(text[start:end].strip())
    return entries


def _parse_entry(raw: str, line_number: Optional[int]) -> Optional[dict]:
    """Parse one annotation entry string into a structured dict."""
    text = fix_pdf_encoding(raw).strip()
    if not text:
        return None

    # Surface form: first whitespace-delimited token
    sf_m = re.match(r"^(\S+)\s+", text)
    if not sf_m:
        return None
    surface_form = sf_m.group(1)
    rest = text[sf_m.end():]

    # POS abbreviation (longest-first scan)
    raw_pos: Optional[str] = None
    pos_end = 0
    for abbr in _POS_ABBRS:
        if rest.startswith(abbr):
            raw_pos = abbr
            pos_end = len(abbr)
            break

    body = rest[pos_end:].strip()

    # Strip optional footnote superscript after POS
    body = re.sub(r"^\d+\s+", "", body)

    # Strip optional compound POS: "+ art. "
    body = re.sub(r"^\+\s+\S+\s*", "", body)

    # Canonical POS, POS-derived gender and strength
    canonical_pos, pos_gender, pos_strength = _ANNO_POS_MAP.get(
        raw_pos or "", (raw_pos, None, None)
    )

    # Gloss: first quoted string (typographic or straight quotes)
    gloss_m = _GLOSS_RE.search(body)
    gloss = gloss_m.group(1) if gloss_m else None

    # Grammar cross-reference in parentheses
    gr_m = _GR_REF_RE.search(body)
    grammar_ref = gr_m.group(1) if gr_m else None

    # Headword: "of HEADWORD" in description
    hw_m = _HEADWORD_RE.search(body)
    headword = fix_pdf_encoding(hw_m.group(1)).strip() if hw_m else None

    # Grammatical tags: from text after the gloss
    desc = body[gloss_m.end():] if gloss_m else body
    tags = _parse_tags(desc)

    # Merge POS-derived metadata into tags
    if pos_gender and "gender" not in tags:
        tags["gender"] = pos_gender
    if pos_strength:
        tags["strength"] = pos_strength

    return {
        "text_id":          "I",
        "line_number":      line_number,
        "surface_form":     surface_form,
        "headword":         headword,
        "pos":              canonical_pos,
        "grammatical_tags": json.dumps(tags) if tags else None,
        "gloss":            gloss,
        "grammar_ref":      grammar_ref,
    }


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def _iter_annotation_lines(pdf_path: Path):
    """Yield (line_number, text) for annotation lines in Text I.

    Font size < _ANNO_FONT_SIZE identifies annotation text (≈8pt vs saga 10pt).
    All annotation text is yielded with line_number=None since line-number
    markers are embedded in the saga text (10pt), not annotation text.
    """
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[_ANNO_FIRST_PAGE : _ANNO_LAST_PAGE + 1]
        for page in pages:
            raw_lines = page.extract_text_lines(x_tolerance=2, y_tolerance=3) or []
            for ln in raw_lines:
                chars = ln.get("chars", [])
                if not chars:
                    continue
                if _avg_font_size(chars) >= _ANNO_FONT_SIZE:
                    continue
                line_text = ln.get("text", "").strip()
                if line_text:
                    yield None, line_text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Surface forms that look like POS abbreviations are false positives
_POS_ABBRS_SET = frozenset(p.rstrip(".").lower() for p in _POS_ABBRS)


def extract_annotations(pdf_path: Path) -> list[dict]:
    """Parse Text I annotations and return a list of annotation dicts.

    Each dict has keys matching the ``annotations`` table schema.
    """
    all_lines = [fix_pdf_encoding(text) for _, text in _iter_annotation_lines(pdf_path)]
    combined = " ".join(all_lines)

    results: list[dict] = []
    for raw_entry in _split_entries(combined):
        entry = _parse_entry(raw_entry, None)
        if entry is None:
            continue
        # Drop entries whose surface form is a POS abbreviation (false positives)
        sf = entry["surface_form"].rstrip(".").lower()
        if sf in _POS_ABBRS_SET:
            continue
        results.append(entry)
    return results
