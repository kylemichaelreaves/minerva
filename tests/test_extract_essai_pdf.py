"""Tests for the *Essai sur la noblesse* extractor (#561, #578).

`tests/fixtures/essai_pdf/essai_pages.json` holds three consecutive pages
(PDF pages 59–61) of the Gallica scan as PyMuPDF reports them — each
line's box and spans — which is everything the extractor reads, so this
runs without the 17 MB PDF. The three pages carry a paragraph that runs
across two page breaks (`… au Gouver-` / `nement , furent …` / `ne
suivirent …`), a catchword with its signature (`B 4 nement ,`), a bare
catchword (`ne`), running heads on both rectos and the verso, and a note
area on every page.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "extract_essai_pdf", REPO / "scripts" / "extract-essai-pdf.py"
)
assert _spec is not None
assert _spec.loader is not None
ee = importlib.util.module_from_spec(_spec)
sys.modules["extract_essai_pdf"] = ee
_spec.loader.exec_module(ee)

from minerva.corpus.ocr_reflow import BLANK, BODY, NOTE, assemble  # noqa: E402
from minerva.corpus.split_paragraphic import is_heading_line  # noqa: E402

_FIXTURE = REPO / "tests" / "fixtures" / "essai_pdf" / "essai_pages.json"


def _pages() -> list[list]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return [ee.merge_fragments(ee.fragments(data["pages"][k])) for k in ("59", "60", "61")]


def _line(text: str, *, y: float = 0.5, x0: float = 0.15, x1: float = 0.8, size: float = 12.0):
    return ee.Line(y, x0, x1, size, text)


class TestJoinSpans:
    def test_the_lost_spaces_between_word_spans_come_back(self) -> None:
        """Every PyMuPDF mode renders this head `DiffertationsurlaNobleffe`."""

        assert ee.join_spans(["Differtation", "fur", " la", "Nobleffe"]) == (
            "Differtation fur la Nobleffe"
        )

    @pytest.mark.parametrize(
        ("spans", "text"),
        [
            (["Ceux", "-", "ci"], "Ceux-ci"),
            (["(", "6", ")"], "(6)"),
            (["maîtres", "."], "maîtres."),
            (["l'égalité", "'", " ,"], "l'égalité' ,"),
            (["", "bien", "  "], "bien"),
        ],
    )
    def test_attaching_punctuation_takes_no_space(self, spans: list[str], text: str) -> None:
        assert ee.join_spans(spans) == text


class TestFragments:
    def test_a_printed_line_split_in_two_is_merged(self) -> None:
        merged = ee.merge_fragments(
            [_line("tenans de la", y=0.5, x0=0.4), _line("du Roi", y=0.501, x0=0.15)]
        )
        assert [ln.text for ln in merged] == ["du Roi tenans de la"]

    def test_lines_come_back_top_to_bottom(self) -> None:
        merged = ee.merge_fragments([_line("second", y=0.6), _line("first", y=0.3)])
        assert [ln.text for ln in merged] == ["first", "second"]

    def test_no_fragments(self) -> None:
        assert ee.merge_fragments([]) == []

    @pytest.mark.parametrize(
        ("text", "stray"), [("،", True), ("ॐ", True), ("ab", False), ("1", False), ("abcd", False)]
    )
    def test_stray_glyphs(self, text: str, stray: bool) -> None:
        assert ee._is_stray_glyph(text) is stray

    def test_stray_glyphs_and_empty_lines_are_not_fragments(self) -> None:
        data = {
            "width": 100.0,
            "height": 100.0,
            "lines": [
                {"bbox": [10, 10, 20, 20], "spans": [{"text": "،", "size": 3.0}]},
                {"bbox": [10, 30, 20, 40], "spans": [{"text": " ", "size": 9.0}]},
                {"bbox": [10, 50, 90, 60], "spans": [{"text": "texte", "size": 12.0}]},
            ],
        }
        assert [f.text for f in ee.fragments(data)] == ["texte"]


class TestFurniture:
    def test_the_fixture_pages(self) -> None:
        kept, notes_at, dropped = ee.strip_furniture(_pages())
        assert [(p, kind, text) for p, kind, text in dropped] == [
            (0, "running head", "de France. 23"),
            (1, "running head", "24 Differtation fur la Nobleffe"),
            (2, "running head", "de France. 25"),
            (0, "catchword", "B 4 nement ,"),
            (1, "catchword", "ne"),
        ]
        # Page 61's `nement` has no next page here to be checked against,
        # so it stays — and its note area is found by the gap instead.
        assert kept[2][notes_at[2]].text.startswith("premiers Rois un Seigneur")
        # Where each page's catchword stood is where its note area begins.
        assert kept[1][notes_at[1]].text.startswith("( 11 ) Cité.")
        assert kept[0][notes_at[0]].text.startswith("nous aprend ci-après")

    @pytest.mark.parametrize(
        "text",
        ["27", "ARB 19", "24 ARC", "PAG ITI", "de France. 25", "Differtation fur la Nobleffe"],
    )
    def test_heads_in_the_top_band(self, text: str) -> None:
        assert ee.is_running_head(_line(text, y=0.08))

    def test_the_same_text_lower_down_is_text(self) -> None:
        assert not ee.is_running_head(_line("de France. 25", y=0.3))

    def test_a_first_line_of_text_in_the_top_band_is_text(self) -> None:
        assert not ee.is_running_head(_line("plonger dans le luxe & dans la dé-", y=0.10))

    @pytest.mark.parametrize("text", ["A 3", "B", "* D3", "Z"])
    def test_signatures(self, text: str) -> None:
        assert ee.is_signature(_line(text, y=0.8, x0=0.55))

    @pytest.mark.parametrize("text", ["Le", "La", "Roi", "Je"])
    def test_words_at_the_foot_are_not_signatures(self, text: str) -> None:
        """The first version's `[A-Z][a-z]?` took these for signatures."""

        assert not ee.is_signature(_line(text, y=0.8, x0=0.55))

    def test_a_signature_at_the_left_margin_is_text(self) -> None:
        assert not ee.is_signature(_line("A 3", y=0.8, x0=0.15))


