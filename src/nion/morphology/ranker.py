"""Rank morphological analyses by reliability using available context."""

from __future__ import annotations

from nion.encoding import normalize_for_search

# Prepositions that unambiguously govern a single case in Old Norse.
# Prepositions taking two cases (í, á, við, fyrir, undir, yfir, eptir, með)
# are intentionally omitted — their case depends on motion vs. location context
# that we cannot resolve without a full syntactic parse.
#
# Keys are search-normalized (normalize_for_search applied).
_PREP_CASE: dict[str, str] = {
    # Genitive
    "til":     "gen",   # to, until
    "utan":    "gen",   # outside of, except
    "innan":   "gen",   # within
    "milli":   "gen",   # between
    "millum":  "gen",   # between (variant)
    "medal":   "gen",   # meðal — among
    "sakir":   "gen",   # for the sake of
    "vegna":   "gen",   # on account of
    "ofan":    "gen",   # down from
    "nedan":   "gen",   # neðan — from below
    "sunnan":  "gen",   # from the south
    "nordan":  "gen",   # norðan — from the north
    "austan":  "gen",   # from the east
    "vestan":  "gen",   # from the west
    # Dative
    "af":      "dat",   # from, of
    "fra":     "dat",   # frá — from
    "at":      "dat",   # at, to
    "hja":     "dat",   # hjá — beside, with
    "ur":      "dat",   # úr — out of
    "or":      "dat",   # ór — out of (variant)
    "gegn":    "dat",   # against, opposite
    "moti":    "dat",   # móti — against, towards
    "mot":     "dat",   # mót — variant
    "naer":    "dat",   # nær — near
    "gagnvart":"dat",   # opposite
    # Accusative
    "um":      "acc",   # about, around, during
    "of":      "acc",   # about (poetic variant of um)
    "gegnum":  "acc",   # through
    "kringum": "acc",   # around
    "thvert":  "acc",   # þvert — across
}


def rank_analyses(
    results: list[dict],
    preceding_token: str | None = None,
) -> list[dict]:
    """Return *results* reordered by reliability.

    Currently applies one rule: if *preceding_token* is a preposition that
    unambiguously governs a single case, results matching that case are moved
    to the front.  All other results follow in their original order.

    This is intentionally conservative — only deterministic signals are used.
    """
    if not results or preceding_token is None:
        return results

    governed_case = _PREP_CASE.get(normalize_for_search(preceding_token))
    if governed_case is None:
        return results

    boosted = [r for r in results if r.get("case_") == governed_case]
    rest    = [r for r in results if r.get("case_") != governed_case]
    return boosted + rest
