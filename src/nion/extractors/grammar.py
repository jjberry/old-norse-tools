"""Extract numbered paradigm tables from the Grammar PDF (NION Part I)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber

from nion.encoding import fix_pdf_encoding


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ParadigmForm:
    form: str
    case_: Optional[str] = None      # nom / acc / gen / dat
    number: Optional[str] = None     # sg / pl
    gender: Optional[str] = None     # m / f / n
    person: Optional[str] = None     # 1 / 2 / 3
    mood: Optional[str] = None       # indic / subj / imper / infin / pres_part / past_part
    tense: Optional[str] = None      # pres / past


@dataclass
class Paradigm:
    paradigm_number: str
    section: str
    pos: str                          # noun / adjective / verb
    gender: Optional[str] = None
    strength: Optional[str] = None   # strong / weak
    verb_class: Optional[str] = None
    is_sk_form: bool = False
    example_word: Optional[str] = None
    example_gloss: Optional[str] = None
    page_number: Optional[int] = None
    forms: list[ParadigmForm] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "paradigm_number": self.paradigm_number,
            "section":         self.section,
            "pos":             self.pos,
            "gender":          self.gender,
            "strength":        self.strength,
            "verb_class":      self.verb_class,
            "is_sk_form":      self.is_sk_form,
            "example_word":    self.example_word,
            "example_gloss":   self.example_gloss,
            "page_number":     self.page_number,
            "forms":           [vars(f) for f in self.forms],
        }


# ---------------------------------------------------------------------------
# PDF text extraction helpers
# ---------------------------------------------------------------------------

# Running page headers: "Noun inflexions and their function 29"
_PAGE_HEADER_RE = re.compile(
    r"^(?:Noun|Verb|Adjective|Pronoun|Numeral)\s+inflexions\s+and\s+their\s+function\s+\d+$",
    re.IGNORECASE,
)


_PAGE_MARKER_RE = re.compile(r"^__PDFPAGE:(\d+)__$")


def _extract_full_text(pdf_path: Path) -> str:
    """Extract text from all pages, injecting __PDFPAGE:N__ markers between pages."""
    parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(f"__PDFPAGE:{page.page_number}__")
            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            parts.append(text)
    return "\n".join(parts)


def _is_noise_line(line: str) -> bool:
    s = line.strip()
    if _PAGE_MARKER_RE.match(s):
        return False   # keep page markers so parsers can track page numbers
    if _PAGE_HEADER_RE.match(s):
        return True
    if re.match(r"^\d{1,3}$", s):
        return True
    return False


def _clean_lines(text: str) -> list[str]:
    lines = []
    for ln in text.splitlines():
        stripped = ln.strip()
        if not stripped:
            continue
        if _is_noise_line(stripped):
            continue
        lines.append(stripped)
    return lines


def _fix(s: str) -> str:
    return fix_pdf_encoding(s).strip()


def _expand_alternatives(form: str) -> list[str]:
    """Split 'form1/form2' into individual fixed forms."""
    return [_fix(p.strip()) for p in form.split("/") if p.strip()]


def _find_gloss(text: str) -> Optional[str]:
    """Return the first 'quoted' string in *text*, or None."""
    m = re.search(r"'([^']+)'", text)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------

def _get_section(full_text: str, heading: str) -> str:
    """Return the body text for a section heading, skipping TOC occurrences.

    TOC occurrences are followed by dots and a page number.
    The section ends at the '— Exercise' variant of the same heading.

    Prepends the most recent __PDFPAGE:N__ marker before the heading so that
    paradigms on the same page as the heading receive a page number.
    """
    end_heading = heading + " — Exercise"
    start = 0
    body_start = -1

    while True:
        idx = full_text.find(heading, start)
        if idx == -1:
            return ""
        line_end = full_text.find("\n", idx)
        suffix = full_text[idx + len(heading) : line_end]
        # TOC lines look like: "....... 47" — skip them
        if not re.match(r"[\s.]+\d+$", suffix.strip() or " "):
            body_start = idx
            break
        start = idx + 1

    exercise_start = full_text.find(end_heading, body_start + len(heading))
    if exercise_start == -1:
        exercise_start = len(full_text)

    section = full_text[body_start:exercise_start]

    # Find the last page marker in the text before body_start and prepend it
    # so parsers know the page of paradigms that open the section.
    prefix_text = full_text[:body_start]
    last_marker = None
    for m in re.finditer(r"^__PDFPAGE:(\d+)__$", prefix_text, re.MULTILINE):
        last_marker = m.group(0)
    if last_marker:
        section = last_marker + "\n" + section

    return section


# ---------------------------------------------------------------------------
# Noun paradigm parser  (section 3.1.8)
# ---------------------------------------------------------------------------

_NOUN_TYPE_HEADER   = re.compile(r"^(Strong|Weak)\s+(masculine|feminine|neuter)", re.IGNORECASE)
_NOUN_PARADIGM_HDR  = re.compile(r"^\((\d+)\)")
_NOUN_FIRST_ROW     = re.compile(r"^Sg\.\s+nom\.\s+(\S+)\s+Pl\.\s+nom\.\s+(\S+)")
_NOUN_CASE_ROW      = re.compile(r"^(acc|gen|dat)\.\s+(\S+)\s+(?:acc|gen|dat)\.\s+(\S+)")
_NOUN_INVARIANT_ROW = re.compile(r"^Sg\.\s+nom\.,\s+acc\.,\s+gen\.,\s+dat\.\s+(\S+)")


def _parse_noun_paradigms(section_text: str) -> list[Paradigm]:
    lines = _clean_lines(section_text)
    paradigms: list[Paradigm] = []
    current_strength: Optional[str] = None
    current_gender: Optional[str] = None
    current: Optional[Paradigm] = None
    current_page: Optional[int] = None

    for ln in lines:
        pm = _PAGE_MARKER_RE.match(ln)
        if pm:
            current_page = int(pm.group(1))
            continue

        m = _NOUN_TYPE_HEADER.match(ln)
        if m:
            current_strength = m.group(1).lower()
            current_gender = m.group(2).lower()[0]   # m / f / n
            continue

        m = _NOUN_PARADIGM_HDR.match(ln)
        if m:
            current = Paradigm(
                paradigm_number=m.group(1),
                section="3.1.8",
                pos="noun",
                gender=current_gender,
                strength=current_strength,
                page_number=current_page,
            )
            rest = ln[m.end():].strip()
            if rest:
                tokens = rest.split()
                current.example_word = _fix(tokens[0]) if tokens else None
                current.example_gloss = _find_gloss(rest)
            paradigms.append(current)
            continue

        if current is None:
            continue

        m = _NOUN_INVARIANT_ROW.match(ln)
        if m:
            form_str = _fix(m.group(1))
            for number in ("sg", "pl"):
                for case in ("nom", "acc", "gen", "dat"):
                    for alt in _expand_alternatives(form_str):
                        current.forms.append(ParadigmForm(form=alt, case_=case, number=number))
            continue

        m = _NOUN_FIRST_ROW.match(ln)
        if m:
            for alt in _expand_alternatives(m.group(1)):
                current.forms.append(ParadigmForm(form=alt, case_="nom", number="sg"))
            for alt in _expand_alternatives(m.group(2)):
                current.forms.append(ParadigmForm(form=alt, case_="nom", number="pl"))
            continue

        m = _NOUN_CASE_ROW.match(ln)
        if m:
            case = m.group(1).lower()
            for alt in _expand_alternatives(m.group(2)):
                current.forms.append(ParadigmForm(form=alt, case_=case, number="sg"))
            for alt in _expand_alternatives(m.group(3)):
                current.forms.append(ParadigmForm(form=alt, case_=case, number="pl"))

    return paradigms


# ---------------------------------------------------------------------------
# Adjective paradigm parser  (section 3.3.9)
# ---------------------------------------------------------------------------
# Format:
#   Strong inflexion
#   (1) Basic pattern: sjúkr 'ill'
#   m. f. n.
#   Sg. nom. sjúkr sjúk sjúkt
#   acc. sjúkan sjúka sjúkt
#   gen. sjúks sjúkrar sjúks
#   dat. sjúkum sjúkri sjúku
#   Pl. nom. sjúkir sjúkar sjúk
#   ...
# ---------------------------------------------------------------------------

_ADJ_STRENGTH    = re.compile(r"^(Strong|Weak)\s+inflexion", re.IGNORECASE)
_ADJ_PARADIGM_HDR = re.compile(r"^\((\d+)\)")
_ADJ_MFN_LINE    = re.compile(r"^m\.\s+f\.\s+n\.", re.IGNORECASE)
_ADJ_SG_PL_ROW   = re.compile(
    r"^(Sg|Pl)\.\s+(nom|acc|gen|dat)\.\s+(\S+)\s+(\S+)\s+(\S+)",
    re.IGNORECASE,
)
_ADJ_CASE_ROW    = re.compile(
    r"^(nom|acc|gen|dat)\.\s+(\S+)\s+(\S+)\s+(\S+)",
    re.IGNORECASE,
)


def _parse_adjective_paradigms(section_text: str) -> list[Paradigm]:
    lines = _clean_lines(section_text)
    paradigms: list[Paradigm] = []
    current_strength: Optional[str] = None
    current: Optional[Paradigm] = None
    current_number: Optional[str] = None   # sg / pl within current paradigm
    current_page: Optional[int] = None

    for ln in lines:
        pm = _PAGE_MARKER_RE.match(ln)
        if pm:
            current_page = int(pm.group(1))
            continue

        m = _ADJ_STRENGTH.match(ln)
        if m:
            current_strength = m.group(1).lower()
            continue

        m = _ADJ_PARADIGM_HDR.match(ln)
        if m:
            current = Paradigm(
                paradigm_number=m.group(1),
                section="3.3.9",
                pos="adjective",
                strength=current_strength,
                page_number=current_page,
            )
            rest = ln[m.end():].strip()
            if rest:
                # Description before colon, then WORD 'gloss'
                after_colon = rest.split(":", 1)[-1].strip()
                tokens = after_colon.split()
                current.example_word = _fix(tokens[0]) if tokens else None
                current.example_gloss = _find_gloss(rest)
            paradigms.append(current)
            current_number = None
            continue

        if current is None:
            continue

        if _ADJ_MFN_LINE.match(ln):
            continue   # skip "m. f. n." header line

        m = _ADJ_SG_PL_ROW.match(ln)
        if m:
            current_number = m.group(1).lower()   # sg / pl
            case = m.group(2).lower()
            for gender, raw_form in zip(("m", "f", "n"), (m.group(3), m.group(4), m.group(5))):
                for alt in _expand_alternatives(raw_form):
                    current.forms.append(
                        ParadigmForm(form=alt, case_=case, number=current_number, gender=gender)
                    )
            continue

        m = _ADJ_CASE_ROW.match(ln)
        if m:
            case = m.group(1).lower()
            for gender, raw_form in zip(("m", "f", "n"), (m.group(2), m.group(3), m.group(4))):
                for alt in _expand_alternatives(raw_form):
                    current.forms.append(
                        ParadigmForm(form=alt, case_=case, number=current_number, gender=gender)
                    )

    return paradigms


# ---------------------------------------------------------------------------
# Verb paradigm parser  (section 3.6.10)
# ---------------------------------------------------------------------------
# Format:
#   Strong verb (type 2): skjóta 'shoot'
#   Present indicative Present subjunctive
#   ek sk‡t ek skjóta
#   flú sk‡tr flú skjótir
#   ...
#   Past indicative Past subjunctive
#   ek skaut ek skyta
#   ...
#   Imperative skjót
#   Infinitive skjóta
#   Present participle skjótandi
#   Past participle skotit
# ---------------------------------------------------------------------------

_VERB_TYPE_HDR = re.compile(
    r"^(Strong|Weak|Irregular|Preterite[- ]present)\s+verb(?:\s+\(type\s+(\d+)\))?:\s+(\S+)",
    re.IGNORECASE,
)
_TENSE_MOOD_HDR = re.compile(
    r"^(Present|Past)\s+indicative\s+(Present|Past)\s+subjunctive",
    re.IGNORECASE,
)
_VERB_CONJ_ROW = re.compile(
    r"^(ek|flú|hann|vér|flér|fleir)\s+(\S+)\s+(ek|flú|hann|vér|flér|fleir)\s+(\S+)",
    re.IGNORECASE,
)
_VERB_IMPERATIVE  = re.compile(r"^Imperative\s+(\S+)", re.IGNORECASE)
_VERB_INFINITIVE  = re.compile(r"^Infinitive\s+(\S+)", re.IGNORECASE)
_VERB_PRES_PART   = re.compile(r"^Present participle\s+(\S+)", re.IGNORECASE)
_VERB_PAST_PART   = re.compile(r"^Past participle\s+(\S+)", re.IGNORECASE)

_PRONOUN_INFO: dict[str, tuple[str, str]] = {
    "ek":    ("1", "sg"),
    "flú":   ("2", "sg"),
    "hann":  ("3", "sg"),
    "vér":   ("1", "pl"),
    "flér":  ("2", "pl"),
    "fleir": ("3", "pl"),
}


def _parse_verb_paradigms(section_text: str) -> list[Paradigm]:
    lines = _clean_lines(section_text)
    paradigms: list[Paradigm] = []
    current: Optional[Paradigm] = None
    para_counter = 0
    # Two-column tense/mood: [(tense1, mood1), (tense2, mood2)]
    current_cols: list[tuple[str, str]] = []
    current_page: Optional[int] = None

    for ln in lines:
        pm = _PAGE_MARKER_RE.match(ln)
        if pm:
            current_page = int(pm.group(1))
            continue

        m = _VERB_TYPE_HDR.match(ln)
        if m:
            para_counter += 1
            verb_type = m.group(1).lower()
            verb_class_num = m.group(2)       # "2", "6", "1" etc. or None
            example_raw = m.group(3)

            strength = None
            if "strong" in verb_type:
                strength = "strong"
            elif "weak" in verb_type:
                strength = "weak"

            # Check for -sk suffix
            is_sk = example_raw.endswith("sk") or example_raw.endswith("sk'")

            current = Paradigm(
                paradigm_number=str(para_counter),
                section="3.6.10",
                pos="verb",
                strength=strength,
                verb_class=verb_class_num,
                is_sk_form=is_sk,
                example_word=_fix(example_raw),
                example_gloss=_find_gloss(ln),
                page_number=current_page,
            )
            paradigms.append(current)
            current_cols = []
            continue

        if current is None:
            continue

        m = _TENSE_MOOD_HDR.match(ln)
        if m:
            # "Present indicative  Present subjunctive"
            # Abbreviate "present" → "pres", keep "past"
            def _t(s: str) -> str:
                return "pres" if s.lower() == "present" else "past"
            current_cols = [
                (_t(m.group(1)), "indic"),
                (_t(m.group(2)), "subj"),
            ]
            continue

        m = _VERB_CONJ_ROW.match(ln)
        if m and len(current_cols) == 2:
            pron1 = m.group(1).lower()
            form1 = m.group(2)
            pron2 = m.group(3).lower()
            form2 = m.group(4)
            (tense1, mood1) = current_cols[0]
            (tense2, mood2) = current_cols[1]
            person1, number1 = _PRONOUN_INFO.get(pron1, (None, None))
            person2, number2 = _PRONOUN_INFO.get(pron2, (None, None))
            for alt in _expand_alternatives(form1):
                current.forms.append(ParadigmForm(
                    form=alt, person=person1, number=number1,
                    tense=tense1, mood=mood1,
                ))
            for alt in _expand_alternatives(form2):
                current.forms.append(ParadigmForm(
                    form=alt, person=person2, number=number2,
                    tense=tense2, mood=mood2,
                ))
            continue

        m = _VERB_IMPERATIVE.match(ln)
        if m and m.group(1).lower() != "lacking":
            for alt in _expand_alternatives(m.group(1)):
                current.forms.append(ParadigmForm(form=alt, mood="imp", person="2", number="sg"))
            continue

        m = _VERB_INFINITIVE.match(ln)
        if m:
            for alt in _expand_alternatives(m.group(1)):
                current.forms.append(ParadigmForm(form=alt, mood="infin"))
            continue

        m = _VERB_PRES_PART.match(ln)
        if m:
            for alt in _expand_alternatives(m.group(1)):
                current.forms.append(ParadigmForm(form=alt, mood="pres_part", tense="pres"))
            continue

        m = _VERB_PAST_PART.match(ln)
        if m:
            for alt in _expand_alternatives(m.group(1)):
                current.forms.append(ParadigmForm(form=alt, mood="past_part", tense="past"))

    return paradigms


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_NOUN_SECTION_HDG = "3.1.8 Examples of noun inflexion"
_ADJ_SECTION_HDG  = "3.3.9 Examples of adjective inflexion"
_VERB_SECTION_HDG = "3.6.10 Examples of verb inflexion"


def extract_paradigms(pdf_path: Path) -> list[dict]:
    """Parse the grammar PDF and return a list of paradigm dicts.

    Each dict has the keys defined in :class:`Paradigm` plus a ``forms`` key
    containing a list of :class:`ParadigmForm` dicts.
    """
    full_text = _extract_full_text(pdf_path)

    noun_section = _get_section(full_text, _NOUN_SECTION_HDG)
    adj_section  = _get_section(full_text, _ADJ_SECTION_HDG)
    verb_section = _get_section(full_text, _VERB_SECTION_HDG)

    paradigms: list[Paradigm] = []
    paradigms.extend(_parse_noun_paradigms(noun_section))
    paradigms.extend(_parse_adjective_paradigms(adj_section))
    paradigms.extend(_parse_verb_paradigms(verb_section))

    return [p.to_dict() for p in paradigms]
