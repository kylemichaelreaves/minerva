"""Tests for reassembling paragraphs in OCR text dumps (#578).

The four fixtures under ``tests/fixtures/ocr_reflow/`` are verbatim
excerpts of the corpus files, each spanning one page break, so these run
where ``data/`` does not exist:

* ``renan_peuple_israel_vol5.txt`` — a paragraph interrupted by its own
  page's footnote and by the next page's running head;
* ``gobineau_essai_inegalite_vol4.txt`` — a running head the OCR read as
  ``DBA KACtB HUMAINES. 37!``;
* ``boulainvilliers_histoire.txt`` — a signature mark and catchword
  (``Y y une``) and a head whose page number came out ``1 3 o``;
* ``boulainvilliers_lettres.txt`` — every line its own blank-separated
  "paragraph", which is what gave that file a 39-character median chunk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minerva.authors import boulainvilliers_works, gobineau_works, renan_works
from minerva.corpus import ocr_reflow
from minerva.corpus.ocr_reflow import (
    OcrReflow,
    dropped_lines,
    is_running_head,
    is_signature,
    reflow,
)
from minerva.corpus.split_paragraphic import is_heading_line

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ocr_reflow"

RENAN = OcrReflow(renan_works.WORKS[0].ocr_reflow)
GOBINEAU = OcrReflow(gobineau_works.WORKS[0].ocr_reflow)
BOULAINVILLIERS = OcrReflow(boulainvilliers_works.WORKS[0].ocr_reflow)


def _paragraphs(name: str, spec: OcrReflow) -> list[str]:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return reflow(text, spec, is_heading_line).split("\n\n")


class TestRealPageBreaks:
    def test_a_paragraph_continues_across_its_footnote_and_the_next_head(self) -> None:
        paras = _paragraphs("renan_peuple_israel_vol5.txt", RENAN)
        body = next(p for p in paras if p.startswith("C'est à peu près"))
        # The page ends mid-sentence on `fièvre;` and the next page's text
        # picks it up — with the note and the head that stood between them
        # gone from the middle of it.
        assert "Israël a la fièvre; il enfante le christianisme" in body
        assert body.endswith("qui existent dans aucune langue.")
        assert "HISTOIRE DU PEUPLE" not in body
        assert "La langue du Cohélet" not in body

    def test_the_interrupting_footnote_is_kept_after_the_paragraph(self) -> None:
        paras = _paragraphs("renan_peuple_israel_vol5.txt", RENAN)
        body = next(i for i, p in enumerate(paras) if p.startswith("C'est à peu près"))
        assert paras[body + 1].startswith("1. La langue du Cohélet")

    def test_the_chapter_heading_stays_a_paragraph_of_its_own(self) -> None:
        paras = _paragraphs("renan_peuple_israel_vol5.txt", RENAN)
        assert "CHAPITRE XV" in paras

    def test_a_mangled_head_is_still_a_head(self) -> None:
        paras = _paragraphs("gobineau_essai_inegalite_vol4.txt", GOBINEAU)
        joined = "\n".join(paras)
        assert "KACtB" not in joined
        assert "parunesoptede i le mal do sa progéniture" in joined

    def test_signature_catchword_and_head_are_all_stepped_over(self) -> None:
        text = (FIXTURES / "boulainvilliers_histoire.txt").read_text(encoding="utf-8")
        kinds = {kind: line for _, kind, line in dropped_lines(text, BOULAINVILLIERS)}
        assert kinds == {
            ocr_reflow.CATCHWORD: "Y y une",
            ocr_reflow.HEAD: "1 3 o Mémoires Historiques.",
        }
        (para,) = _paragraphs("boulainvilliers_histoire.txt", BOULAINVILLIERS)
        assert "promtement refait Lothaire. une armée" in para

    def test_line_level_blanks_are_rejoined(self) -> None:
        paras = _paragraphs("boulainvilliers_lettres.txt", BOULAINVILLIERS)
        assert len(paras) == 1
        assert "Si toutefois les n Seigneurs confulrans cette" in paras[0]
        # `Ci` is the signature and `58 Lettres sur les Anciens` the head.
        assert " Ci " not in paras[0] and "Lettres sur les Anciens" not in paras[0]

    def test_a_star_before_a_quoted_line_is_not_a_note(self) -> None:
        """The *Lettres* OCR reads a quoted line's guillemets as `*`."""

        paras = _paragraphs("boulainvilliers_lettres.txt", BOULAINVILLIERS)
        assert "Il ne * ' >ï Faut pas oublier" in paras[0]


