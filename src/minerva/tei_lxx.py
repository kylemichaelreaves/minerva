"""Parser for First1KGreek biblical TEI P5 files (Septuagint).

Shape differs from the Aristotle First1KGreek bundles handled by
``tei_p5.py``: the LXX uses ``<div type="textpart" subtype="chapter">``
→ ``subtype="verse">`` nesting (chapter/verse, not book/chapter), and
the "book" of each citation is the whole file. So this parser emits
one Chunk per ``<p>`` inside each verse, with:

* ``book`` = canonical English book name from
  ``septuagint_works._BOOKS`` (e.g. ``"Genesis"``)
* ``section`` = ``"<SBL-abbr> <chap>:<verse>"`` from
  ``locations.BCV_BOOK_ABBR`` (e.g. ``"Gen 1:1"``)
* ``citation_system`` = ``"bcv"`` so ``store._resolve_work_refs``
  writes the right ``works.citation_system`` value the first time
  this book is materialized.

Some books carry an extra subtype level (Psalms has
``subtype="book"`` for the five books, Esther interleaves the Greek
additions as letter-named chapters A–F). The walker is depth-
agnostic — it looks for the (chapter, verse) pair in the breadcrumb
regardless of where it sits in the tree.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

from .tei import Chunk, _make_chunk_id, _norm_text

_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def _text_of(elem: ET.Element) -> str:
    """All character content under `elem` with collapsed whitespace.
    ``itertext`` handles nested ``<note>``, ``<lb/>``, ``<hi>``, etc."""
    return _norm_text(" ".join(elem.itertext()))


def _iter_verses(
    elem: ET.Element,
    breadcrumb: tuple[tuple[str | None, str | None], ...] = (),
) -> Iterator[tuple[str, str, list[ET.Element]]]:
    """Walk the textpart tree; yield ``(chapter, verse, paragraphs)``
    for every leaf textpart that carries both a chapter and verse in
    its breadcrumb. Leaves without that pair are skipped silently —
    headers, prefatory material, the rare ungrouped paragraph.
    """

    for child in elem.findall("tei:div", _NS):
        if child.get("type") != "textpart":
            continue
        sub = child.get("subtype")
        n = child.get("n")
        new_crumb = (*breadcrumb, (sub, n))
        has_inner = any(
            d.get("type") == "textpart" for d in child.findall("tei:div", _NS)
        )
        if has_inner:
            yield from _iter_verses(child, new_crumb)
            continue
        chapter: str | None = None
        verse: str | None = None
        for s, v in new_crumb:
            if s == "chapter":
                chapter = v
            elif s == "verse":
                verse = v
        if chapter is None or verse is None:
            continue
        paras = child.findall("tei:p", _NS)
        if not paras:
            continue
        yield chapter, verse, paras


def parse_file(
    path: Path,
    *,
    book_title: str,
    book_abbr: str,
    work_code: str,
) -> Iterator[Chunk]:
    """Parse one Septuagint book TEI P5 file into Chunks."""

    tree = ET.parse(path)
    root = tree.getroot()
    edition = root.find("tei:text/tei:body/tei:div", _NS)
    if edition is None:
        return

    editor_el = root.find(
        "tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:editor", _NS
    )
    editor_name = (
        editor_el.text.strip() if editor_el is not None and editor_el.text else None
    )
    date_el = root.find(
        "tei:teiHeader/tei:fileDesc/tei:sourceDesc//tei:date", _NS
    )
    year = (
        date_el.text.strip() if date_el is not None and date_el.text else None
    )

    for chapter, verse, paragraphs in _iter_verses(edition):
        # Multiple <p> per verse is rare but happens (Swete sometimes
        # breaks a verse on a typographic boundary). Concatenate them
        # so the chunk is one full verse; the chunk_id stays stable
        # across re-ingests because it's content-derived.
        text = _norm_text(" ".join(_text_of(p) for p in paragraphs))
        if not text:
            continue
        section = f"{book_abbr} {chapter}:{verse}"
        chunk_id = _make_chunk_id(
            path.name,
            work_code,
            "grc",
            book_title,
            section,
            "",
            text[:120],
        )
        yield Chunk(
            chunk_id=chunk_id,
            corpus="septuagint",
            author="Septuagint",
            work=book_title,
            lang="grc",
            section=section,
            book=book_title,
            page=None,
            speaker=None,
            text=text,
            source_file=path.name,
            translator=editor_name,  # critical-edition editor (Swete)
            edition_year=year,
            citation_system="bcv",
        )


def parse_dir(directory: Path) -> Iterator[Chunk]:
    """Walk ``raw_xml_lxx/`` and yield Chunks for every recognised
    Septuagint book file. Files not registered in
    ``septuagint_works._BOOKS`` are skipped with a warning."""

    from .authors.septuagint_works import book_for_filename
    from .locations import BCV_BOOK_ABBR

    for entry in sorted(directory.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".xml"):
            continue
        book = book_for_filename(entry.name)
        if book is None:
            print(f"lxx: skipping unknown file {entry.name!r}")
            continue
        abbr = BCV_BOOK_ABBR.get(book.title)
        if abbr is None:
            print(
                f"lxx: book {book.title!r} not in BCV_BOOK_ABBR; "
                f"add it to locations._BCV_BOOKS"
            )
            continue
        yield from parse_file(
            entry,
            book_title=book.title,
            book_abbr=abbr,
            work_code=book.code,
        )
