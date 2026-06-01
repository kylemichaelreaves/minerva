"""Perseus beta-code → polytonic Unicode Greek.

Perseus TEI bundles encode Greek in beta-code (ASCII transliteration) so
the files round-trip through any text editor. Chunks store the original
beta-code verbatim — see the README's "Bilingual storage" note. This
module converts beta-code strings to display-ready polytonic Unicode
for the UI; the on-disk form is unchanged.

Used by the server's works listing so the sidebar shows "Ἵππαρχος"
instead of "*(ippa/rxos". Keep it dependency-free.

Beta-code conventions (Perseus flavour):

* Letters       — ``a..w`` map to α..ω; word-final σ becomes ς.
* Capitals      — leading ``*`` uppercases the next letter, with any
                  diacritic markers placed BEFORE the letter
                  (``*(I`` = Ἱ).
* Breathings    — ``)`` smooth, ``(`` rough.
* Accents       — ``/`` acute, ``\\`` grave, ``=`` circumflex.
* Iota subscript — ``|`` after the vowel.
* Diaeresis     — ``+`` after the vowel.
"""

from __future__ import annotations

import unicodedata

_GREEK_BASE = {
    "a": "α",
    "b": "β",
    "g": "γ",
    "d": "δ",
    "e": "ε",
    "z": "ζ",
    "h": "η",
    "q": "θ",
    "i": "ι",
    "k": "κ",
    "l": "λ",
    "m": "μ",
    "n": "ν",
    "c": "ξ",
    "o": "ο",
    "p": "π",
    "r": "ρ",
    "s": "σ",
    "t": "τ",
    "u": "υ",
    "f": "φ",
    "x": "χ",
    "y": "ψ",
    "w": "ω",
}

# Combining diacritics, ordered so NFC composition picks the right
# precomposed glyph. The order matches Unicode normalization rules:
# breathing → accent → iota subscript → diaeresis.
_DIACRITICS = {
    ")": "̓",  # combining comma above (smooth breathing)
    "(": "̔",  # combining reversed comma above (rough breathing)
    "/": "́",  # combining acute accent
    "\\": "̀",  # combining grave accent
    "=": "͂",  # combining greek perispomeni (circumflex)
    "|": "ͅ",  # combining greek ypogegrammeni (iota subscript)
    "+": "̈",  # combining diaeresis
}

_DIACRITIC_CHARS = frozenset(_DIACRITICS.keys())


def betacode_to_unicode(text: str) -> str:
    """Convert a Perseus beta-code string to polytonic Unicode Greek.

    Non-Greek runs (Latin letters not in the base table, digits,
    punctuation) pass through unchanged so titles like
    ``*)alkibia/dhs a`` produce "Ἀλκιβιάδης α" with the trailing 'α'
    handled correctly.
    """

    if not text:
        return text
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]

        # Capital marker: '*' is followed by optional diacritics, then
        # the letter. Diacritics applied to the lowercase base, then
        # the whole grapheme is uppercased (NFC then .upper() composes
        # to the precomposed capital with breathings, e.g., Ἱ).
        if ch == "*":
            i += 1
            diacritics: list[str] = []
            while i < n and text[i] in _DIACRITIC_CHARS:
                diacritics.append(_DIACRITICS[text[i]])
                i += 1
            if i >= n:
                break
            base_char = _GREEK_BASE.get(text[i].lower())
            if base_char is None:
                # Stray '*' before a non-Greek letter — emit the raw char.
                out.append(text[i])
                i += 1
                continue
            composed = unicodedata.normalize("NFC", base_char + "".join(diacritics))
            out.append(composed.upper())
            i += 1
            continue

        # Lowercase letter: emit base, then absorb any trailing
        # diacritics. End-of-word sigma (σ) collapses to final form (ς).
        base = _GREEK_BASE.get(ch.lower()) if ch.isalpha() else None
        if base is not None:
            i += 1
            diacritics = []
            while i < n and text[i] in _DIACRITIC_CHARS:
                diacritics.append(_DIACRITICS[text[i]])
                i += 1
            if base == "σ" and (i >= n or text[i].lower() not in _GREEK_BASE):
                base = "ς"
            out.append(unicodedata.normalize("NFC", base + "".join(diacritics)))
            continue

        # Everything else (spaces, digits, punctuation, Latin words like
        # "Letter 7") passes through unchanged.
        out.append(ch)
        i += 1

    return "".join(out)


_BETACODE_MARKERS = frozenset("*()/\\=|+")


def looks_like_betacode(text: str) -> bool:
    """A title is beta-code-encoded iff it carries any of the marker
    characters Perseus uses for diacritics and capitalisation. Some Plato
    `gr` rows in the Perseus bundles ship with already-Latin titles
    ("Letter 7", "Republic"); without this guard the converter would
    happily re-read them as Greek letters and produce gibberish like
    "ρεπυβλιξ"."""

    return any(ch in _BETACODE_MARKERS for ch in text)


def display_text(text: str, lang: str) -> str:
    """Render a Greek string for human display. For `grc` strings that
    carry beta-code markers, transliterate to polytonic Unicode; all
    other inputs pass through unchanged.

    The `lang == 'grc'` check on its own is too coarse on two axes:
    (1) Perseus's bilingual bundles ship a few `grc` rows with
    English-language titles (the Letters, Republic) that must pass
    through verbatim, and (2) some `grc` chunk bodies (First1KGreek
    bundles, e.g. Aristotle's Categories) are already polytonic
    Unicode and re-applying the beta-code map would mangle them.
    The marker test catches both cases.
    """

    if lang == "grc" and looks_like_betacode(text):
        return betacode_to_unicode(text)
    return text


# Back-compat alias for callers that still import the title-specific
# name. The function never actually depended on the input being a title.
display_title = display_text
