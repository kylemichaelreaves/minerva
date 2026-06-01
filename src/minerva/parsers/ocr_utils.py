"""Shared OCR plain-text normalization helpers.

German/Latin OCR parsers (``marx_de``, ``hobbes_la``) share chapter-head
detection patterns; text normalization delegates to ``tei._norm_text``.
"""

from __future__ import annotations

import re

from ..tei import _norm_text

# Common Fraktur/Latin OCR chapter heads (Marx Kapital, Hobbes CAPVT).
_CHAPTER_HEAD_RE = re.compile(
    r"^(?:CAPVT|CAPIT|KAPITEL|Kapitel|Capitel|CHAPTER)\s+",
    re.IGNORECASE | re.MULTILINE,
)


def norm_ocr_line(text: str) -> str:
    """Normalize a line of OCR plain text for chunk emission."""
    return _norm_text(text)


def is_chapter_head(line: str) -> bool:
    return bool(_CHAPTER_HEAD_RE.match(line.strip()))
