"""Parser for Internet Classics Archive plain-text Aristotle files.

ICA serves a ``<work>.mb.txt`` file alongside each per-section HTML
page. The text version is structured as:

    Provided by The Internet Classics Archive.
    See bottom for copyright. Available online at
        http://classics.mit.edu//Aristotle/<work>.html

    <Canonical Title>
    By Aristotle


    Translated by <Translator Name>

    ----------------------------------------------------------------------

    SECTION 1

    Part 1

    <prose paragraph>

    <next prose paragraph>

    ...

    SECTION 2

    Part 1

    <prose>
    ...

`SECTION N` is a top-level book/major-division marker. `Part N`
restarts at 1 within each SECTION and is the locator the
ICA-translation tradition uses for citing Aristotle in English. We
emit one chunk per Part — paragraph-level chunking inside a Part
would be too fine-grained for the cross-translation rendering grid
the term-glossary system uses.

This module emits :class:`tei.Chunk` objects so the rest of the
ingest pipeline can consume them unchanged. Citation values are
recorded as ``section = '<SECTION>.<Part>'`` to mimic the
"Bekker-shaped" two-level locator the existing chunks schema
expects, even though ICA itself doesn't expose true Bekker page+line.
True Bekker pagination for these works isn't in the ICA text;
recovering it would require cross-referencing against the Greek.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from minerva.tei import Chunk, _make_chunk_id, _norm_text

_SECTION_HDR = re.compile(r"^SECTION\s+(\d+)\s*$", re.MULTILINE)
_BOOK_HDR = re.compile(r"^BOOK\s+([IVXLC]+)\s*$", re.MULTILINE)
_PART_HDR = re.compile(r"^Part\s+(\d+)\s*$", re.MULTILINE)
_TRANSLATOR = re.compile(r"^Translated by\s+(.+?)\s*$", re.MULTILINE)
_TITLE = re.compile(r"^Translated by\s+", re.MULTILINE)  # marker for header-end


def _roman_to_int(roman: str) -> int:
    """Tiny Roman → Arabic for ICA's BOOK I / II / III / ... headers."""
    table = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total, prev = 0, 0
    for ch in reversed(roman):
        v = table.get(ch, 0)
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    return total


def _split_header(raw: str) -> tuple[str | None, str]:
    """Split the title-page header from the prose body.

    Returns ``(translator, prose)``. The body starts immediately after
    the divider line (``------...``) below the header. If no divider
    is found we return the whole text as body and best-effort
    translator extraction.
    """

    m = _TRANSLATOR.search(raw)
    translator = m.group(1).strip() if m else None

    # The divider is a long run of '-' characters; everything before
    # it is preamble.
    div = re.search(r"^-{20,}\s*$", raw, re.MULTILINE)
    if div is None:
        return translator, raw
    return translator, raw[div.end() :]


def _split_paragraphs(prose: str) -> list[str]:
    """Split a Part's body into paragraphs.

    ICA's text-mirror wraps lines at ~70 columns but uses blank lines
    to separate paragraphs. Treat any run of two or more newlines as
    the paragraph boundary; collapse the internal soft-wraps so each
    chunk reads as continuous prose.

    Divider lines (``--------...`` — used by ICA between SECTION/BOOK
    boundaries) are dropped so they don't surface as their own
    paragraph chunks (the 2026-05-31 audit found 58 such chunks
    leaking into Aristotle's corpus before this guard).
    """

    out: list[str] = []
    for block in re.split(r"\n[ \t]*\n", prose):
        joined = " ".join(line.strip() for line in block.splitlines() if line.strip())
        if not joined:
            continue
        if re.fullmatch(r"-{10,}", joined):
            continue
        out.append(joined)
    return out


