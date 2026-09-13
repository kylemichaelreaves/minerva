"""Tests for recovering lost inter-word spaces from PDF glyph geometry (#561).

Two lines of the Inwood *Phenomenology*'s editor's introduction carry no
space glyphs at all, so they extract as
``IthasbeensaidthatthedifferencebetweenNietzscheandHegelisthatwecanunderstand``.
No PyMuPDF extraction mode recovers them — `get_text("text")` and
`get_text("words")` agree, because the spaces are not in the text layer.

The character *positions* still are. Within a word the glyph gap is
about −0.14pt; between words it is +1.3 to +1.4pt. Cutting at the large
gaps restores the words exactly, with nothing guessed and no dictionary
consulted — which is what separates this from the "space-insertion pass
over already-damaged text" #561 rightly warns against.

`tests/fixtures/pdf_spans/hegel_char_geometry.json` holds real
per-character boxes lifted from the two PDFs, so these run in CI where
`data/` does not exist.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minerva.corpus_extract import _split_on_char_gaps

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "pdf_spans"
    / "hegel_char_geometry.json"
)


def _chars(key: str) -> list[tuple[str, float, float]]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return [(c, x0, x1) for c, x0, x1 in data[key]["chars"]]


class TestRealGeometry:
    def test_the_issues_headline_example_is_restored_exactly(self) -> None:
        got = _split_on_char_gaps(_chars("damaged_runon"))
        assert got == (
            "It has been said that the difference between Nietzsche and "
            "Hegel is that we can understand"
        )

    def test_a_healthy_line_is_left_alone(self) -> None:
        """A span that already has its spaces must come back unchanged —
        not re-split on whatever its widest gap happens to be."""

        assert _split_on_char_gaps(_chars("healthy_spaced")) is None

    def test_a_genuine_german_compound_is_not_split(self) -> None:
        """`Transzendentalphilosophie` is one word, appearing three times
        in the Science of Logic's bibliography. #561 predicted exactly
        this false positive for a length-based detector; a geometric one
        is immune, because the glyph gaps really are uniform."""

        assert _split_on_char_gaps(_chars("german_single_word")) is None


def _synthetic(text: str, *, gap: float = -0.14, word_gap: float = 1.4) -> list:
    """Lay `text` out left to right, 5pt per glyph, using `gap` between
    letters and `word_gap` where a space appears. The space itself is
    not emitted — that is the defect being modelled."""

    out: list[tuple[str, float, float]] = []
    x = 0.0
    for i, ch in enumerate(text):
        if ch == " ":
            x += word_gap
            continue
        out.append((ch, x, x + 5.0))
        x += 5.0
        if i + 1 < len(text) and text[i + 1] != " ":
            x += gap
    return out


class TestSyntheticGeometry:
    def test_round_trip(self) -> None:
        assert _split_on_char_gaps(_synthetic("alpha beta gamma")) == (
            "alpha beta gamma"
        )

    def test_uniform_gaps_are_one_word(self) -> None:
        assert _split_on_char_gaps(_synthetic("indivisible")) is None

    def test_too_few_characters_to_judge(self) -> None:
        assert _split_on_char_gaps(_synthetic("ab cd")) is None

    def test_empty_input(self) -> None:
        assert _split_on_char_gaps([]) is None

    def test_a_span_that_already_contains_a_space_is_declined(self) -> None:
        chars = [("a", 0.0, 5.0), (" ", 5.0, 7.0), ("b", 7.0, 12.0)]
        assert _split_on_char_gaps(chars * 5) is None

    @pytest.mark.parametrize("word_gap", [1.0, 1.4, 2.5, 4.0])
    def test_various_word_gap_widths(self, word_gap: float) -> None:
        got = _split_on_char_gaps(
            _synthetic("recovering the spacing", word_gap=word_gap)
        )
        assert got == "recovering the spacing"

    def test_a_marginally_wider_gap_is_not_a_word_break(self) -> None:
        """Kerning varies within a word — `AV`, `To`, `Wa` sit tighter or
        looser than average. A gap must stand clearly out, not merely be
        the largest, or every span becomes two words."""

        chars = _synthetic("kerning")
        # Widen one interior gap slightly, as a kern pair would.
        c, x0, x1 = chars[3]
        chars[3] = (c, x0 + 0.25, x1 + 0.25)
        assert _split_on_char_gaps(chars) is None

    def test_zero_width_glyphs_do_not_crash_it(self) -> None:
        chars = [("x", 0.0, 0.0)] * 20
        assert _split_on_char_gaps(chars) is None


# ════════════════════════════════════════════════════════════════════
# Page level
# ════════════════════════════════════════════════════════════════════
#
# `_page_space_repairs` and `_extract_pdf_page_lines` take a PyMuPDF
# page, and the PDFs they read live under `data/`, which no CI checkout
# has. A stub page carrying the two calls they actually make —
# `get_text("rawdict")` and `get_text("words")` — exercises both without
# one.


class _StubPage:
    """The two `get_text` modes the extractor uses, and nothing else."""

    def __init__(self, spans: list[list[tuple[str, float, float]]], words):
        self._spans = spans
        self._words = words

    def get_text(self, mode: str):
        if mode == "rawdict":
            return {
                "blocks": [
                    {
                        "lines": [
                            {
                                "spans": [
                                    {
                                        "chars": [
                                            {"c": c, "bbox": (x0, 0.0, x1, 10.0)}
                                            for c, x0, x1 in span
                                        ]
                                    }
                                    for span in self._spans
                                ]
                            }
                        ]
                    }
                ]
            }
        if mode == "words":
            return self._words
        raise AssertionError(f"unexpected get_text mode {mode!r}")


class TestPageSpaceRepairs:
    def test_a_damaged_span_becomes_a_repair_entry(self) -> None:
        from minerva.corpus_extract import _page_space_repairs

        page = _StubPage([_synthetic("alpha beta gamma")], [])
        assert _page_space_repairs(page) == {
            "alphabetagamma": "alpha beta gamma"
        }

    def test_healthy_spans_produce_no_entries(self) -> None:
        from minerva.corpus_extract import _page_space_repairs

        page = _StubPage(
            [_synthetic("indivisible"), _chars("german_single_word")], []
        )
        assert _page_space_repairs(page) == {}

    def test_a_page_with_no_blocks(self) -> None:
        from minerva.corpus_extract import _page_space_repairs

        class _Empty:
            def get_text(self, mode):
                return {}

        assert _page_space_repairs(_Empty()) == {}


class TestExtractPdfPageLines:
    def _words(self, texts: list[str]) -> list[tuple]:
        # (x0, y0, x1, y1, text, block_no, line_no, word_no)
        out = []
        x = 0.0
        for i, t in enumerate(texts):
            out.append((x, 0.0, x + 10.0, 10.0, t, 0, 0, i))
            x += 12.0
        return out

    def test_a_run_on_in_the_word_stream_is_repaired(self) -> None:
        from minerva.corpus_extract import _extract_pdf_page_lines

        page = _StubPage(
            [_synthetic("alpha beta gamma")],
            self._words(["prefix", "alphabetagamma", "suffix"]),
        )
        assert _extract_pdf_page_lines(page) == [
            "prefix alpha beta gamma suffix"
        ]

    def test_untouched_when_nothing_is_damaged(self) -> None:
        from minerva.corpus_extract import _extract_pdf_page_lines

        page = _StubPage(
            [_synthetic("indivisible")],
            self._words(["ordinary", "words", "here"]),
        )
        assert _extract_pdf_page_lines(page) == ["ordinary words here"]

    def test_a_page_with_no_words_yields_nothing(self) -> None:
        from minerva.corpus_extract import _extract_pdf_page_lines

        assert _extract_pdf_page_lines(_StubPage([], [])) == []

    def test_longest_repair_is_applied_first(self) -> None:
        """A short run-on nested inside a longer one must not rewrite the
        longer one out from under itself."""

        from minerva.corpus_extract import _extract_pdf_page_lines

        page = _StubPage(
            [_synthetic("alpha beta"), _synthetic("alpha beta gamma")],
            self._words(["alphabetagamma"]),
        )
        assert _extract_pdf_page_lines(page) == ["alpha beta gamma"]


# ════════════════════════════════════════════════════════════════════
# The false positives the corpus-wide sweep found
# ════════════════════════════════════════════════════════════════════
#
# Every case below fired under the first version of this rule, which
# only asked for a gap above the median. Run over all 15 PDFs that
# version produced 296 repairs and was wrong nearly every time. These
# pin the four families it had to learn, so a later loosening fails
# here rather than in the corpus.


class TestFalsePositiveFamilies:
    def test_spacing_diacritic_does_not_fake_a_word_break(self) -> None:
        """`¨` and `´` are zero-advance glyphs sitting over the previous
        letter, and the box arithmetic around them opens one wide gap.
        This was 164 of the original 296 — `Barthe´lemy`,
        `Zur¨uckf¨uhrung`, `willku¨rlich`, `Systementw¨urfe`."""

        chars = _synthetic("Bartheôlemy")
        # Give the mark a zero-width box displaced like a real accent.
        chars[6] = ("´", chars[6][1] + 0.9, chars[6][1] + 0.9)
        assert _split_on_char_gaps(chars) is None

    def test_letter_spaced_heading_is_left_to_the_kerning_fuser(self) -> None:
        """A banner has *uniform* wide gaps, so it has a widest gap
        without having a bimodal one — but `TRANSLATIONS` has one tight
        pair (`AT`) and so read as bimodal anyway, coming out
        `T R A N S L AT I O N S`. `_fuse_kerned_words` exists to close
        these, and this pass must not fight it."""

        chars = _synthetic("T R A N S L A T I O N S")
        assert _split_on_char_gaps(chars) is None

    def test_a_lowercase_run_with_wide_gaps_is_still_repaired(self) -> None:
        """The uppercase guard must not swallow ordinary prose."""

        assert _split_on_char_gaps(_synthetic("it is only self")) == (
            "it is only self"
        )

    def test_private_use_area_runs_are_declined(self) -> None:
        """The Inwood PDF encodes some runs in PUA glyphs carrying no
        usable character identity; splitting them tidies nothing."""

        chars = _synthetic("thethisandmeaning")
        chars = [(chr(0xF700 + i), x0, x1) for i, (_, x0, x1) in enumerate(chars)]
        assert _split_on_char_gaps(chars) is None

    def test_punctuation_spacing_is_not_a_lost_word_space(self) -> None:
        """`thing-in-itself);` → `thing-in-itself );` adds a space that
        never existed. A lost word space sits between two letters."""

        chars = _synthetic("thing-in-itself );")
        assert _split_on_char_gaps(chars) is None

    def test_an_interior_lone_letter_means_the_cut_fell_inside_a_word(
        self,
    ) -> None:
        """`[Gedankenbes` came out `[ G edankenbes` — a drop cap."""

        assert _split_on_char_gaps(_synthetic("[ G edankenbestimmung")) is None

    def test_a_lone_letter_at_the_edge_is_legitimate(self) -> None:
        """A span often begins mid-word: the damaged run after
        `Nietzsche’` opens with a bare `s`, and that is real."""

        assert _split_on_char_gaps(_synthetic("s individual sentences")) == (
            "s individual sentences"
        )

    def test_a_vowelless_alphabetic_part_means_a_cut_inside_a_word(self) -> None:
        assert _split_on_char_gaps(_synthetic("strngth ungliches")) is None

    def test_vowelless_abbreviations_are_exempt(self) -> None:
        """The vowel test applies to wholly alphabetic parts only. A
        first version tested any part containing a letter and threw away
        three correct repairs on `cf.`, `W.` and `L.`"""

        assert _split_on_char_gaps(_synthetic("Essays on G. W. F. Hegel")) == (
            "Essays on G. W. F. Hegel"
        )

    def test_uniform_wide_gaps_have_no_valley(self) -> None:
        """The valley test is what distinguishes 'has a widest gap' from
        'is bimodal'. With every gap equal there is no valley at all."""

        chars = _synthetic("abcdefghijklmno", gap=1.4)
        assert _split_on_char_gaps(chars) is None

    def test_partial_damage_in_one_span_is_declined(self) -> None:
        """A known, deliberate limitation. A span can carry some of its
        spaces and not others, and this declines the whole span, leaving
        about 13 genuine runs unrepaired.

        Judging each space-delimited segment separately was tried and is
        much worse — corpus-wide it takes 23 repairs to 284, and the
        additions split ordinary words (`tr ansmitted`, `Hoff meister`,
        `j uxtapositions`). An eleven-letter word has ten gaps, one kern
        pair looks bimodal across so few, and the neighbouring spaces
        that reveal the span as healthy are what segmenting discards.
        """

        chars = [
            *_synthetic("Itwillnotbewithoutinterest"),
            (" ", 200.0, 202.0),
            *_synthetic("toexaminethisconstruction"),
        ]
        assert _split_on_char_gaps(chars) is None
