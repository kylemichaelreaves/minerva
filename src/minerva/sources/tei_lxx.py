"""Parser for First1KGreek biblical TEI P5 files (Septuagint).

Shape differs from the Aristotle First1KGreek bundles handled by
``tei_p5.py``: the LXX uses ``<div type="textpart" subtype="chapter">``
→ ``subtype="verse">`` nesting (chapter/verse, not book/chapter), and
the "book" of each citation is the whole file. So this parser emits
one Chunk per verse (its ``<p>``/``<l>``/``<lg>`` content joined), with:

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

import re
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

# Most of Swete's apparatus is wrapped in <note> (skipped below), but a
# residue of manuscript sigla leaked into the running text during the
# First1KGreek encoding: standalone Latin-codepoint capitals (codex
# letters — A, B*, D, F…) and the § supplied-text mark, floating between
# Greek words. A standalone Latin capital or § is never genuine LXX
# text, so strip whitespace-delimited runs of them. (Greek capitals are
# distinct codepoints — Α U+0391 ≠ A U+0041 — so real text is safe.)
_STRAY_SIGLA_RE = re.compile(r"(?:(?<=\s)|^)(?:(?:[A-Z]\*?|§)(?:\s+|$))+")


# Swete's critical apparatus is encoded as inline <note> elements:
# type="marginal" carries manuscript sigla (single capitals like "A",
# "B*", "§"), type="footnote" the variant readings. Neither is verse
# text — skip the whole subtree. (One file has the typo "margnal";
# skipping by tag, not type, covers it.)
_NOTE_TAG = f"{{{_NS['tei']}}}note"


def _text_of(elem: ET.Element) -> str:
    """All character content under `elem` with collapsed whitespace,
    excluding ``<note>`` apparatus subtrees. ``<lb/>``, ``<hi>``, etc.
    still contribute their text/tails."""
    return _norm_text(text_excluding(elem, frozenset({_NOTE_TAG})))


# Verse text lives in <p> for prose books, but the poetic books
# (Job, Proverbs, Wisdom, Song of Songs, Lamentations — plus inset
# poetry like Gen 49 or Exod 15) put it in <l> lines (occasionally
# grouped in <lg>) that are *siblings* of any <p>. Collect all three
# in document order; direct-child <note>/<pb>/<lb> stay excluded.
_CONTENT_TAGS = frozenset(f"{{{_NS['tei']}}}{t}" for t in ("p", "l", "lg"))


def _resolve_cv(
    breadcrumb: tuple[tuple[str | None, str | None], ...],
) -> tuple[str, str] | None:
    """(chapter, verse) from a breadcrumb, or None if it has no verse.
    Single-chapter books (Letter of Jeremiah) have no chapter level in
    the TEI at all — default their chapter to "1" so ``"EpJer 1:72"``
    style sections still form."""

    chapter: str | None = None
    verse: str | None = None
    for s, v in breadcrumb:
        if s == "chapter":
            chapter = v
        elif s == "verse":
            verse = v
    if verse is None:
        return None
    return (chapter if chapter is not None else "1", verse)


def _iter_verses(
    elem: ET.Element,
    breadcrumb: tuple[tuple[str | None, str | None], ...] = (),
) -> Iterator[tuple[str, str, list[ET.Element]]]:
    """Walk the textpart tree; yield ``(chapter, verse, content)``
    for every textpart that carries a verse in its breadcrumb.
    Leaves without one are skipped silently — headers, prefatory
    material, the rare ungrouped paragraph.
    """

    for child in elem.findall("tei:div", _NS):
        if child.get("type") != "textpart":
            continue
        sub = child.get("subtype")
        n = child.get("n")
        new_crumb = (*breadcrumb, (sub, n))
        has_inner = any(d.get("type") == "textpart" for d in child.findall("tei:div", _NS))
        content = [c for c in child if c.tag in _CONTENT_TAGS]
        cv = _resolve_cv(new_crumb)
        if has_inner:
            # A mis-nested wrapper (Psalms has one verse div enclosing
            # the next five) still owns its own text — yield it before
            # descending, or that verse's content vanishes.
            if content and cv is not None:
                yield (*cv, content)
            yield from _iter_verses(child, new_crumb)
            continue
        if cv is None or not content:
            continue
        yield (*cv, content)


def parse_file(
    path: Path,
    *,
    book_title: str,
    book_abbr: str,
    work_code: str,
) -> Iterator[Chunk]:
    """Parse one Septuagint book TEI P5 file into Chunks."""

    tree = _parse_xml(path)
    root = tree.getroot()
    edition = root.find("tei:text/tei:body/tei:div", _NS)
    if edition is None:
        print(
            f"tei_lxx: {path.name!r}: no edition root at text/body/div — skipping file",
            file=sys.stderr,
        )
        return

    editor_el = root.find("tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:editor", _NS)
    editor_name = editor_el.text.strip() if editor_el is not None and editor_el.text else None
    date_el = root.find("tei:teiHeader/tei:fileDesc/tei:sourceDesc//tei:date", _NS)
    year = date_el.text.strip() if date_el is not None and date_el.text else None

    for chapter, verse, content in _iter_verses(edition):
        # A verse may span several content elements — multiple <p>
        # (typographic breaks), or an acrostic-letter <p> heading
        # followed by <l> poetry lines. Concatenate them so the chunk
        # is one full verse; the chunk_id stays stable across
        # re-ingests because it's content-derived.
        text = _norm_text(" ".join(_text_of(p) for p in content))
        text = _norm_text(_STRAY_SIGLA_RE.sub("", text))
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

    from minerva.authors.septuagint_works import book_for_filename
    from minerva.locations import BCV_BOOK_ABBR

    for entry in sorted(directory.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".xml"):
            continue
        book = book_for_filename(entry.name)
        if book is None:
            print(f"lxx: skipping unknown file {entry.name!r}")
            continue
        abbr = BCV_BOOK_ABBR.get(book.title)
        if abbr is None:
            print(f"lxx: book {book.title!r} not in BCV_BOOK_ABBR; add it to locations._BCV_BOOKS")
            continue
        yield from guarded_parse_file(
            "lxx",
            entry,
            lambda e=entry, b=book, a=abbr: parse_file(
                e, book_title=b.title, book_abbr=a, work_code=b.code
            ),
        )
