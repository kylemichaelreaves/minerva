"""Parser for OpenGreekAndLatin First1KGreek TEI P5 files.

These files differ from Perseus's older TEI.2 bundles in three ways:

1. Namespaced — the TEI namespace lives at
   ``http://www.tei-c.org/ns/1.0``. The existing ``tei.py`` parser is
   written against non-namespaced TEI.2 and can't handle these.
2. Polytonic Unicode Greek, not Perseus beta-code. No transliterator
   needed downstream.
3. Body structure: a top-level ``<div type="edition">`` contains a
   recursive tree of ``<div type="textpart" subtype="book|chapter">``.
   Leaf textparts hold ``<p>`` paragraphs (and sometimes ``<head>``
   headings). Some works are chapter-only (Categories: 15 chapters);
   some are book+chapter (Physics: 8 books × N chapters); some are
   book-only with no chapter subdivision (On the Soul).

The parser walks the textpart tree recursively, accumulates a
breadcrumb of (subtype, n) at each level, and emits one Chunk per
``<p>`` it reaches. The breadcrumb collapses into the chunk's
``book`` and ``section`` columns:

* Two-level work (book → chapter): ``book='1'``, ``section='1.3'``
* One-level work (chapter only):   ``book=None``, ``section='5'``
* One-level work (book only):       ``book='2'``, ``section=None``
  (chunks here would have no fine-grained section locator; we fall
  back to a ``¶N`` paragraph counter within the book)

True Bekker pagination is not reliably extractable from these files —
the ``<pb n="N">`` markers carry source-edition page numbers, which
sometimes happen to be Bekker pages (On the Soul starts at 158, close
to 402a's source page) and sometimes don't (Physics counts pages from
1, not 184a). Recovering Bekker would require cross-referencing each
file with a Bekker-numbered edition; out of scope here.
"""

from __future__ import annotations

import sys
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

from ..xml_safe import parse as _parse_xml

_NS = {"tei": "http://www.tei-c.org/ns/1.0"}

_NOTE_TAG = f"{{{_NS['tei']}}}note"


def _text_of(elem: ET.Element) -> str:
    """All character content under ``elem``, excluding ``<note>``
    apparatus subtrees. Milestones, ``<hi>`` spans, etc. still
    contribute their text/tails."""
    return _norm_text(text_excluding(elem, frozenset({_NOTE_TAG})))


def _leaf_paragraphs(textpart: ET.Element) -> list[ET.Element]:
    """Return the chunk-worthy child elements of `textpart`.

    Three shapes are handled:

    * ``<p>`` prose paragraphs — one chunk per paragraph (Aristotle /
      Origen prose).
    * ``<l>`` verse lines (Phaedrus / Babrius / any TEI P5 verse) —
      a single chunk for the whole leaf textpart, since one chunk per
      line is too granular for a citation-style retrieval system.
      Returning ``[textpart]`` makes ``_text_of`` aggregate every
      ``<l>`` inside the fable into one paragraph.
    * Nested textparts (the recursive case) — return ``[]`` and let
      ``_walk_textparts`` descend.
    """

    has_inner = any(d.get("type") == "textpart" for d in textpart.findall("tei:div", _NS))
    if has_inner:
        return []
    paras = textpart.findall("tei:p", _NS)
    if paras:
        return paras
    if textpart.findall("tei:l", _NS):
        # Verse leaf — collapse all <l> lines into one virtual paragraph
        # by yielding the textpart itself; _text_of will itertext() the
        # whole subtree.
        return [textpart]
    return []


def _walk_textparts(
    elem: ET.Element,
    breadcrumb: list[tuple[str | None, str | None]],
) -> Iterator[tuple[list[tuple[str | None, str | None]], list[ET.Element]]]:
    """Recurse the textpart tree; for each leaf, yield
    ``(breadcrumb, paragraphs)``."""

    paras = _leaf_paragraphs(elem)
    if paras:
        yield breadcrumb, paras
        return
    for child in elem.findall("tei:div", _NS):
        if child.get("type") != "textpart":
            continue
        sub = child.get("subtype")
        n = child.get("n")
        yield from _walk_textparts(child, [*breadcrumb, (sub, n)])


