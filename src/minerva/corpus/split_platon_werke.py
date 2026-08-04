"""Structure-aware splitter for "Platon: die Werke" — the complete German
Plato (Schleiermacher, with Susemihl/Georgii for some dialogues), a single
~1,388-page PDF arranged by Thrasyllus's tetralogies.

One PDF holds every dialogue + the Letters, so this is a *multi-work*
splitter (like split_ekgwb): it walks pages, detects each work by its
heading, and — within a work — reconstructs the Stephanus locator from the
edition's inline index markers, emitting one chunk per Stephanus section.

Locator markers in the German body:
  ``[2 St.1 A]``  → Stephanus page 2 (Stephanus vol 1), section a
  ``[B]``/``[C]``/``[D]``/``[E]`` → section b/c/d/e on the current page
The reconstructed ``section`` ("2a", "327b", …) matches the Greek and
English editions verbatim, so the three align chunk-to-chunk (#50).

Work titles are canonicalized to Latinized Greek via ``plato_titles`` so
each German chunk attaches as a ``deu`` translation on the same works row
as the Greek original and the English translation.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..authors import plato_titles
from ..corpus_extract import IngestDepsMissing
from ..corpus_works import CorpusWork
from ..tei import Chunk, _make_chunk_id, _norm_text

# German ordinal → canonical Letter (Epistole roman numeral).
_ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII")
_BRIEF_ORDINALS = {
    "ERSTER": 1, "ZWEITER": 2, "DRITTER": 3, "VIERTER": 4, "FÜNFTER": 5,
    "SECHSTER": 6, "SIEBENTER": 7, "ACHTER": 8, "NEUNTER": 9, "ZEHNTER": 10,
    "ELFTER": 11, "ZWÖLFTER": 12, "DREIZEHNTER": 13,
}

# Per-canonical translator + edition year. Most of the edition is
# Schleiermacher (Platons Werke, 2. Aufl. Berlin 1818); a handful of
# dialogues were supplied by Susemihl / Georgii (see the PDF's
# per-dialogue "Nach der Übersetzung von …" attributions).
_SUSEMIHL = ("Franz Susemihl", "1863")
_GEORGII = ("Ludwig Georgii", "1853")
_SCHLEIERMACHER = ("Friedrich Schleiermacher", "1818")
_TRANSLATOR: dict[str, tuple[str, str]] = {
    "Parmenides": _SUSEMIHL, "Symposion": _SUSEMIHL, "Timaios": _SUSEMIHL,
    "Kritias": _SUSEMIHL, "Nomoi": _SUSEMIHL, "Epinomis": _SUSEMIHL,
    "Phaidros": _GEORGII,
}

# A candidate work-heading line: an UPPERCASE Greek/Latin/German name near
# the top of a page. We only treat it as a boundary if it resolves to a
# known Plato work (canonical_for) / a Brief ordinal / ALKIBIADES.
_HEAD_RE = re.compile(r"^\s*([A-ZÄÖÜ][A-ZÄÖÜ .\-']{2,45})\.?\s*$", re.M)
_BRIEF_RE = re.compile(r"^\s*([A-ZÄÖÜ]+)\s+BRIEF\s*$", re.M)

# Stephanus marker: optional "N St.V" page reset, then the section letter.
# `\s*` spans newlines, so markers split across line breaks still match.
_MARK_RE = re.compile(r"\[\s*(?:(\d+)\s*St\.\s*\d+\s*)?([A-E])\*?\s*\]")
# A page-number / running-chrome line to drop from body text.
_CHROME_RE = re.compile(r"^\s*\d{1,4}\s*$")

# German ordinal → book number, for the two multi-book works. Only the
# Politeia (10) and the Nomoi (12) are divided into books; every other
# dialogue is a single unit and correctly carries no `book` at all —
# which is what the Greek and English sides store for them too.
_BUCH_ORDINALS = {
    "ERSTES": 1, "ZWEITES": 2, "DRITTES": 3, "VIERTES": 4, "FÜNFTES": 5,
    "SECHSTES": 6, "SIEBENTES": 7, "SIEBTES": 7, "ACHTES": 8, "NEUNTES": 9,
    "ZEHNTES": 10, "ELFTES": 11, "ZWÖLFTES": 12,
}

# A body book heading — "Erstes Buch vom Staate." / "ERSTES BUCH ÜBER DIE
# GESETZE". The trailing qualifier (group 2) is REQUIRED, and that is the
# whole point of the pattern: each work's title page carries a
# clickable table of contents listing every book as a bare "Erstes Buch"
# … "Zehntes Buch", and that page falls inside the work's own span. A
# pattern without the qualifier matches all ten TOC lines before the
# first Stephanus marker, and every section of the Politeia comes out
# stamped book 10.
_BUCH_RE = re.compile(
    r"^[ \t]*((?:" + "|".join(_BUCH_ORDINALS) + r")[ \t]+BUCH)[ \t]+(\S[^\n]*)$",
    re.M | re.I,
)


def _resolve_heading(page_text: str, seen_alkibiades: int) -> str | None:
    """Return the canonical work a page starts, or None if it's not a work
    boundary. Handles the two ALKIBIADES headings (I then II) and the
    German ``… BRIEF`` ordinals."""
    for m in _HEAD_RE.finditer(page_text[:400]):
        line = " ".join(m.group(1).upper().rstrip(".").split())
        if line == "ALKIBIADES":
            return "Alkibiades II" if seen_alkibiades else "Alkibiades I"
        bm = _BRIEF_RE.match(m.group(0))
        if bm and bm.group(1) in _BRIEF_ORDINALS:
            return f"Epistole {_ROMAN[_BRIEF_ORDINALS[bm.group(1)] - 1]}"
        canon = plato_titles.canonical_for(line)
        if canon is not None:
            return canon
    return None


def _clean_body(text: str) -> str:
    """Drop bare page-number / chrome lines; keep the German prose."""
    return "\n".join(ln for ln in text.splitlines() if not _CHROME_RE.match(ln))


def _book_boundaries(body: str) -> list[tuple[int, int]]:
    """``(offset, book_number)`` for each body book heading, in order.

    Monotonic by construction: a heading is kept only when it numbers the
    book after the last one accepted. That drops a repeat of the current
    book's heading in a running header, and it means an OCR misread of an
    ordinal loses one boundary rather than renumbering the rest of the
    work.
    """

    out: list[tuple[int, int]] = []
    for m in _BUCH_RE.finditer(body):
        ordinal = m.group(1).split()[0].upper()
        number = _BUCH_ORDINALS[ordinal]
        if number != (out[-1][1] + 1 if out else 1):
            continue
        out.append((m.start(), number))
    return out


def _book_at(boundaries: list[tuple[int, int]], offset: int) -> str | None:
    """The book covering ``offset`` — the last heading at or before it.

    Note what this deliberately does NOT do: it never advances the book
    ahead of the text it stamps. `tei.py` updates its `_cur_book` on
    entering book N+1 *before* flushing the buffered tail of book N, so
    the last chunk of every book is stamped N+1 there (pinned by
    tests/test_homer_ingest.py:87). Resolving by offset at the moment a
    section is created cannot reproduce that.
    """

    book: str | None = None
    for pos, number in boundaries:
        if pos > offset:
            break
        book = str(number)
    return book


def _emit_sections(
    body: str, *, work_title: str, translator: str, year: str, source_file: str
) -> Iterator[Chunk]:
    """Reconstruct Stephanus sections from the marker stream and yield one
    chunk per section."""
    boundaries = _book_boundaries(body)
    sections: dict[str, list[str]] = {}
    books: dict[str, str | None] = {}
    order: list[str] = []
    page: str | None = None
    letter: str | None = None
    last = 0
    for m in _MARK_RE.finditer(body):
        seg = body[last:m.start()]
        if page and letter and seg.strip():
            loc = f"{page}{letter.lower()}"
            if loc not in sections:
                sections[loc] = []
                # Resolved at the segment's START: a heading sitting
                # inside this segment opens the NEXT section's book, not
                # this one's. The heading is preceded by the closing
                # prose of the outgoing book.
                books[loc] = _book_at(boundaries, last)
                order.append(loc)
            sections[loc].append(seg)
        if m.group(1):
            page = m.group(1)
        letter = m.group(2)
        last = m.end()
    if page and letter and body[last:].strip():
        loc = f"{page}{letter.lower()}"
        if loc not in sections:
            sections[loc] = []
            books[loc] = _book_at(boundaries, last)
            order.append(loc)
        sections[loc].append(body[last:])

    for loc in order:
        # The heading is a structural marker, not prose — it would
        # otherwise sit mid-paragraph in whichever chunk spans the
        # boundary.
        text = _norm_text(_BUCH_RE.sub("", " ".join(sections[loc])))
        if not text:
            continue
        yield Chunk(
            chunk_id=_make_chunk_id(source_file, work_title, "deu", loc, text[:120]),
            corpus="plato",
            author="Plato",
            work=work_title,
            lang="deu",
            section=loc,
            book=books[loc],
            page=None,
            speaker=None,
            text=text,
            source_file=source_file,
            translator=translator,
            edition_year=year,
            citation_system="stephanus",
            block_type=None,
            # Conventional German title where one differs from the Greek
            # name ("Der Staat" for Politeia); else None → the reader shows
            # the canonical Latinized-Greek name (correct German usage).
            title_local=plato_titles.local_title(work_title, "deu"),
        )


def split_platon_werke(path: Path, work: CorpusWork) -> Iterator[Chunk]:
    try:
        import fitz  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover
        raise IngestDepsMissing(
            "PDF ingest requires `pymupdf`. Install with `pip install -e '.[hegel]'`."
        ) from exc

    source_file = path.name
    with fitz.open(path) as doc:
        page_texts = [doc[i].get_text() for i in range(doc.page_count)]

    # 1) Find each work's start page.
    seen_alkibiades = 0
    starts: list[tuple[int, str]] = []  # (page_index, canonical_title)
    for i, t in enumerate(page_texts):
        canon = _resolve_heading(t, seen_alkibiades)
        if canon is None:
            continue
        # Guard against re-detecting the same work on a continuation page
        # that happens to repeat the title in a running header.
        if starts and starts[-1][1] == canon:
            continue
        if canon.startswith("Alkibiades"):
            seen_alkibiades += 1
        starts.append((i, canon))

    # 2) Walk each work span and emit its sections.
    for idx, (start, canon) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(page_texts)
        body = _clean_body("\n".join(page_texts[start:end]))
        translator, year = _TRANSLATOR.get(canon, _SCHLEIERMACHER)
        yield from _emit_sections(
            body, work_title=canon, translator=translator, year=year, source_file=source_file
        )
