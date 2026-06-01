"""Heuristic text repair before splitting.

The two helpers here address shapes that show up in EPUB / PDF text
extraction and that, left unfixed, fool the section / paragraph
regexes downstream:

* ``_repair_crossref_linebreaks`` rejoins inline cross-references
  (``see § 6 above``) that PDF extraction wraps onto multiple lines,
  preventing the ``§6`` from being mistaken for a fresh section head.
* ``_looks_like_bibliography`` detects bibliographic listings so we
  can drop them before they pollute the author's chunks.
"""

from __future__ import annotations

import re

# Inline cross-references like ``(see § 14 above)`` get broken across
# lines by EPUB / PDF text extraction, leaving ``§ 14`` at the start of
# its own line where the §-splitter mistakes it for a real section head.
# We rejoin these onto a single line before splitting, so the §-marker
# is no longer at start-of-line and the regex skips it.
#
# Triggered when a §N is preceded (after intervening newline) by a
# short connector word — `see`, `cf.`, `to`, `of`, `for`, `Remarks`,
# etc. Real section heads are preceded by either a paragraph break or
# a chapter heading whose last word does not appear in this list.
_CROSSREF_OPENERS_RE = re.compile(
    r"\b(?:see\s+also|see|cf\.?|Remarks\s+to|Remarks|note|to|of|for"
    r"|and|or|in|on|at|by|with)\s*\n+\s*(§\s*\d+\b)",
    re.IGNORECASE,
)


def _repair_crossref_linebreaks(text: str) -> str:
    """Collapse `connector + newline + §N` onto a single line so the
    §-splitter doesn't mistake the §N for a fresh section head. Run
    iteratively until stable since adjacent cross-refs can chain."""
    prev = None
    while prev != text:
        prev = text
        text = _CROSSREF_OPENERS_RE.sub(lambda m: re.sub(r"\s*\n+\s*", " ", m.group(0)), text)
    return text


_BIB_AUTHOR_RE = re.compile(r"\b[A-Z][A-Z'’\-]{2,},\s+[A-Z][A-Z'’\-\.\s]{1,30}\.")
_BIB_CITY_YEAR_RE = re.compile(
    r"\b[A-Z][a-zA-Z\-éüöäß]+(?:\s+[A-Z][a-zA-Z]+)?,\s+(?:1[6-9]\d\d|20\d\d)\b"
)


def _looks_like_bibliography(text: str) -> bool:
    """True if a chunk's body reads as a bibliographic listing — repeated
    ``SURNAME, FIRSTNAME. Title. City, Year.`` entries — rather than
    Hegel's prose. Catches sub-sections of bibliography apparatus whose
    headings ("A. General Works", "II. Recent Studies") look like normal
    chapter titles to the splitter.

    Two signals; either is enough:
    * 3+ ALL-CAPS-surname author intros (`CAIRD, EDWARD.`).
    * 2+ author intros AND 2+ City-Year publication tokens. The lower
      author threshold catches shorter lists where the disambiguator is
      the publication metadata.
    """

    author_hits = len(_BIB_AUTHOR_RE.findall(text))
    if author_hits >= 3:
        return True
    return author_hits >= 2 and len(_BIB_CITY_YEAR_RE.findall(text)) >= 2
