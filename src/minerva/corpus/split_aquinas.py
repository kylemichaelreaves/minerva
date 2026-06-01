"""Aquinas splitter — Summa Theologiae, Summa contra Gentiles, and
the four major Aristotle commentaries (Ethics, Metaphysics, Physics,
De anima).

Six works share one marker family produced by
`perseus/download_aquinas.py`:

    [ST.<p>.<q>.<a>]      ST Pars `p` (1=I, 2=I-II, 3=II-II, 4=III),
                          Quaestio `q`, Articulus `a`. `a=0` is the
                          Quaestio's prooemium.
    [SCG.<lib>.<cap>]     SCG Liber `lib` (1–4), Caput `cap`.
    [SENT_<W>.<lib>.<l>]  Aristotle-commentary lectio. `W` ∈
                          {ETH, MET, PHY, AN} — Ethics, Metaphysics,
                          Physics, De anima. `lib=0 l=0` is the
                          commentary prooemium (Metaphysics only).

The splitter walks the marker stream, slices each chunk's body
between consecutive markers, and emits one `Chunk` per match with
Reader-friendly section labels matching scholarly Latin citation:

    [ST.1.2.3]        → 'ST I, q. 2, a. 3'                book='ST I'
    [SCG.1.13]        → 'SCG I, cap. 13'                  book='SCG I'
    [SENT_ETH.1.1]    → 'Sent. Ethic., lib. 1, lect. 1'   book='Sent. Ethic., lib. 1'
    [SENT_MET.0.0]    → 'Sent. Metaphys., pr.'            book='Sent. Metaphys.'
    [SENT_PHY.8.4]    → 'In Physic., lib. 8, lect. 4'     book='In Physic., lib. 8'
    [SENT_AN.3.7]     → 'Sent. De anima, lib. 3, lect. 7' book='Sent. De anima, lib. 3'

Granularity: one chunk per article for ST (with sub-sections inlined
as `[arg. 1]…[s. c.]…[co.]…[ad 1]…` labels by the downloader); one
chunk per chapter for SCG; one chunk per lectio for the commentaries
(with `[n. K]` paragraph labels inlined).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..corpus_works import CorpusWork
from ..tei import Chunk, _make_chunk_id, _norm_text

# Pars code → Roman label used in the human-facing citation. The
# encoding (1=I, 2=I-II, …) mirrors the slug numbering on
# corpusthomisticum.org so the downloader's marker shape stays
# memorable.
_ST_PARS_LABEL: dict[int, str] = {
    1: "I",
    2: "I-II",
    3: "II-II",
    4: "III",
}


# Single regex matching all marker shapes via named-group alternation.
# Anchored to start-of-line because the downloader emits markers on
# their own line; bracketed inline references (the inline `[arg. 1]`,
# `[n. 7]`, etc. sub-labels in the body) lack the `^` anchor and
# never match.
_MARKER_RE = re.compile(
    r"^(?:"
    # ST: [ST.<p>.<q>.<a>]
    r"\[ST\.(?P<st_p>\d+)\.(?P<st_q>\d+)\.(?P<st_a>\d+)\]"
    r"|"
    # SCG: [SCG.<lib>.<cap>]
    r"\[SCG\.(?P<scg_lib>\d+)\.(?P<scg_cap>\d+)\]"
    r"|"
    # Aristotle commentary: [SENT_<W>.<lib>.<lect>]
    r"\[SENT_(?P<sent_w>ETH|MET|PHY|AN)\.(?P<sent_lib>\d+)\.(?P<sent_lect>\d+)\]"
    r")\s*$",
    re.MULTILINE,
)


# Reader-facing book/section labels per commentary. The keys match
# the marker tag emitted by the downloader; the values give the
# user-visible work-name prefix used in both the section label
# ("lib. L, lect. M") and the book label (which scopes "lib. L"
# into the work's book grouping).
_SENT_LABELS: dict[str, str] = {
    "ETH": "Sent. Ethic.",
    "MET": "Sent. Metaphys.",
    "PHY": "In Physic.",
    "AN": "Sent. De anima",
}


def _section_for_match(m: re.Match[str]) -> tuple[str, str]:
    """Return (section_label, book_label) for one marker match.

    `section_label` is the user-visible locator that goes into
    `chunks.section` ('ST I, q. 2, a. 3' / 'SCG I, cap. 13').
    `book_label` is the major division for grouping ('ST I', 'ST I-II',
    'ST II-II', 'ST III', 'SCG I', …).
    """

    if m.group("st_p"):
        p = int(m.group("st_p"))
        q = int(m.group("st_q"))
        a = int(m.group("st_a"))
        pars_label = _ST_PARS_LABEL.get(p, str(p))
        book = f"ST {pars_label}"
        if q == 0:
            # Pars-level prooemium (the short introduction Aquinas
            # wrote at the start of each Pars) — cite as `ST <Pars>, pr.`
            return f"ST {pars_label}, pr.", book
        if a == 0:
            # Question prooemium — cite as `ST <Pars>, q. <Q>, pr.`
            # rather than inventing an article-0 number.
            return f"ST {pars_label}, q. {q}, pr.", book
        return f"ST {pars_label}, q. {q}, a. {a}", book

    if m.group("scg_lib"):
        lib = int(m.group("scg_lib"))
        cap = int(m.group("scg_cap"))
        # SCG Liber labels are Roman in scholarly citation. The four
        # books are I, II, III, IV — small enough that a lookup is
        # clearer than a converter.
        roman_lib = {1: "I", 2: "II", 3: "III", 4: "IV"}.get(lib, str(lib))
        return f"SCG {roman_lib}, cap. {cap}", f"SCG {roman_lib}"

    if m.group("sent_w"):
        tag = m.group("sent_w")
        lib = int(m.group("sent_lib"))
        lect = int(m.group("sent_lect"))
        label = _SENT_LABELS[tag]
        # Prooemium uses lib=0 lect=0; render as "<label>, pr." with
        # the book label scoped to the whole work (no "lib. 0" line).
        if lib == 0:
            return f"{label}, pr.", label
        return f"{label}, lib. {lib}, lect. {lect}", f"{label}, lib. {lib}"

    raise RuntimeError(f"unrecognised Aquinas marker shape: {m.group(0)!r}")


def split_aquinas(text: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    """Walk ``text`` for Aquinas markers, emitting one Chunk per
    chunk. Body is everything between this marker and the next,
    whitespace-normalised; the marker line itself is consumed by the
    regex match's end offset."""

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
