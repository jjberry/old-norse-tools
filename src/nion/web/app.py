"""FastAPI web application for the Old Norse analysis tool."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from nion.db.schema import get_connection
from nion.encoding import normalize_for_search
from nion.morphology.parser import parse_form
from nion.morphology.ranker import rank_analyses

DATA_DIR      = Path(__file__).parent.parent.parent.parent / "data"
DB_PATH       = DATA_DIR / "nion.db"
PDF_DIR       = DATA_DIR / "pdfs"
TEMPLATES_DIR = Path(__file__).parent / "templates"

app       = FastAPI(title="Old Norse Tools")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.mount("/pdfs", StaticFiles(directory=str(PDF_DIR)), name="pdfs")

_conn = None


def _get_conn():
    global _conn
    if _conn is None:
        _conn = get_connection(DB_PATH)
    return _conn


# ---------------------------------------------------------------------------
# Morphology formatting (parallel to analyze.py, adapted for HTML context)
# ---------------------------------------------------------------------------

def _morph_str(r: dict) -> str:
    if r.get("pos") == "verb":
        mood = r.get("mood") or ""
        if mood == "infin":      return "infin"
        if mood == "past_part":  return "past.part"
        if mood == "pres_part":  return "pres.part"
        if mood == "imp":
            num = r.get("number") or ""
            return f"imp.{num}" if num else "imp"
        person = r.get("person") or ""
        number = r.get("number") or ""
        tense  = r.get("tense")  or ""
        tag = f"{person}{number}".strip()
        if tense == "past":  tag += " past"
        elif tense == "pres": tag += " pres"
        if mood == "subj":   tag += ".subj"
        return tag.strip()
    else:
        case_  = r.get("case_")  or ""
        number = r.get("number") or ""
        gender = r.get("gender") or ""
        morph  = f"{case_}.{number}" if (case_ and number) else case_ or number
        return f"{morph} {gender}".strip() if gender else morph


_CITATION_RE = re.compile(r"\s+[IVX]+(?:\s+[A-Z])?:\d.*$", re.DOTALL)
_LEAD_GR_RE  = re.compile(r"^\s*\(?\s*Gr\s+[\d.]+.*?\)\s*")
_LEAD_NUM_RE = re.compile(r"^\d+\.\s*")


def _short_defn(defn: str) -> str:
    """Short gloss for inline display (same trim logic as the CLI)."""
    defn = _LEAD_GR_RE.sub("", defn).strip()
    defn = _LEAD_NUM_RE.sub("", defn).strip()
    defn = _CITATION_RE.sub("", defn).strip()
    defn = defn.split("  ")[0].strip()
    if len(defn) > 80:
        defn = defn[:77].rstrip() + "…"
    return defn


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

_CASE_ORDER = {"nom": 0, "acc": 1, "dat": 2, "gen": 3}
_NUM_ORDER  = {"sg": 0, "pl": 1, "du": 2}


def _sort_key(r: dict) -> tuple:
    return (
        _CASE_ORDER.get(r.get("case_") or "", 9),
        _NUM_ORDER.get(r.get("number") or "", 9),
        r.get("person") or "",
    )


def _dedupe(results: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out:  list[dict] = []
    for r in results:
        key = (r.get("headword") or r.get("form"), _morph_str(r))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _build_token_data(tokens: list[str], conn) -> list[dict]:
    """Return one dict per token with analyses and unique entry details."""
    token_data = []
    prev: str | None = None

    for token in tokens:
        raw      = parse_form(token, conn)
        sorted_  = _dedupe(sorted(raw, key=_sort_key))
        results  = rank_analyses(sorted_, prev)
        prev     = token

        # Build analysis rows for display
        rows = []
        for r in results:
            rows.append({
                "headword_display": r.get("headword") or r.get("form") or "?",
                "pos":          r.get("pos") or "",
                "entry_gender": r.get("entry_gender") or "",
                "strength":     r.get("strength") or "",
                "morph":        _morph_str(r),
                "defn_short":   _short_defn(r.get("definition") or ""),
                "source":       r.get("source", "paradigm"),
            })

        # Build unique entry cards for the expandable panel (paradigm only)
        seen_entries: set = set()
        entries = []
        for r in results:
            if r.get("source") != "paradigm":
                continue
            eid = r.get("entry_id")
            if eid in seen_entries:
                continue
            seen_entries.add(eid)
            glossary_page = r.get("glossary_page")
            grammar_page  = r.get("grammar_page")
            entries.append({
                "headword":        r.get("headword") or "",
                "pos":             r.get("pos") or "",
                "gender":          r.get("entry_gender") or "",
                "strength":        r.get("strength") or "",
                "definition":      r.get("definition") or "",
                "grammar_ref":     r.get("grammar_ref") or "",
                "principal_parts": r.get("principal_parts") or "",
                "text_refs":       r.get("text_refs") or "",
                "glossary_url":    f"/pdfs/glossary.pdf#page={glossary_page}" if glossary_page else None,
                "grammar_url":     f"/pdfs/grammar.pdf#page={grammar_page}"   if grammar_page  else None,
            })

        # If only annotation results, build a minimal entry card
        annotation_only = bool(results) and not entries
        annotation_entry = None
        if annotation_only:
            r0 = results[0]
            annotation_entry = {
                "headword":  r0.get("headword") or token,
                "pos":       r0.get("pos") or "",
                "gloss":     r0.get("definition") or "",
                "morph":     _morph_str(r0),
            }

        token_data.append({
            "token":            token,
            "rows":             rows,
            "entries":          entries,
            "annotation_only":  annotation_only,
            "annotation_entry": annotation_entry,
            "no_match":         not results,
        })

    return token_data


# ---------------------------------------------------------------------------
# Paradigm table builders for the lookup view
# ---------------------------------------------------------------------------

_CASES   = ["nom", "acc", "dat", "gen"]
_NUMBERS = ["sg", "pl"]
_GENDERS = ["m", "f", "n"]

_VERB_SECTIONS = [
    ("Present indicative",  "pres", "indic"),
    ("Past indicative",     "past", "indic"),
    ("Present subjunctive", "pres", "subj"),
    ("Past subjunctive",    "past", "subj"),
]

_NON_FINITE_LABELS = {
    "infin":     "infinitive",
    "imp":       "imperative",
    "pres_part": "pres. participle",
    "past_part": "past participle",
}


def _cell(form_map: dict, *keys) -> str:
    """Return ' / '-joined forms for a cell, or '—' if none."""
    forms = form_map.get(keys, [])
    return " / ".join(sorted(set(forms))) if forms else "—"


def _build_noun_table(forms: list[dict]) -> dict:
    fm: dict = {}
    for f in forms:
        key = (f["case_"], f["number"])
        fm.setdefault(key, []).append(f["form"])
    rows = [
        (case, _cell(fm, case, "sg"), _cell(fm, case, "pl"))
        for case in _CASES
    ]
    return {"type": "noun", "rows": rows}


def _build_adj_table(forms: list[dict]) -> dict:
    fm: dict = {}
    for f in forms:
        key = (f["case_"], f["number"], f["gender"])
        fm.setdefault(key, []).append(f["form"])
    rows = []
    for case in _CASES:
        row = [case]
        for num in _NUMBERS:
            for gen in _GENDERS:
                row.append(_cell(fm, case, num, gen))
        rows.append(row)
    return {"type": "adjective", "rows": rows}


def _build_verb_table(forms: list[dict]) -> dict:
    fm: dict = {}
    for f in forms:
        key = (f["mood"], f["tense"], f["person"], f["number"])
        fm.setdefault(key, []).append(f["form"])

    sections = []
    for label, tense, mood in _VERB_SECTIONS:
        rows = []
        for person in ("1", "2", "3"):
            sg = _cell(fm, mood, tense, person, "sg")
            pl = _cell(fm, mood, tense, person, "pl")
            if sg != "—" or pl != "—":
                rows.append((person, sg, pl))
        if rows:
            sections.append({"label": label, "rows": rows})

    # Non-finite forms
    nf_rows = []
    for mood_key, label in _NON_FINITE_LABELS.items():
        # imp uses tense=None; inf/parts use tense from the key
        forms_imp  = fm.get((mood_key, None, "2", "sg"), [])
        forms_nf   = fm.get((mood_key, "pres" if mood_key == "pres_part" else
                                        "past" if mood_key == "past_part" else None,
                              None, None), [])
        combined = forms_imp or forms_nf
        if combined:
            nf_rows.append((label, " / ".join(sorted(set(combined)))))
    if nf_rows:
        sections.append({"label": "Non-finite", "rows": nf_rows, "non_finite": True})

    return {"type": "verb", "sections": sections}


def _build_lookup_result(entry_row, conn) -> dict:
    """Build a full lookup result dict for one entry row."""
    eid   = entry_row["id"]
    pos   = entry_row["pos"]
    forms = conn.execute(
        "SELECT case_, number, gender, person, mood, tense, form "
        "FROM forms WHERE entry_id = ? ORDER BY tense, mood, case_, number, gender, person",
        (eid,),
    ).fetchall()
    forms = [dict(f) for f in forms]

    if pos == "noun":
        table = _build_noun_table(forms)
    elif pos == "adjective":
        table = _build_adj_table(forms)
    elif pos == "verb":
        table = _build_verb_table(forms)
    else:
        table = None

    glossary_page = entry_row["page_number"]
    par = conn.execute(
        "SELECT page_number FROM paradigms WHERE id = ?",
        (entry_row["paradigm_id"],),
    ).fetchone() if entry_row["paradigm_id"] else None
    grammar_page = par["page_number"] if par else None

    return {
        "headword":        entry_row["headword"],
        "pos":             pos,
        "gender":          entry_row["gender"] or "",
        "strength":        entry_row["strength"] or "",
        "definition":      entry_row["definition"] or "",
        "grammar_ref":     entry_row["grammar_ref"] or "",
        "principal_parts": entry_row["principal_parts"] or "",
        "glossary_url":    f"/pdfs/glossary.pdf#page={glossary_page}" if glossary_page else None,
        "grammar_url":     f"/pdfs/grammar.pdf#page={grammar_page}"   if grammar_page  else None,
        "table":           table,
    }


def _lookup_entries(query: str, conn) -> list[dict]:
    """Search entries by headword, exact then prefix fallback."""
    norm = normalize_for_search(query)
    rows = conn.execute(
        "SELECT * FROM entries WHERE headword_normalized = ? AND pos != 'xref' ORDER BY headword",
        (norm,),
    ).fetchall()
    if not rows:
        rows = conn.execute(
            "SELECT * FROM entries WHERE headword_normalized LIKE ? AND pos != 'xref' ORDER BY headword LIMIT 12",
            (norm + "%",),
        ).fetchall()
    return [_build_lookup_result(r, conn) for r in rows]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html",
        {"token_data": [], "query": "", "lookup_query": "", "lookup_results": []},
    )


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request, text: str = Form(...)):
    conn = _get_conn()
    # Simple tokenizer (mirrors the CLI)
    tokens = [w.strip(".,;:!?()[]{}\"'—–-«»") for w in text.split()]
    tokens = [t for t in tokens if t]

    token_data = _build_token_data(tokens, conn) if tokens else []

    return templates.TemplateResponse(
        request, "index.html",
        {"token_data": token_data, "query": text, "lookup_query": "", "lookup_results": []},
    )


@app.post("/lookup", response_class=HTMLResponse)
async def lookup(request: Request, headword: str = Form(...)):
    conn = _get_conn()
    results = _lookup_entries(headword.strip(), conn) if headword.strip() else []
    return templates.TemplateResponse(
        request, "index.html",
        {"token_data": [], "query": "", "lookup_query": headword.strip(), "lookup_results": results},
    )
