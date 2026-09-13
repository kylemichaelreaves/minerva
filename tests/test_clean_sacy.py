"""Tests for the Sacy OCR repair (#557).

Ten verses of the French Sacy OSIS file carry the same capital-I
misread, in two shapes that need two different detectors — which is the
part worth keeping, because a second edition with this OCR profile
would need both tests and not the one that happened to fire.

Shape A (1 verse) — the verse number ate the word. `Il` was read as
`11` and appended to the verse number, so `Lam.3.7` became `Lam.3.711`
and its text lost its subject. Lamentations 3:7 is simply absent from
the edition as a result. Caught by a verse-number range check.

Shape B (9 verses) — the number is fine and the text kept the damage:
`Il`/`Ils` read as `ll`/`lls`, lowercase L. Invisible to the range
check. Caught by a literal match, which is unambiguous because French
has no word `ll` or `lls`.

Two detectors that look plausible and are not, recorded on the issue so
nobody re-walks them: osisIDs ending in three-or-more digits are almost
all Psalm 118, which genuinely has 176 verses here; and "verse number
ends in 11 and the text starts lowercase" returns 48 hits of which 47
are ordinary Sacy continuations.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "clean_sacy_fra", REPO / "scripts" / "clean-sacy-fra.py"
)
assert _spec is not None
assert _spec.loader is not None
cs = importlib.util.module_from_spec(_spec)
sys.modules["clean_sacy_fra"] = cs
_spec.loader.exec_module(cs)


class TestShapeA:
    """The verse number absorbed the verse's own first word."""

    def test_lam_3_711_is_repaired_in_both_fields(self) -> None:
        line = (
            "<verse osisID='Lam.3.711'>a élevé des forts contre moi pour "
            "m'empêcher de sortir ; il a appesanti mes fers.</verse>"
        )
        out, n = cs.repair_text(line)
        assert n == 1
        # Both halves of the same event have to be undone: the id and
        # the missing subject.
        assert "osisID='Lam.3.7'" in out
        assert ">Il a élevé des forts" in out
        assert "711" not in out

    def test_a_legitimate_high_verse_number_is_left_alone(self) -> None:
        """Psalm 118 really does have 176 verses in this versification.
        A rule keyed on "long verse number" rather than "out of range"
        would rewrite scripture."""

        line = "<verse osisID='Ps.118.176'>Je me suis égaré comme une brebis</verse>"
        out, n = cs.repair_text(line)
        assert n == 0
        assert out == line

    @pytest.mark.parametrize("verse", ["Matt.2.11", "Luke.3.11", "John.15.11"])
    def test_verse_numbers_ending_in_11_are_not_suspects(self, verse: str) -> None:
        """The signature the issue first proposed — number ends in `11`,
        text starts lowercase — returns 48 hits of which 47 are ordinary
        continuations that begin lowercase by style."""

        line = f"<verse osisID='{verse}'>et il leur dit encore ceci</verse>"
        out, n = cs.repair_text(line)
        assert n == 0
        assert out == line


class TestShapeB:
    """The number is fine; the text kept the damage."""

    @pytest.mark.parametrize(
        "damaged,fixed",
        [
            ("ll lui a mis dans l'esprit", "Il lui a mis dans l'esprit"),
            ("ll fit le mal devant le Seigneur", "Il fit le mal devant le Seigneur"),
            ("lls demeurèrent avec lui", "Ils demeurèrent avec lui"),
            ("lls ont erré dans la solitude", "Ils ont erré dans la solitude"),
        ],
    )
    def test_leading_ll_becomes_il(self, damaged: str, fixed: str) -> None:
        line = f"<verse osisID='Exod.35.34'>{damaged}</verse>"
        out, n = cs.repair_text(line)
        assert n == 1
        assert f">{fixed}<" in out

    def test_only_the_verse_opening_is_touched(self) -> None:
        """Anchored to the start of the verse text. `ll` mid-verse would
        be part of a real word — and rewriting it would corrupt one."""

        line = "<verse osisID='Gen.1.1'>Au commencement Dieu créa</verse>"
        out, n = cs.repair_text(line)
        assert n == 0
        assert out == line

    def test_a_real_word_starting_with_ll_is_not_a_target(self) -> None:
        """The rule requires `ll` or `lls` as a whole word. French has
        no such word, which is what makes the match safe — but a word
        merely *beginning* `ll` must still survive."""

        line = "<verse osisID='Gen.1.2'>llanos étaient vides</verse>"
        out, n = cs.repair_text(line)
        assert n == 0
        assert out == line


class TestIdempotence:
    def test_second_pass_changes_nothing(self) -> None:
        line = (
            "<verse osisID='Lam.3.711'>a élevé des forts</verse>\n"
            "<verse osisID='Exod.40.22'>ll mit aussi le chandelier</verse>"
        )
        once, n1 = cs.repair_text(line)
        twice, n2 = cs.repair_text(once)
        assert n1 == 2
        assert n2 == 0
        assert once == twice


class TestPopulation:
    """The whole point of the sweep on the issue: it is ten verses, not
    one, and not systematic."""

    def test_the_full_ten_verse_population_is_repaired_together(self) -> None:
        shape_b = [
            ("Exod.35.34", "ll lui a mis dans l'esprit"),
            ("Exod.40.22", "ll mit aussi le chandelier"),
            ("Exod.40.28", "ll posa aussi le bassin"),
            ("2Kgs.24.19", "ll fit le mal devant le Seigneur"),
            ("2Chr.25.2", "ll fit le bien en la présence"),
            ("Job.2.13", "lls demeurèrent avec lui"),
            ("Ps.83.13", "ll ne privera point de ses biens"),
            ("Ps.106.4", "lls ont erré dans la solitude"),
            ("John.15.2", "ll retranchera toutes les branches"),
        ]
        doc = "\n".join(
            ["<verse osisID='Lam.3.711'>a élevé des forts</verse>"]
            + [f"<verse osisID='{vid}'>{text}</verse>" for vid, text in shape_b]
        )
        out, n = cs.repair_text(doc)
        assert n == 10
        assert "Lam.3.711" not in out
        assert ">ll " not in out
        assert ">lls " not in out