class TestRunningHeads:
    @pytest.mark.parametrize(
        "line",
        [
            "158 HISTOIRE DU PEUPLE D'ISRAËL.",
            "AUTONOMIE JUIVE. 27",  # recto: the book's title, matched by shape
            "[An 61] L'ANTECHRIST. 3",
            "2 ORIGINES DU CHRISTIANISME. [Aq GIJ",
            "Mémoires Historiques, 45-",
            "51 LlTTRES SUR LES AhCIîNS:",
            "Parle mens de France.",
        ],
    )
    def test_heads(self, line: str) -> None:
        spec = OcrReflow((*RENAN.titles, *BOULAINVILLIERS.titles))
        assert is_running_head(line, spec)

    @pytest.mark.parametrize(
        "line",
        [
            # Footnote continuation lines are capitals and numbers too; the
            # first sweep dropped five of these from L'Antéchrist.
            "XXXIII, m (16); XXXVI, xv (24).",
            "B. J., VI, VI, 2.",
            "1. Jos., Ant., XVIII, I, 3.",
            # A prose line that ends a sentence on a short title.
            "Roi de France.",
            "de France.",
            # ...or on part of a long one, or runs past one.
            "du christianisme.",
            "l'histoire d'Israël.",
            "plus belle des races humaines (i).",
            # A chapter heading whose numeral came out as digits.
            "CHAPITRE ÎI1",
            # Too short to be sure of, too long to be a head.
            "LIVRE",
            "27",  # a page number alone is left to the other filters
            "AUTONOMIE JUIVE, et ce qu'il en advint dans les siècles suivants. 27",
            "",
        ],
    )
    def test_not_heads(self, line: str) -> None:
        spec = OcrReflow((*RENAN.titles, *BOULAINVILLIERS.titles, "de France"))
        assert not is_running_head(line, spec)

    def test_a_roman_folio_counts_only_beside_a_title(self) -> None:
        spec = OcrReflow(RENAN.titles)
        assert is_running_head("XXII L'ANTECHRIST.", spec)
        assert not is_running_head("CHAPITRE XIII.", spec)

    def test_the_second_half_of_a_divided_word_is_text(self) -> None:
        """`établisse-` / `ment du christianisme.` ends a sentence on a
        title; dropping it as a head also broke the word it completes."""

        text = "un assez long établisse-\nment du christianisme.\n\nSuite."
        assert dropped_lines(text, RENAN) == []
        assert reflow(text, RENAN).startswith("un assez long établissement du christianisme.")

    def test_a_head_after_a_divided_word_is_still_a_head(self) -> None:
        """The folio the OCR reads lower-case (`i36`, `m`) is what makes a
        head look like the second half of the word before it."""

        text = "de l'huma-\n\ni36 DE l'inégalité\n\nnité entière.\n\nm Lettres sur lés Anciens\n"
        spec = OcrReflow((*GOBINEAU.titles, *BOULAINVILLIERS.titles))
        assert [k for _, k, _ in dropped_lines(text, spec)] == [ocr_reflow.HEAD, ocr_reflow.HEAD]

    def test_an_untitled_head_needs_mostly_capitals(self) -> None:
        assert not is_running_head("Chapitre premier de la suite. 27", OcrReflow(()))


class TestSignatures:
    @pytest.mark.parametrize("line", ["C 4", "V 17", "Ci", "A ij", "Y y", "O o", "B2"])
    def test_signatures(self, line: str) -> None:
        assert is_signature(line)

    @pytest.mark.parametrize("line", ["Roi", "Lui", "Moi", "Le", "Il", "A", "Ici", "Yo"])
    def test_words_are_not_signatures(self, line: str) -> None:
        assert not is_signature(line)


class TestCatchwords:
    def test_needs_a_head_between_it_and_its_twin(self) -> None:
        """A short line whose word begins the next line is only a
        catchword across a page break."""

        text = "le prince\n\nciers\n\nciers de l'Armée."
        assert dropped_lines(text, OcrReflow(())) == []

    def test_is_dropped_across_a_head(self) -> None:
        text = "des offi-\n\nciers\n\n68 Mémoires Historiques.\n\nciers de l'Armée."
        assert [k for _, k, _ in dropped_lines(text, BOULAINVILLIERS)] == [
            ocr_reflow.CATCHWORD,
            ocr_reflow.HEAD,
        ]
        assert reflow(text, BOULAINVILLIERS) == "des officiers de l'Armée."

    def test_must_repeat_the_next_word(self) -> None:
        text = "des offi-\n\nciers\n\n68 Mémoires Historiques.\n\nsoldats de l'Armée."
        assert [k for _, k, _ in dropped_lines(text, BOULAINVILLIERS)] == [ocr_reflow.HEAD]

    def test_a_long_line_is_never_a_catchword(self) -> None:
        text = "ceci est une ligne longue\n\n68 Mémoires Historiques.\n\nligne"
        assert [k for _, k, _ in dropped_lines(text, BOULAINVILLIERS)] == [ocr_reflow.HEAD]

    def test_its_prefix_must_be_signature_tokens(self) -> None:
        text = "la bonne une\n\n68 Mémoires Historiques.\n\nune armée."
        assert [k for _, k, _ in dropped_lines(text, BOULAINVILLIERS)] == [ocr_reflow.HEAD]

    def test_with_nothing_after_it(self) -> None:
        assert dropped_lines("fin\n\n68 Mémoires Historiques.", BOULAINVILLIERS)[-1][1] == (
            ocr_reflow.HEAD
        )


