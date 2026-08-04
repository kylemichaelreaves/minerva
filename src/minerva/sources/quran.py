"""Parser for the Tanzil Uthmani Quran XML.

Source format: ``<quran><sura index="N" name="…"><aya index="M"
text="…" /></sura></quran>`` — flat, one root, attributes only.
No nested verse markup, no morphology tags. Simple to parse.

This parser yields one ``Chunk`` per ayah with:

* ``corpus`` = ``"quran"``.
* ``author`` = ``"Quran"`` (the corpus is keyed as a single
  "author" so the Reader sidebar lists 114 surahs under one
  header — same shape as Hebrew Bible / Septuagint / Vulgate).
* ``work``   = the surah's transliterated title (``Al-Fatihah``,
  ``Al-Baqarah``, …), used as the URL-safe id. The Arabic-script
  name is surfaced as ``display_title`` in the Reader API.
* ``book``   = same as ``work`` so the sidebar carries the
  transliterated name in the same field other corpora use for the
  book label.
* ``section`` = ``"<surah>:<ayah>"`` (e.g. ``"2:255"``). Matches
  the ``surah_ayah`` parse_section regex; same compact shape used
  in popular Quran citations.
* ``citation_system`` = ``"surah_ayah"`` (admitted to the works
  CHECK by migration 0017).
* ``text`` = the ayah text NFC-normalised, tashkeel preserved
  verbatim from the source.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from pathlib import Path

from minerva.tei import Chunk, _make_chunk_id, _norm_text

from ..xml_safe import parse as _parse_xml


def _normalize_ayah_text(s: str) -> str:
    """NFC-normalise and collapse interior whitespace. Tashkeel
    (vowel marks like fatha, kasra, damma) and any small recitation
    marks Tanzil ships are preserved verbatim."""

    return _norm_text(unicodedata.normalize("NFC", s))


def parse_file(path: Path) -> Iterator[Chunk]:
    """Parse the Tanzil Uthmani XML into Chunks (one per ayah).

    The XML is a single file containing all 114 surahs — different
    from the per-book layout the Hebrew Bible OSHB uses. Iterate
    surahs in document order (which is canonical Mushaf order) and
    emit one Chunk per ``<aya>``.
    """

    from minerva.authors.quran_works import find_surah

    tree = _parse_xml(path)
    root = tree.getroot()  # <quran>

    for sura_el in root.findall("sura"):
        try:
            sura_n = int(sura_el.get("index", "0"))
        except ValueError:
            continue
        surah = find_surah(sura_n)
        if surah is None:
            # An unknown surah number shouldn't happen with Tanzil's
            # canonical 114-surah file, but skip-with-note keeps the
            # parser robust to malformed input.
            continue

        work_title = surah.transliteration  # canonical URL-safe id
        for aya_el in sura_el.findall("aya"):
            try:
                aya_n = int(aya_el.get("index", "0"))
            except ValueError:
                continue
            text = _normalize_ayah_text(aya_el.get("text", ""))
            if not text:
                continue
            section = f"{sura_n}:{aya_n}"
            chunk_id = _make_chunk_id(
                path.name,
                work_title,
                "ara",
                work_title,
                section,
                "",
                text[:120],
            )
            yield Chunk(
                chunk_id=chunk_id,
                corpus="quran",
                author="Quran",
                work=work_title,
                lang="ara",
                section=section,
                book=work_title,
                page=None,
                speaker=None,
                text=text,
                source_file=path.name,
                # Editor / source attribution — Tanzil is the
                # distribution; the underlying text is the standard
                # 1924 Egyptian (al-Madinah) Uthmani edition.
                translator="Tanzil / 1924 Egyptian Uthmani",
                edition_year="1924",
                citation_system="surah_ayah",
            )


def parse_dir(directory: Path) -> Iterator[Chunk]:
    """Walk ``data/quran/raw/`` and yield Chunks from every
    Tanzil Uthmani XML file present. Typically only one file
    (``quran-uthmani.xml``) — but tolerates more (e.g. if you
    later drop in an alternative recitation/qiraat variant)."""

    for entry in sorted(directory.iterdir()):
        if not entry.is_file() or entry.suffix != ".xml":
            continue
        yield from parse_file(entry)
