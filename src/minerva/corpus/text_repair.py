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


# Scraped page furniture that reached the corpus as text. Both were found
# after the fact, in chunks that had already been embedded and lemmatized:
# the Internet Archive's crawl-provenance block (#383, 33 chunks in *Die
# deutsche Ideologie*, sitting mid-text where the scrape spliced it) and
# mlwerke.de's MEW edition note (#298, 18 chunks). Neither is cosmetic —
# editorial text in a chunk is what produces spurious cross-references, and
# a 100-plus-character bibliographic note clears every length floor in the
# retrieval path.
#
# Matched as a *prefix* of the paragraph rather than as a substring: Marx's
# editors write about archives, and the crawl block's lines are the whole
# paragraph wherever they appear.
_CRAWL_CHROME_PREFIXES = (
    "organization: internet archive",
    "collection: wide crawl",
    "- slash pages from every domain",
    "-- a list of domains using",
    "- top ranked pages",
    "-- a ranking of all urls",
    "-- up to a maximum of",
)

# `Seitenzahlen verweisen auf: Karl Marx - Friedrich Engels - Werke, Band 25,
# …, S. 627 - 652 Dietz Verlag, Berlin/DDR 1983`. Runs to the end of the
# paragraph in all 18 chunks carrying it (longest tail 162 chars), so this
# cuts the note without cutting prose. Seventeen are nothing but the note and
# so vanish; the eighteenth keeps its title line.
_EDITION_NOTE_RE = re.compile(r"\s*Seitenzahlen verweisen auf:.*\Z", re.S)


def strip_source_chrome(text: str) -> str:
    """Remove scraped site/crawl furniture. Empty result means drop the chunk.

    Callers must apply this **after** assigning paragraph indices. Dropping a
    paragraph earlier renumbers every one after it, and `section` feeds
    `_make_chunk_id` — the crawl block sits mid-work, so an early filter
    would churn *Die deutsche Ideologie* entire rather than 33 chunks.
    """

    if any(text.lstrip().lower().startswith(p) for p in _CRAWL_CHROME_PREFIXES):
        return ""
    return _EDITION_NOTE_RE.sub("", text).strip()