def _format_locator(
    breadcrumb: list[tuple[str | None, str | None]],
    paragraph_idx: int,
) -> tuple[str | None, str]:
    """Collapse a textpart breadcrumb + paragraph index into
    ``(book, section)`` strings. The `breadcrumb` order is outermost
    → innermost, e.g. ``[('book', '1'), ('chapter', '3')]``.

    Section strings:
    * ``'1.3.¶5'`` for book → chapter → paragraph
    * ``'5.¶2'`` for chapter-only works
    * ``'¶5'`` for unlabelled prose
    """

    book: str | None = None
    chapter: str | None = None
    for subtype, n in breadcrumb:
        if subtype == "book":
            book = n
        elif subtype in ("chapter", "poem", "fable", "section"):
            # ``poem`` / ``fable`` (Perseus verse-fable TEI P5 — Phaedrus)
            # and ``section`` (general TEI P5 prose-section variant) are
            # treated as the same locator level as ``chapter``. A given
            # work uses only one of these subtypes so they never collide.
            chapter = n
    parts = []
    if book is not None and chapter is not None:
        parts.append(f"{book}.{chapter}")
    elif chapter is not None:
        parts.append(chapter)
    elif book is not None:
        # Book-only nesting: book becomes the section prefix too, so
        # citations read "Book 1, ¶5" not just "¶5".
        parts.append(book)
    parts.append(f"¶{paragraph_idx}")
    return book, ".".join(parts)


_LANG_BY_SUFFIX = {
    "_grc": "grc",
    "_gr": "grc",
    "_lat": "lat",
    "_la": "lat",
    "_eng": "eng",
    "_en": "eng",
    "_deu": "deu",
    "_de": "deu",
    "_fra": "fra",
    "_fr": "fra",
}


def _lang_from_stem(stem: str) -> str | None:
    """Detect the language from a filename stem, or ``None`` when no
    marker is present.

    Matches both the trailing-suffix form used by the flat layout
    (``phaedrus_lat`` → lat) and the bare-code filename used by the
    Aristotle/First1KGreek subdir layout (``grc.xml`` → grc). Returning
    ``None`` rather than silently defaulting to ``grc`` lets the flat
    layout fail loudly on an unsuffixed file instead of mis-stamping a
    Latin/English work as Greek (issue #48)."""
    for suffix, lang in _LANG_BY_SUFFIX.items():
        # ``_grc`` matches both ``foo_grc`` (suffix) and ``grc`` (bare).
        if stem.endswith(suffix) or f"_{stem}" == suffix:
            return lang
    return None


def parse_file(
    path: Path,
    *,
    work: str,
    corpus: str = "aristotle",
    author: str = "Aristotle",
    lang: str | None = None,
) -> Iterator[Chunk]:
    """Parse one TEI P5 file into Chunks.

    Defaults to Aristotle / Greek for backward compatibility with the
    original First1KGreek-only ingest. ``corpus``, ``author``, and
    ``lang`` can all be overridden so other TEI P5 sources (Origen
    Greek, Phaedrus Latin + English) reuse the same walker.

    ``lang=None`` triggers filename-stem detection
    (``_grc/_lat/_eng/_deu/_fra``); pass it explicitly to override.
    """

    tree = _parse_xml(path)
    root = tree.getroot()
    # Two conventions in the wild:
    #
    # * Explicit edition wrapper — ``<body><div type="edition"
    #   n="urn:..."><div type="textpart" subtype="book">...``. First1KGreek
    #   and Perseus's Latin Phaedrus follow this shape.
    # * Direct body children — ``<body><div type="textpart"
    #   subtype="book" n="1">...<div type="textpart" subtype="book"
    #   n="2">...``. Perseus's English Phaedrus (P4-converted) skips
    #   the wrapper. Treat the body itself as the "edition" so the
    #   walker descends through every sibling book.
    body = root.find("tei:text/tei:body", _NS)
    if body is None:
        print(
            f"tei_p5: {path.name!r}: no text/body root element — skipping file",
            file=sys.stderr,
        )
        return
    first_div = body.find("tei:div", _NS)
    if first_div is None:
        print(
            f"tei_p5: {path.name!r}: body has no div children — skipping file",
            file=sys.stderr,
        )
        return
    edition = first_div if first_div.get("type") == "edition" else body
    if lang is None:
        lang = _lang_from_stem(path.stem)
        if lang is None:
            # No recognizable language marker. Fail loudly rather than
            # silently stamping the file Greek (issue #48). The dir
            # walker's guarded_parse_file records this and skips.
            raise ValueError(
                f"tei_p5: cannot detect language for {path.name!r} — "
                f"stem has no recognized suffix ({sorted(_LANG_BY_SUFFIX)}). "
                f"Rename the file or pass lang= explicitly."
            )

    # Translator: First1KGreek files carry an editor (often Bekker /
    # Koetschau / etc.) but not a translator — these are Greek originals.
    # The schema convention from `_resolve_work_refs` is that an empty
    # translator for an original-language chunk gets recorded as the
    # edition's `name`. Use the source edition's <editor> if present.
    editor_el = root.find("tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:editor", _NS)
    editor_name = editor_el.text.strip() if editor_el is not None and editor_el.text else None
    # Year from the source biblStruct
    date_el = root.find("tei:teiHeader/tei:fileDesc/tei:sourceDesc//tei:date", _NS)
    year = date_el.text.strip() if date_el is not None and date_el.text else None

    for breadcrumb, paragraphs in _walk_textparts(edition, []):
        for idx, p in enumerate(paragraphs, 1):
            text = _text_of(p)
            if not text:
                continue
            book, section = _format_locator(breadcrumb, idx)
            chunk_id = _make_chunk_id(
                path.name,
                work,
                lang,
                book or "",
                section,
                "",
                text[:120],
            )
            yield Chunk(
                chunk_id=chunk_id,
                corpus=corpus,
                author=author,
                work=work,
                lang=lang,
                section=section,
                book=book,
                page=None,
                speaker=None,
                text=text,
                source_file=path.name,
                translator=editor_name,  # critical-edition editor
                edition_year=year,
            )