class TestCatchwords:
    @pytest.mark.parametrize(
        ("line", "next_first"),
        [
            ("nement", "nement , furent ou retenus"),
            ("B Ro-", "Romains , & par conféquent"),  # divided like its word
            ("caufe", "cauſe d'eux s'apelle encore"),  # long s read as f
            ("* A 4 valoir", "valoir leurs droits"),  # after a signature
        ],
    )
    def test_catchwords(self, line: str, next_first: str) -> None:
        assert ee.is_catchword(_line(line, y=0.8, x0=0.7), next_first)

    @pytest.mark.parametrize(
        ("line", "next_first", "y", "x0"),
        [
            ("nement", "tout autre chose", 0.8, 0.7),  # not what follows
            ("nement", None, 0.8, 0.7),  # last page
            ("nement", "nement , furent", 0.8, 0.15),  # left margin: text
            ("nement", "nement , furent", 0.05, 0.7),  # the head band
            ("une ligne bien plus longue", "une ligne bien plus longue", 0.8, 0.7),
            ("x", "x", 0.8, 0.7),  # too short to compare
        ],
    )
    def test_not_catchwords(self, line: str, next_first: str | None, y: float, x0: float) -> None:
        assert not ee.is_catchword(_line(line, y=y, x0=x0), next_first)


class TestNoteArea:
    def test_found_by_the_gap_and_the_tighter_setting(self) -> None:
        body = [_line(f"texte {i}", y=0.1 + 0.03 * i) for i in range(12)]
        notes = [_line(f"note {i}", y=0.5 + 0.06 + 0.018 * i) for i in range(6)]
        lines = body + notes
        assert ee.note_area_start(lines) == len(body)

    def test_a_heading_gap_with_text_spacing_after_it_is_not_notes(self) -> None:
        lines = [_line(f"texte {i}", y=0.1 + 0.03 * i) for i in range(12)]
        lines += [_line(f"suite {i}", y=0.5 + 0.08 + 0.03 * i) for i in range(6)]
        assert ee.note_area_start(lines) == len(lines)

    def test_too_few_lines(self) -> None:
        assert ee.note_area_start([_line("a"), _line("b")]) == 2


class TestAssembly:
    def test_a_paragraph_runs_on_across_two_page_breaks_past_its_notes(self) -> None:
        kept, notes_at, _ = ee.strip_furniture(_pages())
        items = [
            item
            for page, at in zip(kept, notes_at, strict=True)
            for item in ee.page_items(page, at)
        ]
        paragraphs = assemble(items, is_heading_line)
        body = next(p for p in paragraphs if p.startswith("Ceux enfin"))
        assert "au Gouvernement , furent ou retenus auprès du Prince" in body
        assert "Les François ne ſuivirent point en cela" in body
        assert body.endswith("par des Seigneurs de cette Nation.")
        # Page 60's notes come after the paragraph they interrupted.
        after = paragraphs[paragraphs.index(body) + 1 :]
        assert any(p.startswith("( 11 ) Cité.") for p in after)
        assert any(p.startswith("(12) Comte , du latin Comes.") for p in after)

    def test_page_items_marks_paragraph_ends_and_the_page_break(self) -> None:
        lines = [
            _line("une ligne pleine de texte qui va", x1=0.8),
            _line("jusqu'au bout.", x1=0.4),
            _line("Un alinéa rentré", x0=0.2),
            _line("( 1 ) une note", x0=0.15),
        ]
        assert ee.page_items(lines, 3) == [
            (BODY, "une ligne pleine de texte qui va"),
            (BODY, "jusqu'au bout."),
            (BLANK, ""),
            (BLANK, ""),
            (BODY, "Un alinéa rentré"),
            (NOTE, "( 1 ) une note"),
            (BLANK, ""),
        ]

    def test_an_empty_page(self) -> None:
        assert ee.page_items([], 0) == []