def _split_by_part(body: str) -> Iterator[tuple[str, str, str]]:
    """Yield ``(section, part, prose)`` for every Part in the body.

    ``section`` is the major-division number — either Arabic from a
    ``SECTION N`` header (used by shorter works like Categories,
    Sophistical Refutations, On Interpretation) or the
    Arabic-converted form of a Roman ``BOOK I`` header (used by
    larger works: Physics, Topics, On the Soul, the biological
    works). ``part`` is the Part header's number (resets to 1 each
    SECTION/BOOK).

    Some short Parva Naturalia have no major-division header at all
    (Movement of Animals, On Dreams, etc.) — those works present as
    a flat sequence of Part headers. We treat the implied section as
    "1" so they still produce locator-shaped section strings.
    """

    current_section: str | None = None
    cuts: list[tuple[int, int, str, str]] = []  # (start, end, sec, part)
    last_anchor: tuple[int, str, str] | None = None
    # Combined pattern: SECTION arabic, BOOK roman, or Part arabic.
    pat = re.compile(
        r"^(?:SECTION\s+(\d+)|BOOK\s+([IVXLC]+)|Part\s+(\d+))\s*$",
        re.MULTILINE,
    )
    for m in pat.finditer(body):
        sect_arabic, book_roman, part_num = m.group(1), m.group(2), m.group(3)
        if sect_arabic is not None:
            current_section = sect_arabic
            continue
        if book_roman is not None:
            current_section = str(_roman_to_int(book_roman))
            continue
        if part_num is not None:
            if current_section is None:
                # Flat-Part works (no SECTION/BOOK headers, e.g. some
                # short Parva Naturalia). Synthesize section "1".
                current_section = "1"
            if last_anchor is not None:
                cuts.append((last_anchor[0], m.start(), last_anchor[1], last_anchor[2]))
            last_anchor = (m.end(), current_section, part_num)
    if last_anchor is not None:
        cuts.append((last_anchor[0], len(body), last_anchor[1], last_anchor[2]))

    for start, end, sec, part in cuts:
        prose = body[start:end].strip()
        if prose:
            yield sec, part, prose


def parse_ica_text(
    path: Path,
    *,
    corpus: str,
    author: str,
    work: str,
    translator: str | None,
    edition_year: str | None,
) -> Iterator[Chunk]:
    """Parse one ``<work>.mb.txt`` file into Chunks.

    Caller supplies ``corpus`` / ``author`` / ``work`` because ICA's
    text doesn't carry author-side metadata in a structured form
    beyond the title line (which is the same as the work title).
    ``translator`` may be passed explicitly when known; otherwise we
    extract it from the file's "Translated by" header.
    """

    raw = path.read_text(encoding="utf-8", errors="replace")
    file_translator, body = _split_header(raw)
    chosen_translator = translator or file_translator

    for sec, part, prose in _split_by_part(body):
        # Within each Part, split on blank lines so each paragraph
        # becomes its own chunk. Without this, a "Part" in ICA's
        # text-mirror is often page-sized — too coarse for the
        # term-glossary granularity (the Greek side from First1KGreek
        # chunks per `<p>`). Matching granularities lets pairing
        # work as the reader UI expects.
        paragraphs = _split_paragraphs(prose)
        for p_idx, para in enumerate(paragraphs, 1):
            text = _norm_text(para)
            if not text:
                continue
            section_label = f"{sec}.{part}.¶{p_idx}"
            chunk_id = _make_chunk_id(
                path.name,
                work,
                "eng",
                "",
                section_label,
                "",
                text[:120],
            )
            yield Chunk(
                chunk_id=chunk_id,
                corpus=corpus,
                author=author,
                work=work,
                lang="eng",
                section=section_label,
                book=sec,  # The major-division number doubles as `book`
                page=None,
                speaker=None,
                text=text,
                source_file=path.name,
                translator=chosen_translator,
                edition_year=edition_year,
            )


def parse_dir(directory: Path) -> Iterator[Chunk]:
    """Walk an ICA download directory layout
    (``<canonical_title>/eng.txt`` per work) and yield Chunks.

    Importing the aristotle_works catalog gives us the canonical
    title + ICA translator metadata without re-deriving from the
    filename, and keeps the source mapping in one place.
    """

    from minerva.authors.aristotle_works import works_with_ica

    by_slug = {_slug_for_title(w.canonical_title): w for w in works_with_ica()}

    for entry in sorted(directory.iterdir()):
        if not entry.is_dir():
            continue
        text_file = entry / "eng.txt"
        if not text_file.is_file():
            continue
        meta = by_slug.get(entry.name)
        if meta is None:
            print(f"ica: skipping unknown work directory {entry.name!r}")
            continue
        yield from parse_ica_text(
            text_file,
            corpus="aristotle",
            author="Aristotle",
            work=meta.canonical_title,
            translator=None,  # discovered from the file header
            edition_year=None,
        )


def _slug_for_title(title: str) -> str:
    """Mirror of the downloader's slug derivation. Kept here so the
    parser doesn't need to import the downloader script."""
    return "".join(c.lower() if c.isalnum() else "_" for c in title).strip("_")
