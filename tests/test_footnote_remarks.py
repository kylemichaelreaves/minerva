"""Tests for typing Renan's own footnotes ``block_type='remark'`` (#732).

`ocr_reflow` keeps a scan's footnotes as paragraphs of their own, so each
one reaches the index as a chunk — 6,049 of Renan's 12,067, all typed as
body. They are Renan's words, not an editor's, so the type is `remark`
(as Marx's own footnotes in *Kapital* are), not the apparatus type `note`.

The fixture ``ocr_reflow/renan_peuple_israel_vol5_notes.txt`` is two
verbatim excerpts of *Histoire du peuple d'Israël* V (lines 318-381 and
10642-10700 of the corpus file): footnotes whose markers the OCR read
cleanly (`1. `) and mangled (`i. `, `S. `), and the chapter title
`* IMMORTALITE DE L AME CHEZ LES JUIFS.` that the `*` marker would
otherwise take for a note.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from minerva.authors import renan_works
from minerva.corpus.footnote_remarks import apply_footnote_remarks, opens_footnote
from minerva.corpus.pipeline import parse_file
from minerva.tei import Chunk

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "ocr_reflow"
    / ("renan_peuple_israel_vol5_notes.txt")
)
VOL5 = renan_works.WORKS[6]


def _parse(**changes: object) -> list[Chunk]:
    return list(parse_file(FIXTURE, dataclasses.replace(VOL5, **changes)))


class TestOpensFootnote:
    @pytest.mark.parametrize(
        "text",
        [
            "1. T. IV, p. 325-331.",
            "(1) Voir ci-dessus.",
            "( 11 ) Voir ci-dessus.",
            "(i) Voir ci-dessus.",
            "* Voir ci-dessus.",
            # Markers the OCR mangled.
            "i. Comp. I Macch., xv, 11-12.",
            "i . Ch. xc, 33 et suiv.",
            "(i. Comparez Actes, iv, 32 et siiiv.",
            "1 . Jos., Ant, XIII, V, 9 ; XVIII, i, 5.",
            "S. I Macch., xiv, 25 etsuiv.",
            "S. « lias supcrstitiones, licet contrarias sibi",
            "A. Énoch, xc.",
        ],
    )
    def test_notes(self, text: str) -> None:
        assert opens_footnote(text)

    @pytest.mark.parametrize(
        "text",
        [
            "Sauf cette intolérance, qui était l'essence même de l'État juif.",
            "* IMMORTALITE DE L AME CHEZ LES JUIFS.",
            "CIIAPITRK XII",
            "S. de la lettre",  # `S.` needs a capital after it
            "is. lower",
            "",
        ],
    )
    def test_not_notes(self, text: str) -> None:
        assert not opens_footnote(text)


class TestOnTheRealExcerpt:
    def test_footnotes_are_typed_remark(self) -> None:
        typed = {c.section: c.text for c in _parse() if c.block_type == "remark"}
        assert set(typed) == {
            "¶3",
            "¶4",
            "¶7",
            "¶8",
            "¶9",
            "¶10",
            "Ciiapitrk XII, ¶3",
            "Ciiapitrk XII, ¶4",
            "Ciiapitrk XII, ¶6",
            "Ciiapitrk XII, ¶7",
            "Ciiapitrk XII, ¶8",
            "Ciiapitrk XII, ¶9",
        }
        assert typed["¶9"] == "i. Comp. I Macch., xv, 11-12."
        assert typed["¶10"].startswith("S. I Macch., xiv, 25")

    def test_body_and_the_starred_heading_are_untouched(self) -> None:
        untyped = {c.section: c.text for c in _parse() if c.block_type is None}
        assert untyped["Ciiapitrk XII, ¶1"] == "* IMMORTALITE DE L AME CHEZ LES JUIFS."
        assert untyped["Ciiapitrk XII, ¶2"].startswith("L'auteur de la Sagesse")
        assert untyped["¶6"].startswith("Sauf cette intolérance")

    def test_typing_changes_no_id_and_no_text(self) -> None:
        typed = _parse()
        plain = _parse(footnote_remarks=False)
        assert [(c.chunk_id, c.text, c.section) for c in typed] == [
            (c.chunk_id, c.text, c.section) for c in plain
        ]
        assert {c.block_type for c in plain} == {None}

    def test_every_renan_work_asks_for_it(self) -> None:
        assert all(w.footnote_remarks for w in renan_works.WORKS)


class TestApply:
    @staticmethod
    def _chunk(text: str, block_type: str | None = None) -> Chunk:
        return Chunk(
            chunk_id="x",
            corpus="renan",
            author="Renan",
            work="w",
            lang="fra",
            section="¶1",
            book=None,
            page=None,
            speaker=None,
            text=text,
            source_file="f.txt",
            translator=None,
            edition_year=None,
            block_type=block_type,
        )

    def test_a_work_that_does_not_ask_is_returned_as_is(self) -> None:
        chunks = [self._chunk("1. Une note.")]
        work = dataclasses.replace(VOL5, footnote_remarks=False)
        assert apply_footnote_remarks(chunks, work) is chunks

    def test_an_existing_type_is_not_overwritten(self) -> None:
        (chunk,) = apply_footnote_remarks([self._chunk("1. Une note.", "editorial")], VOL5)
        assert chunk.block_type == "editorial"
