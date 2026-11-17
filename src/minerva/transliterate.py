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


def _contains_precomposed_greek(text: str) -> bool:
    """True when ``text`` already carries Unicode Greek codepoints —
    Greek and Coptic (U+0370–03FF) or Greek Extended (U+1F00–1FFF,
    the precomposed polytonic block)."""

    return any(0x0370 <= ord(ch) <= 0x03FF or 0x1F00 <= ord(ch) <= 0x1FFF for ch in text)


def looks_like_betacode(text: str) -> bool:
    """Heuristic: is this string beta-code-encoded Greek?

    Two guards, both needed:

    * Already-Unicode polytonic Greek is NOT beta-code, full stop —
      even when it contains ASCII punctuation that doubles as a
      beta-code marker (parentheses, slashes, ``+``). The old
      any-marker check converted every ASCII letter in such chunks
      (a parenthetical "cf." became Greek gibberish) at display time
      AND at ingest.
    * A marker character alone is not evidence either ("Letter 7",
      "Republic" — some Perseus `gr` rows ship already-Latin titles).
      Require an actual beta-code letter+marker sequence: a letter
      from the beta-code base table immediately followed by a
      diacritic marker (``a)``, ``h=``, ``w|``), or a ``*`` capital
      marker introducing a base letter (``*a``, ``*(i``).
    """

    if _contains_precomposed_greek(text):
        return False
    n = len(text)
    for i, ch in enumerate(text):
        if ch == "*":
            # Capital marker: '*' + optional diacritics + base letter.
            j = i + 1
            while j < n and text[j] in _DIACRITIC_CHARS:
                j += 1
            if j < n and text[j].lower() in _GREEK_BASE:
                return True
        elif ch in _DIACRITIC_CHARS and i > 0 and text[i - 1].lower() in _GREEK_BASE:
            # Diacritics follow the letter they modify in beta-code.
            return True
    return False


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
