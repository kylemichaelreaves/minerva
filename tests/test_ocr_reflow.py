"""Tests for reassembling paragraphs in OCR text dumps (#578).

The four fixtures under ``tests/fixtures/ocr_reflow/`` are verbatim
excerpts of the corpus files, each spanning one page break, so these run
where ``data/`` does not exist:

* ``renan_peuple_israel_vol5.txt`` — a paragraph interrupted by its own
  page's footnote and by the next page's running head;
* ``gobineau_essai_inegalite_vol4.txt`` — a running head the OCR read as
  ``DBA KACtB HUMAINES. 37!``. An excerpt of the file the corpus called
  "vol. 4" before #742, which was the corrupt Google scan of *Tome II*
  (re-sourced in batch 13m); kept because its OCR damage is the point;
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


class TestCarets:
    """`^` is OCR noise in the Gobineau and Renan scans, never text.

    Measured over the corpus files (batch 13m): in Renan about two thirds
    of the 3,095 carets stand where a superscript note call was printed
    (`Jérusalem^.`, `moyens ^ Un Juif`); in Gobineau most sit inside a
    word the OCR garbled (`diT^e`). None reads as a misprinted circumflex.
    A note call is not text, so the caret goes; what must not happen is a
    word fused to its neighbour, or a caret-only line turned into a blank
    that ends a paragraph.
    """

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            # A note call after a word, before its punctuation.
            ("le pays fort tempéré^. Sans doute", "le pays fort tempéré. Sans doute"),
            # A free-standing note call between two words: one space, not two.
            ("pour les esprits moyens ^ Un Juif", "pour les esprits moyens Un Juif"),
            ("épître dite aux Éphésiens^ Mais", "épître dite aux Éphésiens Mais"),
            # At the end of a line: nothing left behind.
            (
                "couvrirent toujours depuis la colline occidental e^",
                "couvrirent toujours depuis la colline occidental e",
            ),
            ("vie était racontée ^", "vie était racontée"),
            # Glyph noise inside a word.
            ("diT^e les tendances", "diTe les tendances"),
            # Between a word and a number, a space keeps them apart.
            ("Saint Paul^2 et", "Saint Paul 2 et"),
            ("Au 11^siècle", "Au 11 siècle"),
            # A run of carets is one caret.
            ("s'approchait^^^^^^", "s'approchait"),
            # The second half of a divided word is found again.
            ("Gomme exemple des chan-^", "Gomme exemple des chan-"),
        ],
    )
    def test_strips_the_character(self, line: str, expected: str) -> None:
        assert ocr_reflow.strip_carets(line) == expected

    def test_a_caret_standing_for_a_note_number_goes_too(self) -> None:
        """`^. Megillaih Taanith` is note 2 with its number read as `^`.
        Reflow does not take `^. ` for a note marker, so the line is glued
        into the paragraph above whether or not the caret stays; 12 of the
        13 such lines in Renan were, so keeping it only left carets in
        body text."""

        assert ocr_reflow.strip_carets("^. Megillaih Taanith") == ". Megillaih Taanith"

    def test_a_caret_only_line_is_removed_not_blanked(self) -> None:
        assert ocr_reflow.strip_carets("une phrase qui\n^^\ncontinue.") == (
            "une phrase qui\ncontinue."
        )
        assert reflow("une phrase qui\n^^\n\ncontinue.", OcrReflow(())) == (
            "une phrase qui continue."
        )

    def test_reflow_strips_carets(self) -> None:
        assert reflow("la colline occidental e^\nSimon fortifia.", OcrReflow(())) == (
            "la colline occidental e Simon fortifia."
        )

    def test_a_caret_after_a_full_stop_no_longer_hides_it(self) -> None:
        assert reflow("de cette inscription.^\n\nSimon fut.", OcrReflow(())) == (
            "de cette inscription.\n\nSimon fut."
        )

    @pytest.mark.parametrize(
        ("name", "spec"),
        [
            ("renan_peuple_israel_vol5.txt", RENAN),
            ("renan_peuple_israel_vol5_notes.txt", RENAN),
            ("gobineau_essai_inegalite_vol4.txt", GOBINEAU),
        ],
    )
    def test_no_caret_survives_in_the_real_excerpts(self, name: str, spec: OcrReflow) -> None:
        for para in _paragraphs(name, spec):
            assert "^" not in para

    def test_the_ecclesiaste_note_call_leaves_one_space(self) -> None:
        body = next(
            p for p in _paragraphs("renan_peuple_israel_vol5.txt", RENAN) if p.startswith("C'est")
        )
        assert "le Cohélet ou Ecclésiaste Nulle part ailleurs" in body


#: Renan's scans, with the note rules only his works ask for (#789, #792).
RENAN_NOTES = OcrReflow(RENAN.titles, notes=True)


class TestRenanRunningHeads:
    """Heads the OCR mangled past the rules above (#814)."""

    @pytest.mark.parametrize(
        "line",
        [
            # `«` is a misread folio digit, like the `»` already allowed.
            "AUTONOMIE JUIVE. «3",
            # The 10-letter title, under `_UNNUMBERED_MIN_LETTERS`, with a
            # folio the OCR read as punctuation and stray letters.
            "VIE DE JÉSUS. :{",
            "VIE DE JESUS. :,<)",
            "VIE DE JÉSUS. l",
            "VIE DE JÉSUS. 2G1",
            "VIE DR JIÎSUS. S.')",
            "VIE DE JÉSUS, '25;{",
            # A recto head has no title to match, so rests on its folio:
            # a digit among letters and marks still makes one.
            "AUTONOMIE JUIVE. T9",
            "LE PEUPLE JUIF SOUS LA DOMINATION ROMAINE. 3M",
            "[An 70J I/ANTECIIRIST. 5H",
            "[830 av. J.-C] LES DEUX ROYAUMES. 12]",
        ],
    )
    def test_heads(self, line: str) -> None:
        assert is_running_head(line, RENAN)

    @pytest.mark.parametrize(
        "line",
        [
            # Prose that ends on the title: lower case, so not a head.
            "la vie de Jésus. Il",
            # The title alone, its folio lost, stays text: a title page
            # prints it too, and nothing on the line says it is a head.
            "VIE DE JÉSUS.",
            # The trailing token is a word, not a folio.
            "VIE DE JÉSUS. Rome",
            # A recto folio with no digit left is not trusted: `Il` and
            # `St` are words as often as folios.
            "AUTONOMIE JUIVE. Il",
            "LE PEUPLE JUIF SOUS LA DOMINATION ROMAINE. 3St",
        ],
    )
    def test_not_heads(self, line: str) -> None:
        assert not is_running_head(line, RENAN)

    def test_the_short_title_head_no_longer_splits_its_paragraph(self) -> None:
        paras = _paragraphs("renan_vie_de_jesus.txt", RENAN)
        assert any("qui se développèrent dès une antiquité fort reculée" in p for p in paras)
        assert not any("VIE DE JÉSUS" in p for p in paras)

    def test_the_guillemet_folio_head_is_dropped(self) -> None:
        paras = _paragraphs("renan_peuple_israel_vol5_carry.txt", RENAN)
        assert not any("AUTONOMIE JUIVE" in p for p in paras)


class TestRenanNoteCarry:
    """A note that runs over a page break continues at the foot of the
    next page, after that page's body text (#789)."""

    def test_the_continuation_rejoins_its_note(self) -> None:
        paras = _paragraphs("renan_peuple_israel_vol5_carry.txt", RENAN_NOTES)
        (note,) = [p for p in paras if p.startswith("1. Les écrivains chrétiens")]
        assert "citations de Jude. de Barnabe et des autres Pères de l'Eglise." in note
        assert note.endswith("c'est la partie d seule qui doit nous occuper.")

    def test_the_body_continues_across_both_page_breaks(self) -> None:
        paras = _paragraphs("renan_peuple_israel_vol5_carry.txt", RENAN_NOTES)
        (body,) = [p for p in paras if p.startswith("Vers ce temps")]
        assert "pour donner aux hommes de bons conseils, à l'heure solennelle" in body
        assert "autres Pères" not in body

    def test_only_a_work_that_asks_for_it(self) -> None:
        paras = _paragraphs("renan_peuple_israel_vol5_carry.txt", RENAN)
        assert any("de bons autres Pères de l'Eglise" in p for p in paras)

    @staticmethod
    def _carry(after_head: list[str]) -> list[str]:
        """A note open at a page break, then the next page's lines."""

        text = "\n".join(
            [
                "Le corps du texte qui ne finit pas",
                "",
                "1. Une note qui passe à la page suivante et qui",
                "",
                "AUTONOMIE JUIVE. 27",
                "",
                *after_head,
            ]
        )
        return reflow(text, RENAN_NOTES).split("\n\n")

    def test_a_short_first_line_is_not_taken(self) -> None:
        """Under 55 characters the block is as likely the body's own."""

        paras = self._carry(["suite du corps.", "", "fin courte."])
        assert paras == [
            "Le corps du texte qui ne finit pas suite du corps.",
            "1. Une note qui passe à la page suivante et qui",
            "fin courte.",
        ]

    def test_a_capitalised_block_is_not_taken(self) -> None:
        line = "Un nouveau paragraphe commence ici avec une majuscule initiale."
        paras = self._carry(["suite du corps.", "", line])
        assert line in paras
        assert paras[1] == "1. Une note qui passe à la page suivante et qui"

    def test_the_continuation_follows_the_pages_last_body_paragraph(self) -> None:
        """`Ses sœurs se marièrent…` is the page's second body paragraph;
        note 4's `…qui au-` goes on after it, as `raient commencé…`."""

        paras = _paragraphs("renan_vie_de_jesus_notes.txt", RENAN_NOTES)
        (note,) = [p for p in paras if p.startswith("4. En effet")]
        assert "vrais frères de Jésus, qui auraient commencé par lui être hostiles" in note
        (body,) = [p for p in paras if p.startswith("Ses sœurs")]
        assert "raient commencé" not in body

    @pytest.mark.parametrize(
        "line",
        [
            # A note whose marker the OCR made a letter: a new note.
            "l.Le Maaka ouBcth-Maakaétaitla région du Jourdain avant son",
            "d. Hab., 11, 13. Cette belle phrase est répétée dans Jér., li,",
            # `Il` read as `11`, opening a line of quoted verse.
            "11 ne décidera pas selon ce que ses oreilles auront entendu;",
            # A number then a capital is a note marker.
            "1 Luc, XVII, 20. Comp. Tolmud de Babyl., Sanhédrin, 97 a.",
            # A quotation.
            "« Voilà que je viens vite ! Et avec moi j'apporte la récom-",
        ],
    )
    def test_blocks_that_do_not_continue_a_note(self, line: str) -> None:
        paras = self._carry(["suite du corps.", "", line])
        assert paras[1] == "1. Une note qui passe à la page suivante et qui"

    def test_a_number_that_continues_a_citation(self) -> None:
        line = "3 etsuiv., 6-16. Ce dernier écrit n'est pas de Paul; mais il peut"
        paras = self._carry(["suite du corps.", "", line])
        assert paras[1] == f"1. Une note qui passe à la page suivante et qui {line}"

    def test_nothing_is_taken_before_the_page_has_body(self) -> None:
        line = "continuation qui suit directement la tête de page, sans corps."
        paras = self._carry([line])
        assert paras[0] == f"Le corps du texte qui ne finit pas {line}"

    def test_a_new_note_ends_the_carry(self) -> None:
        line = "et un bloc assez long pour passer le seuil des cinquante-cinq."
        paras = self._carry(["suite du corps.", "", "2. Autre note.", "", line])
        assert paras[1:] == [
            "1. Une note qui passe à la page suivante et qui",
            "2. Autre note.",
            line,
        ]

    def test_the_carry_rejoins_a_word_divided_at_the_page_foot(self) -> None:
        text = "\n".join(
            [
                "Le corps du texte qui ne finit pas",
                "",
                "1. Une note dont le dernier mot est considé-",
                "",
                "AUTONOMIE JUIVE. 27",
                "",
                "suite du corps.",
                "",
                "rables, et la note continue ici jusqu'à son point final.",
            ]
        )
        paras = reflow(text, RENAN_NOTES).split("\n\n")
        assert paras[1] == (
            "1. Une note dont le dernier mot est considérables, "
            "et la note continue ici jusqu'à son point final."
        )


class TestRenanMangledNotes:
    """Notes whose number the OCR misread are held aside like any other,
    and before the heading test that took `I. ` for a numeral (#792)."""

    def test_a_roman_one_note_is_a_note_not_a_heading(self) -> None:
        paras = _paragraphs("renan_vie_de_jesus_notes.txt", RENAN_NOTES)
        (body,) = [p for p in paras if p.startswith("Ses sœurs se marièrent")]
        assert "Acl." not in body
        assert any(p.startswith("I. Acl., I, 14.") for p in paras)

    def test_a_caret_note_is_held_aside(self) -> None:
        paras = _paragraphs("renan_antechrist_caret_note.txt", RENAN_NOTES)
        (body,) = [p for p in paras if "Pomponia" in p and "Graecina portait" in p]
        assert "Tac, Ann." not in body
        assert ". Tac, Ann., XIV, 42 elsuiv." in paras

    @pytest.mark.parametrize(
        "line",
        [
            "I. Acl., I, 14.",
            "I. Voir lo passage précilô de Papias.",
            "t. Ce second nom est la traduction grecque du premier.",
            "o. Col., I, 1.",
            "\\. Acl., m, 21.",
            "î. Voir ci-dessus, p. 400.",
            "l. Sur la conception du nasi cVIsraël, à cette époque, voir",
            ".3. Jean, XII. 20; Ad., mm. 27.",
            ". Tac, Ann., XIV, 42 elsuiv.",
            "i. II Macch., XV, 12 et suIt.",
            "S. I Macch., xiv, 25 etsuiv.",
        ],
    )
    def test_mangled_openers(self, line: str) -> None:
        assert ocr_reflow.opens_mangled_note(line)

    @pytest.mark.parametrize(
        "line",
        [
            # Table-of-contents entries: a dash, or a title and its folio.
            "I. — Arrivée des Sémites en Syrie. Chananeeris. . i",
            "I. Paul captif à Rome 1",
            "I. Place de Jésus dans l'histoire du monde *",
            # A heading in capitals.
            "I. LES ORIGINES",
            # A caret-stripped full stop run into a word is a misread letter.
            ".lean est venu, ne mangeant ni ne buvant, et vous",
            "A. côté du nabi",
            "",
        ],
    )
    def test_not_mangled_openers(self, line: str) -> None:
        assert not ocr_reflow.opens_mangled_note(line)

    def test_only_after_a_blank(self) -> None:
        text = "Une phrase qui ne finit pas\nt. continue ici.\n"
        assert reflow(text, RENAN_NOTES) == "Une phrase qui ne finit pas t. continue ici."

    def test_only_a_work_that_asks_for_it(self) -> None:
        paras = _paragraphs("renan_antechrist_caret_note.txt", RENAN)
        assert any("Pomponia . Tac, Ann." in p for p in paras)


class TestRenanPipeline:
    def test_every_renan_work_asks_for_the_note_rules(self) -> None:
        assert all(w.ocr_reflow_notes for w in renan_works.WORKS)

    def test_no_other_work_does(self) -> None:
        assert not any(
            w.ocr_reflow_notes for w in (*gobineau_works.WORKS, *boulainvilliers_works.WORKS)
        )

    def test_a_roman_one_note_keeps_its_text_and_is_no_label(self) -> None:
        """`I. Acl., I, 14.` was a section label, its text in no chunk."""

        from minerva.corpus.pipeline import parse_file

        work = renan_works.WORKS[0]
        chunks = list(parse_file(FIXTURES / "renan_vie_de_jesus_notes.txt", work))
        assert not any("Acl." in (c.section or "") for c in chunks)
        (note,) = [c for c in chunks if c.text.startswith("I. Acl., I, 14.")]
        assert note.block_type == "remark"
