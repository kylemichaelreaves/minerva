"""Augustine splitter — Confessiones, De civitate Dei, De Trinitate.

Three works share one marker format produced by
`perseus/download_augustine.py`:

    [CONF.<b>.<c>.<p>]   Confessiones Liber `b`, Caput `c`, ¶ `p`
    [CIV.<b>.<c>]        De civitate Dei Liber `b`, Caput `c`
    [TRIN.<b>.<c>.<p>]   De Trinitate Liber `b`, Caput `c`, ¶ `p`

The splitter walks the marker stream, slices each chunk's body
between consecutive markers, and emits one `Chunk` per match with
Reader-friendly section labels matching scholarly citation shape:

    [CONF.8.7.16]   → 'Conf. VIII.7.16'   book='Conf. VIII'
    [CIV.19.13]     → 'Civ. Dei XIX.13'   book='Civ. Dei XIX'
    [TRIN.9.4.7]    → 'Trin. IX.4.7'      book='Trin. IX'

Granularity is per-paragraph for Confessions and De Trinitate (the
Wikisource source carries paragraph anchors), and per-chapter for
De civitate Dei (the source only carries chapter anchors). The
`book` field carries the bare major-division label so the Reader can
group chunks ('Conf. VIII', 'Civ. Dei XIX', 'Trin. IX', …).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..corpus_works import CorpusWork
from ..tei import Chunk, _make_chunk_id, _norm_text

# Arabic → Roman for the Liber numerals. Confessiones tops out at 13,
# Civ. Dei at 22, De Trin. at 15 — a lookup table is clearer than a
# general converter for these bounded ranges.
_ROMAN: dict[int, str] = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
    6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X",
    11: "XI", 12: "XII", 13: "XIII", 14: "XIV", 15: "XV",
    16: "XVI", 17: "XVII", 18: "XVIII", 19: "XIX", 20: "XX",
    21: "XXI", 22: "XXII",
}


def _roman(n: int) -> str:
    return _ROMAN.get(n, str(n))


# Single regex matching all three marker shapes via named-group
# alternation. Anchored to start-of-line because the downloader
# emits markers on their own line; in-body bracketed references
# (Bible citations, etc.) lack the `^` anchor and never match.
_MARKER_RE = re.compile(
    r"^(?:"
    # Confessions: [CONF.<b>.<c>.<p>]
    r"\[CONF\.(?P<conf_b>\d+)\.(?P<conf_c>\d+)\.(?P<conf_p>\d+)\]"
    r"|"
    # Civ. Dei: [CIV.<b>.<c>]
    r"\[CIV\.(?P<civ_b>\d+)\.(?P<civ_c>\d+)\]"
    r"|"
    # De Trinitate: [TRIN.<b>.<c>.<p>]
    r"\[TRIN\.(?P<trin_b>\d+)\.(?P<trin_c>\d+)\.(?P<trin_p>\d+)\]"
    r")\s*$",
    re.MULTILINE,
)


def _section_for_match(m: re.Match[str]) -> tuple[str, str]:
    """Return (section_label, book_label) for one marker match.

    `section_label` is the user-visible locator that goes into
    `chunks.section` (e.g. 'Conf. VIII.7.16'). `book_label` is the
    major division for grouping ('Conf. VIII', 'Civ. Dei XIX',
    'Trin. IX').
    """

    if m.group("conf_b"):
        b = int(m.group("conf_b"))
        c = int(m.group("conf_c"))
        p = int(m.group("conf_p"))
        rb = _roman(b)
        return f"Conf. {rb}.{c}.{p}", f"Conf. {rb}"

    if m.group("civ_b"):
        b = int(m.group("civ_b"))
        c = int(m.group("civ_c"))
        rb = _roman(b)
        return f"Civ. Dei {rb}.{c}", f"Civ. Dei {rb}"

    if m.group("trin_b"):
        b = int(m.group("trin_b"))
        c = int(m.group("trin_c"))
        p = int(m.group("trin_p"))
        rb = _roman(b)
        return f"Trin. {rb}.{c}.{p}", f"Trin. {rb}"

    # Unreachable — `finditer` only yields matches against the
    # exhaustive alternation above.
    raise RuntimeError(f"unrecognised Augustine marker shape: {m.group(0)!r}")


def split_augustine(text: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    """Walk ``text`` for Augustine markers, emitting one Chunk per
    chunk. Body is everything between this marker and the next,
    whitespace-normalised; the marker line itself is consumed by the
    regex match's end offset, and the leading blank line `_render`
    inserts after the marker is collapsed by `_norm_text`.
    """

    matches = list(_MARKER_RE.finditer(text))
    if not matches:
        return

    for i, m in enumerate(matches):
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = _norm_text(text[body_start:body_end])
        if not body:
            continue

        section_label, book_label = _section_for_match(m)
        chunk_id = _make_chunk_id(
            path.name,
            work.title,
            work.lang,
            book_label,
            section_label,
            "",
            body[:120],
        )
        yield Chunk(
            chunk_id=chunk_id,
            corpus=work.corpus,
            author=work.author,
            work=work.title,
            lang=work.lang,
            section=section_label,
            book=book_label,
            page=None,
            speaker=None,
            text=body,
            source_file=path.name,
            translator=work.translator,
            edition_year=work.edition_year,
            citation_system=work.citation_system,
        )
