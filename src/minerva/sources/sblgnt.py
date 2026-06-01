"""Parser for the SBL Greek New Testament XML edition.

SBLGNT (Mike Holmes ed., 2010) is distributed as 27 per-book XML
files in a custom format that pre-tokenises every word. The shape:

    <book id="Mt">
      <title>ΚΑΤΑ ΜΑΘΘΑΙΟΝ</title>
      <p>
        <verse-number id="Matthew 1:1">1:1</verse-number>
        <w>Βίβλος</w><suffix> </suffix>
        <w>γενέσεως</w><suffix> </suffix>
        ...
      </p>
      ...

Notable shape differences from the LXX TEI files we handled in
``tei_lxx.py``:

* No XML namespace — bare element names.
* No TEI ``<div type="textpart">`` nesting. Chapter and verse
  numbers are encoded as **milestones**: a ``<verse-number>``
  element marks the START of a new verse; everything between two
  consecutive ``verse-number`` milestones (in document order) is
  the previous verse's content. Verses can span ``<p>`` boundaries
  because paragraphs are editorial, not verse-aligned.
* Pre-tokenised — every word is wrapped in ``<w>`` and the trailing
  whitespace / punctuation lives in a sibling ``<suffix>``. We
  reassemble the verse by concatenating ``w.text + suffix.text``
  in order.
* The ``verse-number/@id`` carries the full book name followed by
  ``chap:verse`` — ``"1 Corinthians 13:4"`` — which we round-trip
  to ``section="<sbl-abbr> <chap>:<verse>"`` via the BCV book
  table (e.g. ``"1Cor 13:4"``).

License: see ``perseus/download_sblgnt_nt.py`` for the SBLGNT EULA
context.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

from minerva.tei import Chunk, _make_chunk_id, _norm_text

# Verse-number id is "<Book Name> <chap>:<verse>". Book names can
# contain spaces ("1 Corinthians", "Song of Songs") — match greedily
# up to the last "<chap>:<verse>" suffix.
_VERSE_ID_RE = re.compile(r"^(.+)\s+(\d+):(\d+)$")


def _parse_verse_id(raw: str) -> tuple[str, int, int] | None:
    m = _VERSE_ID_RE.match(raw.strip())
    if m is None:
        return None
    return m.group(1).strip(), int(m.group(2)), int(m.group(3))


def parse_file(
    path: Path,
    *,
    book_title: str,
    book_abbr: str,
    work_code: str,
) -> Iterator[Chunk]:
    """Parse one SBLGNT book file into per-verse Chunks.

    Verses are flushed lazily as we walk the document: each new
    ``<verse-number>`` we encounter emits the previous verse, so the
    chunk order matches reading order even when verses cross ``<p>``
    boundaries.
    """

    tree = ET.parse(path)
    root = tree.getroot()

    current_section: str | None = None
    current_book: str | None = None
    current_chunks: list[str] = []
    ord_counter = 0

    def _flush() -> Chunk | None:
        nonlocal current_section, current_book, current_chunks
        if current_section is None:
            current_section = None
            current_book = None
            current_chunks = []
            return None
        text = _norm_text("".join(current_chunks))
        section = current_section
        book = current_book
        current_section = None
        current_book = None
        current_chunks = []
        if not text:
            return None
        chunk_id = _make_chunk_id(
            path.name,
            work_code,
            "grc",
            book or "",
            section,
            "",
            text[:120],
        )
        return Chunk(
            chunk_id=chunk_id,
            corpus="new_testament",
            author="New Testament",
            work=book_title,
            lang="grc",
            section=section,
            book=book_title,
            page=None,
            speaker=None,
            text=text,
            source_file=path.name,
            translator="(Original)",
            edition_year="2010",  # SBLGNT 2nd ed.
            citation_system="bcv",
        )

    for elem in root.iter():
        tag = elem.tag
        if tag == "verse-number":
            # Boundary: flush whatever was accumulating for the
            # previous verse, then open a new one.
            chunk = _flush()
            if chunk is not None:
                yield chunk
                ord_counter += 1
            parsed = _parse_verse_id(elem.get("id") or "")
            if parsed is None:
                # Unknown id format — skip the milestone and let the
                # following words accumulate into the next valid
                # verse. Better than silently misattributing them.
                continue
            full_name, chap, verse = parsed
            if full_name != book_title:
                # Sanity check: every milestone in a book file should
                # name the same book. A mismatch suggests the SBLGNT
                # repo changed shape and book_title was derived
                # wrong upstream. Skip the verse so we don't write
                # cross-book chunks.
                print(
                    f"sblgnt: {path.name}: verse-number book {full_name!r} "
                    f"doesn't match expected {book_title!r}; skipping"
                )
                continue
            current_section = f"{book_abbr} {chap}:{verse}"
            current_book = book_title
        elif tag == "w":
            if current_section is not None and elem.text:
                current_chunks.append(elem.text)
        elif tag == "suffix":
            # SBL convention: an empty <suffix></suffix> means a
            # word-to-word boundary (render as a single space). A
            # non-empty suffix carries the inter-word punctuation
            # verbatim, including any trailing space — emit it as-is.
            # Em-dash suffixes like "—" or ",—" are intentionally
            # space-less (the dash glues to the next word).
            if current_section is not None:
                current_chunks.append(elem.text if elem.text else " ")

    # Flush the final verse at EOF.
    chunk = _flush()
    if chunk is not None:
        yield chunk


def parse_dir(directory: Path) -> Iterator[Chunk]:
    """Walk ``data/nt/raw_grc/`` and yield Chunks for every recognised
    SBLGNT book file. Files whose stem isn't in
    ``new_testament_works._BOOKS`` are skipped with a warning."""

    from minerva.authors.new_testament_works import book_for_filename
    from minerva.locations import BCV_BOOK_ABBR

    for entry in sorted(directory.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".xml"):
            continue
        book = book_for_filename(entry.name)
        if book is None:
            print(f"nt: skipping unknown file {entry.name!r}")
            continue
        abbr = BCV_BOOK_ABBR.get(book.title)
        if abbr is None:
            print(f"nt: book {book.title!r} not in BCV_BOOK_ABBR; add it to locations._BCV_BOOKS")
            continue
        yield from parse_file(
            entry,
            book_title=book.title,
            book_abbr=abbr,
            work_code=book.code,
        )