def parse_dir(directory: Path) -> Iterator[Chunk]:
    """Walk a First1KGreek download directory layout
    (``<canonical_title>/grc.xml`` per work) and yield Chunks.

    Two layouts are supported:

    * **Aristotle layout** — ``<dir>/<canonical_title>/grc.xml`` per
      work, with the canonical title looked up in
      ``aristotle_works.works_with_first1k``. This is the original
      caller and stays the default.
    * **Flat single-work layout** — ``<dir>/<workname>_grc.xml`` at
      the top level. Used by Origen (``data/origen/contra_celsum_grc.xml``)
      and any future author with a single in-corpus First1KGreek work.
      The directory name is the corpus slug; the work title is derived
      from the file name (strip ``_grc.xml``, replace ``_`` with `` ``,
      title-case) and author defaults to the corpus slug capitalised.
      For richer per-corpus metadata, call ``parse_file`` directly
      with explicit ``corpus``/``author`` from the registry factory.
    """

    # Aristotle layout: subdirectories with grc.xml inside.
    sub_dirs = [e for e in directory.iterdir() if e.is_dir()]
    if sub_dirs:
        from minerva.authors.aristotle_works import works_with_first1k

        by_slug = {_slug_for_title(w.canonical_title): w for w in works_with_first1k()}
        for entry in sorted(sub_dirs):
            xml_file = entry / "grc.xml"
            if not xml_file.is_file():
                continue
            meta = by_slug.get(entry.name)
            if meta is None:
                print(f"first1k: skipping unknown work directory {entry.name!r}")
                continue
            yield from guarded_parse_file(
                entry.name,
                xml_file,
                lambda f=xml_file, w=meta.canonical_title: parse_file(f, work=w),
            )
        return

    # Flat single-work layout (Origen / Aesop / future). Corpus =
    # parent dir name; author = corpus title-cased. Files are
    # ``<workname>_<lang>.xml`` — the lang suffix drives both the
    # ``lang`` column and the work-title derivation (which strips the
    # suffix).
    corpus = directory.name
    author = corpus[:1].upper() + corpus[1:]
    for xml_file in sorted(directory.glob("*.xml")):
        stem = xml_file.stem
        # Strip the lang suffix (_grc, _lat, _eng, ...) for the work
        # title so per-language editions share the same `work` field.
        for suffix in _LANG_BY_SUFFIX:
            if stem.endswith(suffix):
                stem = stem.removesuffix(suffix)
                break
        work_title = stem.replace("_", " ").title()
        yield from guarded_parse_file(
            corpus,
            xml_file,
            lambda f=xml_file, w=work_title: parse_file(
                f, work=w, corpus=corpus, author=author
            ),
        )


def _slug_for_title(title: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in title).strip("_")
