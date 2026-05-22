"""FastAPI web application for the Old Norse analysis tool."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from nion.db.schema import get_connection
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
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html",
        {"token_data": [], "query": ""},
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
        {"token_data": token_data, "query": text},
    )