class TestAssembly:
    def test_a_closed_sentence_ends_the_paragraph(self) -> None:
        assert reflow("Une phrase.\n\nUne autre.", OcrReflow(())) == "Une phrase.\n\nUne autre."

    def test_an_open_sentence_continues_across_the_blank(self) -> None:
        assert reflow("une phrase qui\n\ncontinue.", OcrReflow(())) == "une phrase qui continue."

    def test_a_divided_word_is_rejoined(self) -> None:
        assert reflow("la décré-\npitude.", OcrReflow(())) == "la décrépitude."

    def test_a_compound_the_text_hyphenates_keeps_its_hyphen(self) -> None:
        """`quelques-` / `uns` at a line end is a compound, and the text
        says so by printing `quelques-uns` elsewhere mid-line."""

        text = "quelques-uns le disent.\n\nMais quelques-\nuns le nient."
        assert reflow(text, OcrReflow(())).endswith("Mais quelques-uns le nient.")

    def test_a_divided_word_seen_whole_loses_its_hyphen(self) -> None:
        text = "la décrépitude.\n\nSa décré-\npitude."
        assert reflow(text, OcrReflow(())).endswith("Sa décrépitude.")

    def test_a_hyphen_before_a_capital_is_kept(self) -> None:
        assert reflow("Jean-\nBaptiste.", OcrReflow(())) == "Jean- Baptiste."

    def test_a_closing_guillemet_closes_the_sentence(self) -> None:
        assert reflow("il dit : « non. »\n\nPuis.", OcrReflow(())) == "il dit : « non. »\n\nPuis."

    def test_a_heading_closes_an_open_paragraph(self) -> None:
        out = reflow("une phrase qui\n\nCHAPITRE XV\n\ncontinue.", OcrReflow(()), is_heading_line)
        assert out == "une phrase qui\n\nCHAPITRE XV\n\ncontinue."

    def test_a_note_with_no_open_paragraph_is_emitted_in_place(self) -> None:
        out = reflow("Fin.\n\n1. Une note\nqui continue.\n\nSuite.", OcrReflow(()))
        assert out == "Fin.\n\n1. Une note qui continue.\n\nSuite."

    def test_a_note_at_the_end_of_the_text(self) -> None:
        assert reflow("une phrase\n\n(1) Note", OcrReflow(())) == "une phrase\n\n(1) Note"

    def test_an_overlong_open_paragraph_is_closed_at_the_next_blank(self) -> None:
        """OCR that loses its full stops must not merge a whole chapter."""

        line = "mot " * 400
        out = reflow(f"{line}\n{line}\n\nsuite", OcrReflow(()))
        assert out.count("\n\n") == 1

    def test_blank_runs_and_furniture_only(self) -> None:
        assert reflow("\n\n\n", OcrReflow(())) == ""
        assert reflow("C 4\n\n", OcrReflow(())) == ""


class TestAssembleWithKnownNotes:
    """`assemble` takes the note area from a caller that can see the page."""

    def test_a_marker_opens_a_note_and_a_plain_line_continues_it(self) -> None:
        items = [
            (ocr_reflow.BODY, "une phrase qui"),
            (ocr_reflow.NOTE, "(1) Première note"),
            (ocr_reflow.NOTE, "qui continue."),
            (ocr_reflow.NOTE, "(2) Seconde note."),
            (ocr_reflow.BLANK, ""),
            (ocr_reflow.BODY, "continue ici."),
        ]
        assert ocr_reflow.assemble(items) == [
            "une phrase qui continue ici.",
            "(1) Première note qui continue.",
            "(2) Seconde note.",
        ]

    def test_a_note_carried_over_from_the_last_page_starts_unmarked(self) -> None:
        items = [(ocr_reflow.NOTE, "suite de la note."), (ocr_reflow.BLANK, "")]
        assert ocr_reflow.assemble(items) == ["suite de la note."]


class TestPipeline:
    def test_parse_file_reflows_a_work_that_asks_for_it(self, tmp_path: Path) -> None:
        import dataclasses

        from minerva.corpus.pipeline import parse_file

        src = tmp_path / "x.txt"
        src.write_text(
            "Première phrase qui\n\n158 HISTOIRE DU PEUPLE D'ISRAËL.\n\ncontinue ici.\n",
            encoding="utf-8",
        )
        work = renan_works.WORKS[0]
        (chunk,) = list(parse_file(src, work))
        assert chunk.text == "Première phrase qui continue ici."
        plain = list(parse_file(src, dataclasses.replace(work, ocr_reflow=None)))
        assert [c.text for c in plain] == [
            "Première phrase qui",
            "158 HISTOIRE DU PEUPLE D'ISRAËL.",
            "continue ici.",
        ]
