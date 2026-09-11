"""Kant A/B marginal pagination — Cambridge KrV splitter.

Cambridge editions of the Critique of Pure Reason interleave Kant's
A (1781) and B (1787) page numbers in the margins. PyMuPDF surfaces
them as standalone marker lines like ``A 47``, ``B 63``, or
``A449/B477`` (for passages preserved across both editions). Chapter
heads carry an edition annotation: ``Section II. On Time <B>``. This
splitter walks the text, treats each marker line as a fresh chunk
boundary, and records the A/B locator in ``section`` (parseable as
``kant_ab`` by ``locations.parse_section``) while the most-recent
chapter heading lives in ``book``.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterator
from pathlib import Path

from ..corpus_works import CorpusWork
from ..heading_clean import _is_editorial_heading, _is_skipped_for_work
from ..tei import Chunk, _make_chunk_id
from .split_paragraphic import _emit

# Standalone A/B marker: "A 47", "B 63", "A xiii", "Bvii", "A449"
# (with or without internal whitespace). Roman numerals appear for
# Kant's prefaces; Arabic for body text. Whole-line match — keeps us
# from matching in-prose mentions like "I refer to A 47 here".
_KANT_AB_MARKER_RE = re.compile(
    r"^\s*([AB])\s*(\d{1,4}|[ivxlcdm]{1,8})\s*$",
    re.IGNORECASE,
)
# Combined marker: "A449/B477" — section appears in both editions.
# Prefer the A side as canonical (oldest); the B value is recoverable
# from chunk content if needed.
_KANT_AB_COMBO_RE = re.compile(
    r"^\s*([AB])\s*(\d{1,4})\s*/\s*([AB])\s*(\d{1,4})\s*$",
    re.IGNORECASE,
)
# Chapter heading with edition annotation: "Introduction <B>",
# "Section II. On Time <B>", "Section III. ... <A>". The ``<a,b>``
# variant (both editions) also exists.
_KANT_AB_CHAPTER_RE = re.compile(r"^\s*(.{4,80})\s*<\s*([ABab])\s*(?:,\s*([ABab]))?\s*>\s*$")


def _norm_ab_marker(letter: str, number: str) -> str:
    """Render an A/B marker as a single-token section locator.

    Arabic numbers stay Arabic; Roman numerals are kept lowercase so
    ``locations.parse_section('kant_ab', ...)`` can extend its
    accepted range to cover the prefaces if/when needed. Output
    examples: ``A47``, ``B63``, ``Axiii``.

    OCR normalization for Roman numerals: PyMuPDF often misreads
    italic lowercase ``l`` as ``i`` (and vice versa); the Cambridge
    KrV uses italic Roman numerals for its preface pagination, so
    `Axiii` arrives as `Axill` and `Bxiv` as `Bxlv`. Since Kant's A
    and B preface pages each run to ~xxiv (24), the Roman 50 token
    ``l`` never legitimately appears — substitute ``l → i`` /
    ``L → I`` unconditionally for Roman inputs.
    """

    letter = letter.upper()
    n = number.strip()
    if n.isdigit():
        return f"{letter}{int(n)}"
    # Roman: drop the OCR-introduced `l` → `i` confusion.
    normalized_roman = n.lower().replace("l", "i")
    return f"{letter}{normalized_roman}"


def split_by_kant_ab(text: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    """Chunk an A/B-paginated text. Each chunk spans the prose between
    two consecutive A or B markers, with ``section`` set to the
    opening marker (e.g. ``A47``) and ``book`` to the most-recent
    chapter heading (e.g. ``Section II. On Time``).

    Prose before the first marker (Cambridge's preface page, the
    work's title page) is emitted with section=None so the global
    fallback locator (``¶1``) picks it up; the page range on the
    CorpusWork entry already trims publisher front-matter, so what falls
    in this bucket is real Kant prose without a Bekker page.

    Italic-Roman OCR misreads (``B II`` → ``B 11``, ``A III`` →
    ``A 111``) are corrected by a post-pass that swaps Arabic
    section labels back to Roman when the surrounding chunks are
    Roman-paginated. PyMuPDF can't disambiguate italic ``II`` from
    Arabic ``11`` reliably; the surrounding-context heuristic
    handles the cases we've seen without false-positive risk on
    body pages (which never sit next to Roman markers).
    """

    current_section: str | None = None
    current_heading: str | None = None
    current_block_type: str | None = None
    buffer: list[str] = []
    collected: list[Chunk] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if not body:
            return
        section_label = current_section or "¶1"
        chunk = _emit(
            work,
            path,
            section=section_label,
            text=body,
            book_label=current_heading,
            block_type=current_block_type,
        )
        if chunk is not None:
            collected.append(chunk)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        # Chapter heading with explicit edition annotation: flush so
        # the new heading starts a fresh chunk.
        ch = _KANT_AB_CHAPTER_RE.match(line)
        if ch:
            # The full heading text — minus the `<A>`/`<B>` suffix —
            # becomes the book label. Discard editorial-shaped lines
            # so glossary subheadings don't leak in.
            heading = ch.group(1).strip()
            editorial = _is_editorial_heading(heading) or _is_skipped_for_work(
                heading, work.skip_headings
            )
            # Apparatus is TAGGED, not dropped (#534). This site used to
            # flush and set `current_heading = None`, which discarded the
            # heading and emitted the editor's prose under a null one --
            # attributing it to Kant, which is worse than either keeping
            # it or dropping it outright (#537).
            flush()
            buffer = []
            current_heading = heading
            current_block_type = "editorial" if editorial else None
            continue
        # Combined A/B marker (e.g. "A449/B477"): boundary, use A.
        cb = _KANT_AB_COMBO_RE.match(line)
        if cb:
            flush()
            buffer = []
            current_section = _norm_ab_marker(cb.group(1), cb.group(2))
            continue
        # Standalone A/B marker
        mk = _KANT_AB_MARKER_RE.match(line)
        if mk:
            flush()
            buffer = []
            current_section = _norm_ab_marker(mk.group(1), mk.group(2))
            continue
        # Ordinary prose / blank lines
        buffer.append(raw_line)

    flush()
    _demangle_roman_misreads(collected)
    yield from collected


# Italic Roman → Arabic OCR misreads at the marker-recognition step.
# These pairs are the only practical confusions in Cambridge KrV's
# preface pagination (A i..xxiv, B vii..xliv): italic `II` reads as
# `11`, `III` as `111`, `IIII` (rare alt. for `iv`) as `1111`. Body
# pages never reach those values adjacent to Roman markers, so the
# adjacency check is sufficient context.
_ROMAN_MISREAD_FIXES = {"11": "ii", "111": "iii", "1111": "iv"}


def _demangle_roman_misreads(chunks: list[Chunk]) -> None:
    """Walk emitted chunks; if an Arabic section sits between Roman
    sections of the same A/B letter, convert it to the Roman form
    OCR most likely intended. Mutates `chunks` in place; chunk_ids
    stay stable because the section value isn't part of the id."""

    for i, ch in enumerate(chunks):
        if not ch.section or ch.section[:1] not in ("A", "B"):
            continue
        letter, rest = ch.section[0], ch.section[1:]
        if not rest.isdigit():
            continue
        fixed = _ROMAN_MISREAD_FIXES.get(rest)
        if not fixed:
            continue

        # Adjacency: any Roman-paginated chunk (either letter) within
        # ±6 positions counts as evidence we're still in preface
        # territory. The dedication page in particular sits among
        # alternating A and B Roman markers, so a same-letter
        # requirement is too tight.
        def _has_roman_neighbor(start: int, stop: int, step: int) -> bool:
            for j in range(start, stop, step):
                if j < 0 or j >= len(chunks):
                    continue
                sec = chunks[j].section or ""
                if sec[:1] in ("A", "B") and sec[1:] and not sec[1:].isdigit():
                    return True
            return False

        near_roman = _has_roman_neighbor(i - 1, i - 7, -1) or _has_roman_neighbor(i + 1, i + 7, 1)
        if near_roman:
            # Recompute chunk_id so two chunks that ended up with
            # the same section (e.g. body A11 and demangled-Aii)
            # don't collide. Same recipe as _make_chunk_id called
            # from _emit.
            new_section = f"{letter}{fixed}"
            chunks[i] = dataclasses.replace(
                ch,
                section=new_section,
                chunk_id=_make_chunk_id(
                    ch.source_file,
                    ch.work,
                    ch.lang,
                    ch.book or "",
                    new_section,
                    "",
                    ch.text[:120],
                ),
            )
