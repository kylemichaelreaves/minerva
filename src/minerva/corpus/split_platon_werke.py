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

import dataclasses
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

# ── Title-page attributions (#206) ───────────────────────────────────
#
# This table used to be seven overrides plus a silent fallback to
# ("Friedrich Schleiermacher", "1818"). The fallback covered 41 of the 48
# works and was wrong far more often than right: only Euthyphron and Apologia
# are actually the 1818 second edition, the other Schleiermacher dialogues
# come from later Auflagen (1826, 1855-1861), Susemihl's volumes are each a
# different year, and the thirteen Letters are not Schleiermacher at all.
#
# The volume states every attribution itself, once per work, in a fixed
# formula on the work's own title page:
#
#     Nach der Übersetzung von <translator> in: <edition>, <city> <year>,
#     bearbeitet.
#
# Every entry below is transcribed from one of those, and carries the PDF page
# it was read from so the claim is checkable rather than merely asserted. The
# front matter (p2) confirms the closed set of five translators: Schleiermacher
# "vor allem", with Georgii, Susemihl, Teuffel and Wiegand "zur Ergänzung".
#
# THERE IS NO DEFAULT. An unlisted work raises — see `attribution_for`.


@dataclasses.dataclass(frozen=True)
class Attribution:
    """Who translated a work, in which year, and where that was read."""

    translator: str
    year: str
    #: PDF page (0-based, as `fitz` numbers them) carrying the formula.
    source_page: int = 0


def _a(translator: str, year: str, page: int) -> Attribution:
    return Attribution(translator, year, page)


_SCHL = "Friedrich Schleiermacher"
_SUSE = "Franz Susemihl"
_GEOR = "Ludwig Georgii"
_TEUF = "Wilhelm Siegmund Teuffel"
_WIEG = "Wilhelm Wiegand"

#: The thirteen Letters share one title page (p1342), hence one attribution.
_LETTERS = {
    f"Epistole {n}": _a(_WIEG, "1859", 1342)
    for n in (
        "I", "II", "III", "IV", "V", "VI", "VII",
        "VIII", "IX", "X", "XI", "XII", "XIII",
    )
}

_ATTRIBUTION: dict[str, Attribution] = {
    "Euthyphron": _a(_SCHL, "1818", 3),
    "Apologia": _a(_SCHL, "1818", 16),
    "Kriton": _a(_SCHL, "1855", 32),
    "Phaidon": _a(_SCHL, "1861", 41),
    "Kratylos": _a(_SCHL, "1857", 86),
    "Theaitetos": _a(_SCHL, "1856", 130),
    "Sophistes": _a(_SCHL, "1857", 187),
    "Politikos": _a(_SCHL, "1857", 234),
    "Parmenides": _a(_SUSE, "1865", 278),
    "Philebos": _a(_SCHL, "1861", 326),
    "Symposion": _a(_SUSE, "1855", 376),
    "Phaidros": _a(_GEOR, "1853", 412),
    # p450 "Erster Dialog", p483 "Zweiter Dialog" — different Auflagen.
    "Alkibiades I": _a(_SCHL, "1826", 450),
    "Alkibiades II": _a(_SCHL, "1855", 483),
    "Hipparchos": _a(_SCHL, "1855", 494),
    "Erastai": _a(_SCHL, "1861", 501),
    "Theages": _a(_SCHL, "1861", 508),
    "Charmides": _a(_SCHL, "1855", 517),
    "Laches": _a(_SCHL, "1855", 536),
    "Lysis": _a(_SCHL, "1855", 553),
    "Euthydemos": _a(_SCHL, "1856", 571),
    "Protagoras": _a(_SCHL, "1855", 601),
    "Gorgias": _a(_SCHL, "1856", 637),
    "Menon": _a(_SCHL, "1856", 698),
    "Hippias Meizon": _a(_SCHL, "1861", 724),
    "Hippias Elatton": _a(_SCHL, "1855", 744),
    "Ion": _a(_SCHL, "1855", 755),
    "Menexenos": _a(_SCHL, "1861", 765),
    "Kleitophon": _a(_SCHL, "1861", 775),
    # Politeia is handled by `attribution_for` — two translators, split by
    # book. Recorded here as well so the "every work is present" check covers
    # it; the value is the Teuffel half.
    "Politeia": _a(_TEUF, "1855", 779),
    "Timaios": _a(_SUSE, "1856", 1015),
    "Kritias": _a(_SUSE, "1857", 1065),
    "Minos": _a(_SCHL, "1855", 1076),
    # p1085 cites "Stuttgart 1862, 1863" — a multi-volume run across two
    # years. The later one is the completed edition.
    "Nomoi": _a(_SUSE, "1863", 1085),
    "Epinomis": _a(_SUSE, "1863", 1328),
    **_LETTERS,
}

#: Politeia is the only work in the volume with two translators, split at the
#: book boundary (p779). Representable because German Politeia chunks carry
#: `book` (#201) and `chunks.translation_id` is per-chunk, so the two land as
#: two `translations` rows with their chunks routed between them.
_POLITEIA_SPLIT: dict[int, Attribution] = {
    **{b: _a(_TEUF, "1855", 779) for b in range(1, 6)},
    **{b: _a(_WIEG, "1855", 779) for b in range(6, 11)},
}


def attribution_for(canon: str, book: str | None = None) -> Attribution:
    """The title-page attribution for *canon*, or raise.

    Deliberately total-or-fatal. The defect this replaces was a silent
    default: an unlisted work received a confident wrong translator and year,
    and nothing downstream could tell that from a checked one. Stopping the
    ingest costs one title-page reading; the alternative cost 41 wrong rows
    that sat unnoticed for a release (#206).
    """

    if canon == "Politeia":
        if book is None:
            raise ValueError(
                "Politeia's translator depends on the book (Teuffel I-V, "
                "Wiegand VI-X) and this chunk carries no book — the "
                "book-boundary scan failed; fix that rather than picking one"
            )
        try:
            return _POLITEIA_SPLIT[int(book)]
        except (KeyError, ValueError):
            raise ValueError(
                f"Politeia book {book!r} is outside I-X; the book-boundary "
                "scan produced something the split cannot route"
            ) from None

    try:
        return _ATTRIBUTION[canon]
    except KeyError:
        raise ValueError(
            f"no title-page attribution recorded for {canon!r} — read its "
            "title page in the PDF and add it to `_ATTRIBUTION` with the page "
            "number. There is deliberately no default (#206)."
        ) from None

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


def _emit_sections(body: str, *, work_title: str, source_file: str) -> Iterator[Chunk]:
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
        # Resolved per section, not per work: Politeia's translator changes at
        # the book boundary, and `books[loc]` is already computed above (#206).
        attribution = attribution_for(work_title, books[loc])
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
            translator=attribution.translator,
            edition_year=attribution.year,
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
        # No attribution resolved here any more: `_emit_sections` asks per
        # section, because Politeia's changes at the book boundary (#206).
        yield from _emit_sections(body, work_title=canon, source_file=source_file)
