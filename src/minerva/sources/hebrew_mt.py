"""Parser for OSHB (Open Scriptures Hebrew Bible) OSIS XML.

Source format: ``<verse osisID="Gen.1.1"> <w lemma="…" morph="…">word</w>
… <seg type="x-sof-pasuq">׃</seg> </verse>`` — one ``<verse>`` per
biblical verse, words wrapped in ``<w>`` with morphology metadata, and
end-of-verse punctuation as a ``<seg>``.

This parser yields one ``Chunk`` per verse with:

* ``book``  = canonical English name from
  ``hebrew_mt_works._BOOKS`` (e.g. ``"Genesis"``), so cross-corpus
  alignment with LXX/Vulgate uses the same key.
* ``section`` = ``"<SBL-abbr> <chap>:<verse>"`` from
  ``locations.BCV_BOOK_ABBR`` (e.g. ``"Gen 1:1"``) — same shape as
  the Septuagint and Vulgate ingest emit.
* ``citation_system`` = ``"bcv"``.
* ``text`` = concatenation of the verse's ``<w>`` content with the
  OSIS morpheme separator (``/``) stripped and Unicode normalised
  to NFC. Cantillation marks (te'amim) and niqqud (vowel pointing)
  are preserved verbatim from the source.

Morphology / Strong's lemma data is dropped at this layer — the
chunk text is the surface form. A future Hebrew lemmatization pass
(plan Phase G) can re-mine the OSIS XML directly via the
``<w lemma=…>`` attribute when it lands.
"""

from __future__ import annotations

import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

from minerva.tei import (
    Chunk,
    _make_chunk_id,
    _norm_text,
    guarded_parse_file,
    text_excluding,
)

# OSIS XML uses a default namespace; ElementTree exposes it as a
# Clark-notation prefix on every tag. Bind it so XPath queries stay
# readable.
_NS = {"osis": "http://www.bibletechnologies.net/2003/OSIS/namespace"}

# OSHB encodes a morpheme break inside an orthographic word with a
# literal "/" — e.g., ``בְּ/רֵאשִׁית`` ("be-" + "reshit") renders
# orthographically as ``בְּרֵאשִׁית``. The slash is an analytical
# marker, not part of the text the reader sees; strip it.
_MORPHEME_SEP = "/"


def _normalize_verse_text(s: str) -> str:
    """Strip morpheme slashes and NFC-normalise.

    NFC composes the cantillation marks and niqqud so equal-looking
    strings compare equal at the bytes level — important for the
    chunk_id hash, FTS5 matching, and cross-edition comparison.
    """

    return unicodedata.normalize("NFC", s.replace(_MORPHEME_SEP, ""))


# WLC/OSHB transcription apparatus: <note> carries English editorial
# prose ("We read one or more accents in L differently than BHS…") and
# nests the variant machinery (<rdg>, <catchWord>). None of it is verse
# text; skipping the <note> subtree drops all of it.
_NOTE_TAG = f"{{{_NS['osis']}}}note"


def _verse_text(verse: ET.Element) -> str:
    """Concatenate the textual content of a ``<verse>`` element.

    Walks every descendant text/tail node in document order — except
    ``<note>`` subtrees (transcription apparatus) — giving the surface
    form (``<w>`` bodies + ``<seg>`` content like the sof-pasuq mark).
    Whitespace is collapsed and the morpheme separator is stripped
    after the concatenation so it doesn't leak into the chunk.
    """

    raw = text_excluding(verse, frozenset({_NOTE_TAG}))
    return _norm_text(_normalize_verse_text(raw))


def _parse_osis_id(osis_id: str) -> tuple[str, str, str] | None:
    """Split ``"Gen.1.1"`` into ``("Gen", "1", "1")``. Returns
    ``None`` for malformed ids (whole-book or whole-chapter
    references the OSIS schema allows but our parser doesn't index).
    """

    parts = osis_id.split(".")
    if len(parts) != 3:
        return None
    book_id, chapter, verse = parts
    if not (book_id and chapter and verse):
        return None
    return book_id, chapter, verse


def parse_file(path: Path) -> Iterator[Chunk]:
    """Parse one OSHB OSIS XML file into Chunks (one per verse).

    The book metadata (canonical English name, SBL abbreviation) is
    resolved from the filename via ``hebrew_mt_works.find_book`` and
    cross-checked against the ``osisID`` prefix on the first verse.
    Files registered in ``hebrew_mt_works`` are processed; everything
    else (e.g. VerseMap.xml) is silently skipped.
    """

    from minerva.authors.hebrew_mt_works import find_book
    from minerva.locations import BCV_BOOK_ABBR

    book = find_book(path.name)
    if book is None:
        return

    book_title = book.english
    sbl_abbr = BCV_BOOK_ABBR.get(book_title)
    if sbl_abbr is None:
        # Print-and-skip, matching the sibling scripture parsers
        # (tei_lxx, osis_bible) which treat a missing BCV entry as a
        # soft skip rather than raising. A raise here would abort the
        # whole book (issue #46).
        print(
            f"hebrew_mt: book {book_title!r} from {path.name} not in "
            f"BCV_BOOK_ABBR; add it to locations._BCV_BOOKS"
        )
        return

    tree = ET.parse(path)
    root = tree.getroot()

    work_code = book_title.lower().replace(" ", "_")

    for verse_el in root.iter(f"{{{_NS['osis']}}}verse"):
        osis_id = verse_el.get("osisID")
        if not osis_id:
            continue
        parsed = _parse_osis_id(osis_id)
        if parsed is None:
            continue
        verse_book_id, chapter, verse = parsed
        if verse_book_id != book.osis_id:
            # Cross-book reference inside a verse element — shouldn't
            # happen in OSHB's per-book files but guard so we don't
            # silently mis-attribute chunks.
            continue
        text = _verse_text(verse_el)
        if not text:
            continue
        section = f"{sbl_abbr} {chapter}:{verse}"
        chunk_id = _make_chunk_id(
            path.name,
            work_code,
            "heb",
            book_title,
            section,
            "",
            text[:120],
        )
        yield Chunk(
            chunk_id=chunk_id,
            corpus="hebrew_mt",
            author="Hebrew Bible",
            work=book_title,
            lang="heb",
            section=section,
            book=book_title,
            page=None,
            speaker=None,
            text=text,
            source_file=path.name,
            # Editor of the underlying critical edition: Christopher
            # V. Kimball stamps each OSHB file as the WLC encoder.
            # Hardcoded here to avoid parsing the OSIS header
            # twice — pre-resolved at the file level.
            translator="WLC / OSHB",
            edition_year="2018",  # OSHB 4.20 release date
            citation_system="bcv",
        )


def parse_dir(directory: Path) -> Iterator[Chunk]:
    """Walk ``data/hebrew_mt/raw/`` and yield Chunks for every
    recognised OSHB book file. Files not registered in
    ``hebrew_mt_works._BOOKS`` (e.g. VerseMap.xml metadata) are
    skipped silently."""

    from minerva.authors.hebrew_mt_works import find_book

    for entry in sorted(directory.iterdir()):
        if not entry.is_file() or entry.suffix != ".xml":
            continue
        if find_book(entry.name) is None:
            continue
        yield from guarded_parse_file(
            "hebrew_mt", entry, lambda e=entry: parse_file(e)
        )
