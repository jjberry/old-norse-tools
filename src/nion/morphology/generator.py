"""Generate all inflected forms for a lexical entry given its paradigm."""

from __future__ import annotations

import re

from nion.encoding import normalize_for_search


# ---------------------------------------------------------------------------
# Stem extraction
# ---------------------------------------------------------------------------

def _lcp(strings: list[str]) -> str:
    """Longest common prefix of a list of strings."""
    if not strings:
        return ""
    prefix = strings[0]
    for s in strings[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


def _compute_stem(example_word: str, form_strings: list[str]) -> str:
    """LCP of forms sharing the first 3 chars of example_word.

    Used for verb forms where ablaut grades diverge early.
    """
    prefix = example_word[:3] if len(example_word) >= 3 else example_word
    regular = [s for s in form_strings if s.startswith(prefix)]
    return _lcp(regular) if regular else _lcp(form_strings)


def _compute_stem_adaptive(citation: str, form_strings: list[str]) -> str:
    """Find the longest useful stem from the citation form outward.

    Tries prefix lengths from len(citation) down to 2, picking the prefix
    length that maximises the number of covered forms while yielding a stem
    of at least 2 chars.  This handles paradigms where the umlaut vowel
    diverges deep in the word (e.g. bardagi/bardǫgum).
    """
    best_stem = ""
    for prefix_len in range(2, len(citation) + 1):
        prefix = citation[:prefix_len]
        regular = [s for s in form_strings if s.startswith(prefix)]
        if len(regular) < 2:
            continue
        stem = _lcp(regular)
        if len(stem) >= 2:
            best_stem = stem
    return best_stem or _lcp(form_strings) or ""


def _derive_alternate_stem(new_primary: str, ex_primary: str, ex_secondary: str) -> str:
    """Apply to new_primary the same character substitutions that convert
    ex_primary → ex_secondary (e.g. the u-umlaut a→ǫ in the saga paradigm).

    Position is measured from the end so different-length stems align
    on their suffixes.  Only applies changes where the source character
    is present at the same relative position in new_primary.
    """
    if len(ex_primary) != len(ex_secondary):
        return new_primary

    result = list(new_primary)
    for i in range(len(ex_primary)):
        c_from, c_to = ex_primary[i], ex_secondary[i]
        if c_from != c_to:
            pos_from_end = len(ex_primary) - 1 - i
            new_pos = len(new_primary) - 1 - pos_from_end
            if 0 <= new_pos < len(new_primary) and result[new_pos] == c_from:
                result[new_pos] = c_to
    return "".join(result)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_result(new_form: str, f: dict) -> dict:
    return {
        "form":            new_form,
        "form_normalized": normalize_for_search(new_form),
        "case_":           f.get("case_"),
        "number":          f.get("number"),
        "gender":          f.get("gender"),
        "person":          f.get("person"),
        "mood":            f.get("mood"),
        "tense":           f.get("tense"),
    }


def _find_citation_form(all_forms: list[dict]) -> str | None:
    """Nom.sg form: prefer m gender (adjectives), fall back to genderless."""
    for f in all_forms:
        if f.get("case_") == "nom" and f.get("number") == "sg" and f.get("gender") == "m":
            return f["form"]
    for f in all_forms:
        if f.get("case_") == "nom" and f.get("number") == "sg" and f.get("gender") is None:
            return f["form"]
    return None


# ---------------------------------------------------------------------------
# Nominal inflection (nouns, adjectives, …)
# ---------------------------------------------------------------------------

def _generate_nominal_forms(
    headword: str, example_word: str, all_forms: list[dict]
) -> list[dict]:
    form_strings = [f["form"] for f in all_forms if f.get("form")]

    citation = _find_citation_form(all_forms)
    if citation is None:
        return []

    # Primary stem: longest useful stem anchored on the citation form.
    primary_stem = _compute_stem_adaptive(citation, form_strings)
    if not primary_stem or not citation.startswith(primary_stem):
        return []

    cit_ending = citation[len(primary_stem):]
    if cit_ending and headword.endswith(cit_ending):
        new_primary = headword[: -len(cit_ending)]
    else:
        new_primary = headword  # zero citation ending (e.g. laug, orð)

    # Detect a secondary stem for paradigms with systematic vowel alternation
    # (e.g. saga/sǫg-, vatn/vǫtn-, bardagi/bardǫgum).
    secondary_forms = [s for s in form_strings if not s.startswith(primary_stem)]
    secondary_stem: str | None = None
    new_secondary: str | None = None

    if secondary_forms:
        # The alternation only changes characters within the stem, not the length.
        # Truncate each secondary form to len(primary_stem) before computing LCP
        # so that shared case endings (e.g. the -u- in sǫgu/sǫgur/sǫgum) don't
        # inflate the apparent stem length.
        trunc = [s[: len(primary_stem)] for s in secondary_forms]
        sec = _lcp(trunc)
        if len(sec) == len(primary_stem) and len(sec) >= 2:
            secondary_stem = sec
            new_secondary = _derive_alternate_stem(new_primary, primary_stem, secondary_stem)

    results: list[dict] = []
    seen: set = set()

    for f in all_forms:
        form = f.get("form") or ""
        new_form: str | None = None

        if form.startswith(primary_stem):
            new_form = new_primary + form[len(primary_stem):]
        elif secondary_stem and new_secondary is not None and form.startswith(secondary_stem):
            new_form = new_secondary + form[len(secondary_stem):]

        if new_form is None:
            continue

        key = (new_form, f.get("case_"), f.get("number"), f.get("gender"))
        if key not in seen:
            seen.add(key)
            results.append(_make_result(new_form, f))

    return results


# ---------------------------------------------------------------------------
# Verbal inflection
# ---------------------------------------------------------------------------

def _generate_verb_forms(
    headword: str, example_word: str, all_forms: list[dict]
) -> list[dict]:
    """Two-stem approach: separate present stem and (where derivable) past stem.

    The past stem can only be derived mechanically when it is a prefix-extension
    of the present stem (class 2 weak verbs, e.g. flakka: pres "flakk-" →
    past "flakka-").  For verbs where the past stem diverges (strong verbs,
    class 1 weak verbs), only present-group forms are generated.
    """
    pres_group = [
        f for f in all_forms
        if f.get("tense") == "pres" or f.get("mood") in ("infin", "pres_part", "imp")
    ]
    past_group = [
        f for f in all_forms
        if f.get("tense") == "past" or f.get("mood") == "past_part"
    ]

    pres_strings = [f["form"] for f in pres_group if f.get("form")]
    if not pres_strings:
        return []

    pres_stem = _compute_stem(example_word, pres_strings)

    infin = next((f for f in pres_group if f.get("mood") == "infin"), None)
    if infin is None or not (infin["form"] or "").startswith(pres_stem):
        return []

    infin_ending = infin["form"][len(pres_stem):]
    if infin_ending and headword.endswith(infin_ending):
        new_pres_stem = headword[: -len(infin_ending)]
    else:
        new_pres_stem = headword

    results: list[dict] = []
    seen: set = set()

    for f in pres_group:
        form = f.get("form") or ""
        if not form.startswith(pres_stem):
            continue
        new_form = new_pres_stem + form[len(pres_stem):]
        key = (new_form, f.get("mood"), f.get("tense"), f.get("number"), f.get("person"))
        if key not in seen:
            seen.add(key)
            results.append(_make_result(new_form, f))

    # Past forms: only generate when past_stem is a prefix-extension of pres_stem.
    # This covers class 2 weak verbs (flakka: pres "flakk-" → past "flakka-").
    past_strings = [f["form"] for f in past_group if f.get("form")]
    if past_strings:
        past_stem = _compute_stem(example_word, past_strings)
        if past_stem and past_stem.startswith(pres_stem):
            extra = past_stem[len(pres_stem):]
            new_past_stem = new_pres_stem + extra
            for f in past_group:
                form = f.get("form") or ""
                if not form.startswith(past_stem):
                    continue
                new_form = new_past_stem + form[len(past_stem):]
                key = (new_form, f.get("mood"), f.get("tense"), f.get("number"), f.get("person"))
                if key not in seen:
                    seen.add(key)
                    results.append(_make_result(new_form, f))

    return results


# ---------------------------------------------------------------------------
# Strong verb generation from principal parts
# ---------------------------------------------------------------------------

# Patterns for extracting the four principal parts from the glossary string.
# Format: "pres. X, past Y, past pl. Z, pp. W"
# Some entries omit fields; some have grammar refs or alternates (X/Y or X, Y).

# _PP_PP_RE captures everything after "pp. (n. )?" up to the next field keyword.
# The negative lookahead on "," prevents stopping at commas that introduce
# alternate forms (e.g. "pp. búinn, búit/bút") while still stopping before
# a new field (e.g. "pp. gefinn, pp. n. gefit").
_PP_PRES_RE    = re.compile(r"\bpres\.\s+(\S+?)(?=\s*(?:,|Gr\b|$))")
_PP_PAST_SG_RE = re.compile(r"\bpast\s+(?!pl\.|subj\.)(\S+)")
_PP_PAST_PL_RE = re.compile(r"\bpast\s+pl\.\s+(\S+)")
_PP_PP_RE      = re.compile(
    r"\bpp\.\s+(?:n\.\s+)?"
    r"((?:[^,]|,(?!\s*(?:pres\.|past\b|pp\.|[A-Z]|$)))+)"
)

_FIELD_SEP_RE = re.compile(r"[/,]")


def _alts(raw: str) -> list[str]:
    """Split on '/' and ',' separators, strip punctuation, drop empty."""
    return [p.strip(" .,;") for p in _FIELD_SEP_RE.split(raw) if p.strip(" .,;")]


def _parse_principal_parts(pp_str: str) -> dict[str, list[str]]:
    """Extract key forms from a glossary principal-parts string.

    Returns a dict with keys pres_sg, past_sg, past_pl, pp — each a
    (possibly empty) list of alternate surface forms.
    """
    result: dict[str, list[str]] = {
        "pres_sg": [],
        "past_sg": [],
        "past_pl": [],
        "pp":      [],
    }
    m = _PP_PRES_RE.search(pp_str)
    if m:
        result["pres_sg"] = _alts(m.group(1))

    m = _PP_PAST_PL_RE.search(pp_str)
    if m:
        result["past_pl"] = _alts(m.group(1))

    m = _PP_PAST_SG_RE.search(pp_str)
    if m:
        result["past_sg"] = _alts(m.group(1))

    for m in _PP_PP_RE.finditer(pp_str):
        result["pp"].extend(_alts(m.group(1)))

    return result


def generate_strong_verb_forms(headword: str, pp_str: str) -> list[dict]:
    """Generate inflected forms for a strong verb using its principal parts.

    Covers: infinitive, present participle, imperative, present indicative
    (all persons/numbers), present subjunctive, past indicative (1/3sg, all pl),
    and past participle.

    Skips past 2sg indicative (dental suffix is too irregular) and past
    subjunctive (requires i-umlaut of the past-plural stem, which varies by
    class).  Also skips present 1pl umlaut for class 6/7 verbs — those verbs
    are handled by the existing paradigm extraction for fara/falla.
    """
    pp = _parse_principal_parts(pp_str)

    # Infinitive stem: strip -a (most verbs) or -ja (ja-infinitives)
    if headword.endswith("ja"):
        inf_stem = headword[:-2]
    elif headword.endswith("a"):
        inf_stem = headword[:-1]
    else:
        inf_stem = headword

    results: list[dict] = []
    seen:    set         = set()

    def add(form_str: str, **morph) -> None:
        for alt in _alts(form_str):
            if not alt:
                continue
            key = (normalize_for_search(alt),
                   morph.get("mood"), morph.get("tense"),
                   morph.get("person"), morph.get("number"))
            if key not in seen:
                seen.add(key)
                results.append({
                    "form":            alt,
                    "form_normalized": normalize_for_search(alt),
                    "case_":           None,
                    "gender":          None,
                    **morph,
                })

    # --- Infinitive & present participle ---
    add(headword,           mood="infin",     tense=None,   person=None, number=None)
    add(inf_stem + "andi",  mood="pres_part", tense="pres", person=None, number=None)

    # --- Imperative 2sg: bare infinitive stem (= base form without -a) ---
    add(inf_stem, mood="imp", tense=None, person="2", number="sg")

    # --- Present indicative ---
    for form in pp["pres_sg"]:
        add(form,              mood="indic", tense="pres", person="2", number="sg")
        add(form,              mood="indic", tense="pres", person="3", number="sg")
        # 1sg = 2/3sg minus final -r (e.g. ferr→fer, skýtr→skýt)
        if form.endswith("rr"):
            add(form[:-1],     mood="indic", tense="pres", person="1", number="sg")
        elif form.endswith("r"):
            add(form[:-1],     mood="indic", tense="pres", person="1", number="sg")

    add(inf_stem + "um",  mood="indic", tense="pres", person="1", number="pl")
    add(inf_stem + "ið",  mood="indic", tense="pres", person="2", number="pl")
    add(inf_stem + "a",   mood="indic", tense="pres", person="3", number="pl")

    # --- Present subjunctive ---
    add(inf_stem + "a",   mood="subj",  tense="pres", person="1", number="sg")
    add(inf_stem + "ir",  mood="subj",  tense="pres", person="2", number="sg")
    add(inf_stem + "i",   mood="subj",  tense="pres", person="3", number="sg")
    add(inf_stem + "im",  mood="subj",  tense="pres", person="1", number="pl")
    add(inf_stem + "ið",  mood="subj",  tense="pres", person="2", number="pl")
    add(inf_stem + "i",   mood="subj",  tense="pres", person="3", number="pl")

    # --- Past indicative ---
    for form in pp["past_sg"]:
        add(form, mood="indic", tense="past", person="1", number="sg")
        add(form, mood="indic", tense="past", person="3", number="sg")

    for form in pp["past_pl"]:
        add(form, mood="indic", tense="past", person="3", number="pl")
        # 1pl and 2pl: strip trailing -u to get the stem
        stem = form[:-1] if form.endswith("u") else form
        add(stem + "um",  mood="indic", tense="past", person="1", number="pl")
        add(stem + "uð",  mood="indic", tense="past", person="2", number="pl")

    # --- Past participle ---
    for form in pp["pp"]:
        add(form, mood="past_part", tense="past", person=None, number=None)

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_forms(headword: str, paradigm: dict) -> list[dict]:
    """Return all inflected forms for *headword* using the given *paradigm*.

    Each dict has keys: form, form_normalized, case_, number, gender,
    person, mood, tense.

    Forms whose paradigm stem diverges irrecoverably (e.g. strong-verb
    ablaut grades) are silently skipped.
    """
    example_word = paradigm.get("example_word") or ""
    all_forms = paradigm.get("forms", [])
    pos = paradigm.get("pos", "")

    if not example_word or not all_forms:
        return []

    if pos == "verb":
        return _generate_verb_forms(headword, example_word, all_forms)
    return _generate_nominal_forms(headword, example_word, all_forms)
