"""Spinoza splitter — Ethica's geometric structure + TIE / TP / TTP.

Four works share one marker format produced by the
``perseus/download_spinoza*.py`` downloaders:

    [E.<p>.<TYPE>.<n>]   Ethica Pars `p` (1–5)
                          TYPE ∈ {D (Definitiones), A (Axiomata),
                                  Post (Postulata), P (Propositio)}
                          n is the item number
    [E.<p>.App]          Ethica Pars `p` Appendix
    [TIE.<nnn>]          Tractatus de Intellectus Emendatione, §`nnn`
    [TP.<c>.<nnn>]       Tractatus Politicus, Caput `c`, art. `nnn`
    [TTP.<c>.<nnn>]      Tractatus Theologico-Politicus, Caput `c`
                          (0 = Praefatio), paragraph `nnn`

The splitter walks the marker stream, slices each chunk's body
between consecutive markers, and emits one `Chunk` per match with
Reader-friendly section labels:

    [E.1.D.1]    → 'E I, Def. 1'
    [E.1.A.3]    → 'E I, Ax. 3'
    [E.2.Post.5] → 'E II, Post. 5'
    [E.1.P.7]    → 'E I, P7'
    [E.1.App]    → 'E I, App.'
    [TIE.017]    → 'TIE §17'
    [TP.3.005]   → 'TP III, art. 5'
    [TTP.0.001]  → 'TTP Praef., ¶1'
    [TTP.7.004]  → 'TTP VII, ¶4'

The `book` field carries the bare major-division label so the
Reader can group chunks ('Ethica I', 'TIE', 'TP III', 'TTP VII', …).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..corpus_works import CorpusWork
from ..tei import Chunk, _make_chunk_id, _norm_text

# Roman numerals for Spinoza's Pars (1–5), TP Caput (1–11), and TTP
# Caput (1–20). A tiny lookup table is clearer than a general
# converter for these bounded ranges; chapter numbers above XX don't
# appear in any Spinoza work.
_ROMAN: dict[int, str] = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
    6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X",
    11: "XI", 12: "XII", 13: "XIII", 14: "XIV", 15: "XV",
    16: "XVI", 17: "XVII", 18: "XVIII", 19: "XIX", 20: "XX",
}

# Human-facing TYPE labels for the Ethica's section taxonomy.
_TYPE_LABEL: dict[str, str] = {
    "D": "Def.",
    "A": "Ax.",
    "Post": "Post.",
    "P": "P",  # Propositions get the bare "P" prefix — short and
               # idiomatic in Spinoza scholarship ("E IIp40s2").
}

# Single regex that matches all three marker shapes via alternation.
# Anchored to start-of-line because the downloader emits markers on
# their own line; in-body bracketed references like `[3]` (footnote
# numbers) lack the `^` anchor and never match.
_MARKER_RE = re.compile(
    r"^(?:"
    # Ethica Appendix — `[E.<p>.App]`
    r"\[E\.(?P<eapp_p>\d)\.App\]"
    r"|"
    # Ethica Def/Ax/Post/Prop — `[E.<p>.<TYPE>.<n>]`
    r"\[E\.(?P<eitem_p>\d)\.(?P<eitem_type>D|A|Post|P)\.(?P<eitem_n>\d+)\]"
    r"|"
    # TIE — `[TIE.<nnn>]`
    r"\[TIE\.(?P<tie_n>\d{3})\]"
    r"|"
    # TTP — `[TTP.<c>.<nnn>]` — must precede TP so the longer prefix
    # wins (re alternation is left-to-right; without this Python's
    # regex would attempt `TP` first and the trailing `TP\.…` would
    # leave the leading `T` dangling).
    r"\[TTP\.(?P<ttp_c>\d{1,2})\.(?P<ttp_n>\d{3})\]"
    r"|"
    # TP — `[TP.<c>.<nnn>]`
    r"\[TP\.(?P<tp_c>\d{1,2})\.(?P<tp_n>\d{3})\]"
    r")\s*$",
    re.MULTILINE,
)


def _section_for_match(m: re.Match[str]) -> tuple[str, str]:
    """Return (section_label, book_label) for one marker match.

    `section_label` is the user-visible locator that goes into
    `chunks.section` (e.g. 'E I, P7'). `book_label` is the major
    division for grouping ('Ethica I', 'TIE', 'TP III').
    """

    if m.group("eapp_p"):
        p = int(m.group("eapp_p"))
        roman = _ROMAN.get(p, str(p))
        return f"E {roman}, App.", f"Ethica {roman}"

    if m.group("eitem_p"):
        p = int(m.group("eitem_p"))
        type_code = m.group("eitem_type")
        n = int(m.group("eitem_n"))
        roman = _ROMAN.get(p, str(p))
        label = _TYPE_LABEL[type_code]
        # Propositions read `E I, P7`; everything else has a space:
        # `E I, Def. 1`. The bare-prefix idiom for Props matches
        # standard Spinoza citation shape.
        if type_code == "P":
            return f"E {roman}, {label}{n}", f"Ethica {roman}"
        return f"E {roman}, {label} {n}", f"Ethica {roman}"

    if m.group("tie_n"):
        n = int(m.group("tie_n"))
        return f"TIE §{n}", "TIE"

    if m.group("tp_c"):
        c = int(m.group("tp_c"))
        n = int(m.group("tp_n"))
        roman = _ROMAN.get(c, str(c))
        return f"TP {roman}, art. {n}", f"TP {roman}"

    if m.group("ttp_c"):
        c = int(m.group("ttp_c"))
        n = int(m.group("ttp_n"))
        # Praefatio = caput 0 in the marker stream; render as 'Praef.'.
        # Otherwise Roman ordinal Caput I-XX.
        if c == 0:
            return f"TTP Praef., ¶{n}", "TTP Praef."
        roman = _ROMAN.get(c, str(c))
        return f"TTP {roman}, ¶{n}", f"TTP {roman}"

    # Unreachable — the regex's alternation is exhaustive for
    # well-formed input, and `finditer` only yields matches.
    raise RuntimeError(f"unrecognised Spinoza marker shape: {m.group(0)!r}")


def split_spinoza(text: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    """Walk ``text`` for Spinoza markers, emitting one Chunk per
    chunk. Body is everything between this marker and the next
    (stripped of the marker line itself, whitespace-normalised).
    """

    matches = list(_MARKER_RE.finditer(text))
    if not matches:
        return

    for i, m in enumerate(matches):
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw_body = text[body_start:body_end]
        # The marker line we just matched is fully consumed by
        # `m.end()`, but the body still starts with the leading
        # newline + the blank line `_render` inserts after the
        # marker. `_norm_text` collapses both away.
        body = _norm_text(raw_body)
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
