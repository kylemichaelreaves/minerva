"""Shared Roman-numeral → int conversion for the source parsers.

One strict converter, used by ``hobbes_la`` / ``marx_de`` /
``ica_parse``. "Strict" means invalid input yields ``None`` — empty
strings and strings with any character outside I/V/X/L/C/D/M never
silently map to a number (an earlier per-module copy let unknown
characters contribute 0, so garbage produced wrong nonzero values).

OCR repair (glyph substitutions, internal whitespace) is deliberately
NOT here — it's scan-specific and belongs in a caller-side pre-pass;
see :func:`minerva.sources.hobbes_la._roman_to_int`.
"""

from __future__ import annotations

_ROMAN_VALUES = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}


def roman_to_int(roman: str) -> int | None:
    """Convert a Roman numeral string to int via the standard
    subtractive reading. Case-insensitive. Returns ``None`` for empty
    input or any character outside the Roman alphabet. Non-classical
    but decodable sequences ("IIII", "IL") are accepted — the source
    scans aren't typographically disciplined enough for stricter
    canonical-form validation."""

    if not roman:
        return None
    upper = roman.upper()
    if any(c not in _ROMAN_VALUES for c in upper):
        return None
    total = 0
    prev = 0
    for c in reversed(upper):
        v = _ROMAN_VALUES[c]
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    return total or None
