"""Shared OCR text-normalization primitives.

Single source of truth for the typographic-glyph normalization that
several ``scripts/clean-*.py`` OCR-cleanup passes (Rousseau,
Boulainvilliers, and the Gobineau / Renan / Hobbes shims that import
the Boulainvilliers pipeline) each used to redefine by hand. Keeping
one copy here removes the drift risk a prior audit flagged.

Scope is deliberately narrow: only the *verbatim-identical* core is
hoisted. Author- or language-specific operations (dictionary-guided
``f``→``s`` long-s repair, running-header strips, glyph-soup line
predicates) stay in their call sites because they legitimately differ
between sources — e.g. the long-s ``f``→``s`` pass false-positives on
German ``-schaft`` / ``-kraft`` and English ``different`` /
``sufficient``, so 19th-c authors skip it entirely.

Stdlib-only; importable as ``from minerva import textnorm`` or
``from minerva.textnorm import replace_long_s``.
"""

from __future__ import annotations

import unicodedata

# Typographic-ligature → ASCII decompositions. Covers the medial
# long-s (U+017F) plus the Unicode "Alphabetic Presentation Forms"
# ligatures (U+FB00–FB06) that EPUB / Google-Books OCR ships as atomic
# codepoints. Modern orthography expects them decomposed.
#
# This is the literal map both clean-rousseau-long-s.py and
# clean-boulainvilliers-texts.py defined independently (identical keys
# and values); it is the genuine common core.
LIGATURE_MAP: dict[str, str] = {
    # Long-s (medial s): U+017F. Not strictly a ligature but in the
    # same early-typography family — normalized in the same pass.
    "ſ": "s",  # ſ
    "ﬀ": "ff",  # ﬀ
    "ﬁ": "fi",  # ﬁ
    "ﬂ": "fl",  # ﬂ
    "ﬃ": "ffi",  # ﬃ
    "ﬄ": "ffl",  # ﬄ
    "ﬅ": "st",  # ﬅ
    "ﬆ": "st",  # ﬆ
}

# Just the long-s codepoint → plain ``s``. The narrowest shared op,
# exposed separately for call sites (e.g. Rousseau) that only care
# about long-s rather than the full ligature family.
LONG_S_MAP: dict[str, str] = {"ſ": "s"}


def replace_long_s(text: str) -> str:
    """Replace the medial long-s glyph (U+017F ``ſ``) with plain ``s``.

    Does not touch the other ligatures or run NFC normalization — use
    :func:`normalize_ligatures` for the full early-typography pass.
    """

    return text.replace("ſ", "s")


def normalize_ligatures(text: str) -> str:
    """Decompose long-s + U+FB00–FB06 ligatures, then NFC-normalize.

    Applies every :data:`LIGATURE_MAP` substitution and then NFC
    normalizes so any split combining marks (e.g. ``e`` + U+0301 → ``é``)
    re-compose. Idempotent.
    """

    for src, dst in LIGATURE_MAP.items():
        text = text.replace(src, dst)
    return unicodedata.normalize("NFC", text)
