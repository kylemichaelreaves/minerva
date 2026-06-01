"""Parser for the Clementine Vulgate plain-text files.

Each .lat file is one book; each non-blank line is exactly one verse
in the shape ``<chap>:<verse> <text>``. The shape is a simple regex
match — no XML, no markup state machine — but a few VulSearch-era
typographic conventions warrant a small normalization pass:

* **Trailing ``\\``** at end of line: leftover delimiter character
  from VulSearch's original distribution. Strip.
* **``[...]`` poetry brackets** (Psalms, Proverbs, Wisdom, Sirach,
  some prophets): wrap poetic stanzas. The text inside them is
  the verse content; the brackets are typographic only. Strip the
  brackets but keep the content.
* **``/`` soft line-break markers** inside poetry: render the
  scribal line breaks in metrical psalms / lamentations. Replace
  with a single space for retrieval purposes.
* **``<...>`` inline superscriptions** (Bar 6 has one): rare
  editorial annotation. Strip the wrapping markers but keep the
  text — losing the text would orphan some verses.

The Vulgate's Septuagint-derived Psalm numbering, Susanna and Bel
as Daniel 13–14, and the Letter of Jeremiah as Baruch 6 are all
preserved by source — no special handling.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from .tei import Chunk, _make_chunk_id, _norm_text

_VERSE_LINE_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s+(.*?)\s*$")
_TRAILING_BACKSLASH_RE = re.compile(r"\\$")
_POETRY_BRACKET_RE = re.compile(r"[\[\]]")
_SUPERSCRIPTION_RE = re.compile(r"[<>]")
_SOFT_BREAK_RE = re.compile(r"\s*/\s*")


def _clean_verse_text(raw: str) -> str:
    text = _TRAILING_BACKSLASH_RE.sub("", raw)
    text = _POETRY_BRACKET_RE.sub("", text)
    text = _SUPERSCRIPTION_RE.sub("", text)
    text = _SOFT_BREAK_RE.sub(" ", text)
    return _norm_text(text)


def parse_file(
    path: Path,
    *,
    book_title: str,
    book_abbr: str,
    work_code: str,
) -> Iterator[Chunk]:
    """Yield one Chunk per verse line in a Clementine Vulgate book file."""

    with path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n\r")
            if not line.strip():
                continue
            m = _VERSE_LINE_RE.match(line)
            if m is None:
                # Some files have stray editorial lines (rare; mostly
                # comments at top of Bar.lat etc.). Skip silently —
                # the regex is strict on purpose so a real verse can't
                # slip past.
                continue
            chap = int(m.group(1))
            verse = int(m.group(2))
            text = _clean_verse_text(m.group(3))
            if not text:
                continue
            section = f"{book_abbr} {chap}:{verse}"
            chunk_id = _make_chunk_id(
                path.name,
                work_code,
                "lat",
                book_title,
                section,
                "",
                text[:120],
            )
            yield Chunk(
                chunk_id=chunk_id,
                corpus="vulgate",
                author="Vulgate",
                work=book_title,
                lang="lat",
                section=section,
                book=book_title,
                page=None,
                speaker=None,
                text=text,
                source_file=path.name,
                translator="(Original)",  # Jerome's Vulgate is the original
                edition_year="1592",  # Clementine recension
                citation_system="bcv",
            )


def parse_dir(directory: Path) -> Iterator[Chunk]:
    """Walk ``data/vulgate/raw_lat/`` and yield Chunks for every
    recognised Clementine Vulgate book file. Files whose stem isn't
    in ``vulgate_works._BOOKS`` are skipped with a warning."""

    from .authors.vulgate_works import book_for_filename
    from .locations import BCV_BOOK_ABBR

    for entry in sorted(directory.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".lat"):
            continue
        book = book_for_filename(entry.name)
        if book is None:
            print(f"vulgate: skipping unknown file {entry.name!r}")
            continue
        abbr = BCV_BOOK_ABBR.get(book.title)
        if abbr is None:
            print(
                f"vulgate: book {book.title!r} not in BCV_BOOK_ABBR; "
                f"add it to locations._BCV_BOOKS"
            )
            continue
        yield from parse_file(
            entry,
            book_title=book.title,
            book_abbr=abbr,
            work_code=book.code,
        )
