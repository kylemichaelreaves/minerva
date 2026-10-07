"""`scripts/clean-boulainvilliers-texts.py` keeps the body text it used to drop (#739).

A sweep of every line each filter removed from the raw Histoire and Lettres
(batch 13m) measured:

* ``_is_column_edge_garbage`` — 87 of its 103 Lettres drops were body text
  (``de Coutance , de Blois , de Bayeux , Se``, the heading
  ``SI XI E' ME LETTRE*``). Removed.
* the run-on splitter — wrote ``Angle terre`` 89 times into the three files;
  22 of 40 sampled splits were wrong. Removed.
* the cleaner's own hyphen join at a line END — duplicates the compound-aware
  join that `corpus/ocr_reflow` does at ingest for both works that reach this
  cleaner line by line. Removed; the test below runs the reflow to show the
  word still comes out whole. The MID-line join (``Mai- fon``) is kept: the
  reflow does not do that one, and dropping it left 86 split words in the
  Essai where the old cleaner had 31 (batch 13m).
* the ``[A-Z]{2,5}[IVX]+`` running-head branch — ate ``Roi.`` (``Ro`` +
  ``i``) and ``Bailli.``. Narrowed to the shape every real Lettres head in
  the sweep has: a few letters, a dot, then an upper-case numeral
  (``Lett.V.``, ``Utt. IX.``).
* page-number, glyph-soup and f→s — measured mostly right, kept.

The fixtures are verbatim excerpts of the cleaner's real input — what the
downloader writes — under ``tests/fixtures/boulainvilliers/``. The f→s
pass needs ``pyspellchecker``, which is only in the optional ``ocr-clean``
extra (#740) and so absent from CI, so the tests stand in a word list for its
French dictionary; the words in it are
ones that dictionary has (and ``angleterre`` is one it lacks, which is how
the splitter produced ``Angle terre``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from minerva.authors import boulainvilliers_works
from minerva.corpus.ocr_reflow import OcrReflow, reflow
from minerva.corpus.split_paragraphic import is_heading_line

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "boulainvilliers"

_spec = importlib.util.spec_from_file_location(
    "clean_boulainvilliers_texts", ROOT / "scripts" / "clean-boulainvilliers-texts.py"
)
assert _spec is not None
assert _spec.loader is not None
bv = importlib.util.module_from_spec(_spec)
sys.modules["clean_boulainvilliers_texts"] = bv
_spec.loader.exec_module(bv)

# A stand-in for pyspellchecker's French dictionary: it knows both halves of
# `Angleterre` and not the whole, the long-s repairs of `puiffent` and
# `mauvaifes` and `confommation`, and `es` — which a fragment `ef-` would be
# mis-repaired to.
_WORDS = frozenset(
    {"angle", "terre", "puissent", "mauvaises", "consommation", "effectivement", "es", "maison"}
)


@pytest.fixture(autouse=True)
def _dictionary(monkeypatch):
    monkeypatch.setattr(bv, "_FRENCH_DICT", _WORDS)


def _clean(name: str) -> list[str]:
    return bv.clean_text((FIXTURES / name).read_text(encoding="utf-8")).split("\n")


class TestBodyLinesSurvive:
    def test_short_word_body_lines_are_not_column_edge_debris(self) -> None:
        lines = _clean("clean_lettres.txt")
        assert "de Coutance , de Blois , de Bayeux , Se" in lines
        # The Essai example from #739, as a line of its own.
        assert (
            bv.clean_text("il y avoit , au commencement de la")
            == "il y avoit , au commencement de la"
        )

    def test_angleterre_is_not_split(self) -> None:
        text = "\n".join(_clean("clean_lettres.txt"))
        assert "Angle terre" not in text
        assert "en Angleterre ," in text

    def test_roi_on_its_own_line_is_kept(self) -> None:
        lines = _clean("clean_histoire.txt")
        assert "Roi." in lines

    @pytest.mark.parametrize("line", ["Roi.", "Bailli.", "Roi", "Louis XI"])
    def test_words_ending_in_roman_letters_are_not_running_heads(self, line) -> None:
        assert not bv._RUNNING_HEADERS.match(line)

    def test_a_divided_word_is_left_for_the_reflow_to_join(self) -> None:
        text = bv.clean_text((FIXTURES / "clean_lettres.txt").read_text(encoding="utf-8"))
        # The cleaner no longer joins hyphens itself ...
        assert "en Al-\nlemagne" in text
        # ... and the ingest-time reflow, which both these works set, does.
        work = boulainvilliers_works.find_work("lettres_parlemens_fra.txt")
        assert work is not None
        assert work.ocr_reflow is not None
        reflowed = reflow(text, OcrReflow(titles=work.ocr_reflow), is_heading=is_heading_line)
        assert "en Angleterre , en Allemagne, en Pologne" in reflowed


class TestFurnitureStillGoes:
    def test_page_number_line_is_dropped(self) -> None:
        lines = _clean("clean_histoire.txt")
        assert "XV" not in lines
        assert "I quitter" in lines  # the catchword above it is not this filter's job

    def test_glyph_soup_line_is_dropped(self) -> None:
        text = "\n".join(_clean("clean_lettres.txt"))
        assert "Us divers / - r r -i" not in text

    @pytest.mark.parametrize(
        "line", ["Lett.V.", "LiTT. V,", "Utt. IX.", "Tr.IX.", "ITT. XIV.", "LETTRE II."]
    )
    def test_letter_running_heads_are_dropped(self, line) -> None:
        assert bv._RUNNING_HEADERS.match(line)

    def test_long_s_misread_is_repaired(self) -> None:
        text = "\n".join(_clean("clean_histoire.txt"))
        assert "puissent" in text
        assert "puiffent" not in text

    def test_long_s_repair_sees_a_divided_word_whole(self) -> None:
        """With the hyphen join gone, `mau-` / `vaifes` reaches the f→s
        pass as two fragments: `vaifes` is no word, so it stayed, and the
        reflow then wrote `mauvaifes`; `ef-` is the word `es`, so
        `ef-` / `fectivement` became `esfectivement`. The divided word is
        judged as one, and its hyphen and line break are left in place."""

        text = "\n".join(_clean("clean_histoire.txt"))
        assert "mau-\nvaises" in text
        assert "ef-\nfectivement" in text

    def test_a_divided_word_is_repaired_when_debris_stood_at_the_break(self) -> None:
        """`con- ^^^` / `fommation`: the caret debris is stripped after the
        first f→s pass, so the halves only meet then. Repaired in one run,
        not two — which is also what keeps the cleaner idempotent."""

        text = "\n".join(_clean("clean_histoire.txt"))
        assert "con-\nsommation" in text


@pytest.mark.parametrize("name", ["clean_lettres.txt", "clean_histoire.txt"])
def test_cleaning_twice_changes_nothing(name) -> None:
    once = bv.clean_text((FIXTURES / name).read_text(encoding="utf-8"))
    assert bv.clean_text(once) == once


def test_a_mid_line_split_word_is_joined_and_then_repaired_whole() -> None:
    """``Mai- fon`` is a word the PDF span join left split mid-line; the
    reflow only rejoins a hyphen at a line end, so the cleaner must. Joined
    first, the f→s pass then sees ``Maifon`` whole and repairs it."""

    assert bv.clean_text("de la Mai- fon du Roi") == "de la Maison du Roi"


def test_the_mid_line_join_leaves_a_capitalised_continuation_alone() -> None:
    assert bv.clean_text("le Comte- Duc") == "le Comte- Duc"
