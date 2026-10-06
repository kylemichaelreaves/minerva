"""Tests for the Latin Roman-numeral-chapter scripture cite rule (#535).

Molesworth's 1839 *Opera Latina* cites scripture in the 19th-century
scholarly convention — ``1 Cor. ix. 9``, ``Rom. viii. 5``, ``Matth.
xxv. 41`` — where the 1642/1668 printings it reprints used Arabic
chapter numbers, ``Cor. 9``. Re-sourcing the Latin Hobbes to Molesworth
therefore moved every one of its scripture citations out of reach of
`lexicon._CITE_RE`, whose chapter group is `\\d{1,3}`: the Latin Hobbes
went from 276 Vulgate cross-references to 4.

This is a sibling rule rather than a widening of the shared regex,
following `ScriptureCiteRuleFrRoman`, which exists for the same
convention in French (Renan). Measured before writing it: chapter-in-
Roman citations number 555 in the new Hobbes Latin, 7 in Spinoza, and 0
in Aquinas, Augustine and Descartes — so widening the shared pattern
would have carried risk across every Latin author for a benefit
confined to one.
"""

from __future__ import annotations

import pytest

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.scripture_cite import ScriptureCiteRule
from minerva.refs.rules.scripture_cite.lat import ScriptureCiteRuleLatRoman


def _chunk(text: str, *, author: str = "Hobbes", lang: str = "lat") -> ChunkInfo:
    return ChunkInfo(
        chunk_id="test",
        author=author,
        work="Leviathan",
        lang=lang,
        section="Cap 1, ¶1",
        text=text,
    )


def _locators(text: str, **kw) -> list[str | None]:
    rule = ScriptureCiteRuleLatRoman()
    return [c.target_locator for c in rule.scan(_chunk(text, **kw))]


class TestMolesworthForms:
    """Every shape below is a verbatim citation from the re-sourced
    files, not an invented one."""

    @pytest.mark.parametrize(
        "text,locator",
        [
            ("sanctus Paulus, 1 Cor. ix. 9, de hominibus", "1Cor 9:9"),
            ("Et sanctus Paulus (1 Cor. xv. 22-24): Sicut", "1Cor 15:22"),
            ("multis in locis (Rom. viii. 5)", "Rom 8:5"),
            ("verbis Servatoris nostri (Matth. xxv. 41): Ite", "Matt 25:41"),
            ("populus Dei dicuntur (Exod. xix. 6) Gens sancta", "Exod 19:6"),
            ("Deut. xxv. 4: Non obturabis os bovis", "Deut 25:4"),
            ("Prov. ix. 10, initium sapientiae", "Prov 9:10"),
            ("Jer. xxxi. 33, dabo legem meam", "Jer 31:33"),
        ],
    )
    def test_roman_chapter_with_arabic_verse(self, text: str, locator: str) -> None:
        assert locator in _locators(text)

    @pytest.mark.parametrize(
        "text",
        [
            # No space after the abbreviation's period.
            "Psal.lxxxiv. 11, beatus homo",
            # No space before the verse.
            "Gen. xiii.8 dixit ergo Abram",
        ],
    )
    def test_spacing_variants_the_scan_actually_contains(self, text: str) -> None:
        assert _locators(text), f"no candidate from {text!r}"

    def test_arabic_ordinal_prefix_disambiguates(self) -> None:
        """Molesworth writes ``1 Cor.`` where the shared Latin pattern
        expects the Roman ordinal ``I Cor.``. Without the Arabic
        alternative the book stays ambiguous and the candidate lands on
        the wrong epistle or at floor confidence."""

        assert "1Cor 9:9" in _locators("Paulus, 1 Cor. ix. 9, de bobus")
        assert "2Cor 5:1" in _locators("Paulus, 2 Cor. v. 1, scimus enim")

    def test_roman_ordinal_prefix_still_works(self) -> None:
        assert "1Cor 9:9" in _locators("Paulus, I Cor. ix. 9, de bobus")


class TestFalsePositives:
    """The chapter group is a run of `ivxlc`, which is also how a good
    many short Latin words are spelled. The gates are the lexicon
    lookup on the book name and the required period after the numeral."""

    @pytest.mark.parametrize(
        "text",
        [
            # Not a book of the Bible.
            "Aristoteles. ix. 3 dicit",
            # A Latin word where the chapter would go, with no period.
            "Matth. vix intelligitur",
            # Bare prose containing roman-looking letters.
            "civilis illa vis maxima est",
            # No chapter numeral at all.
            "sicut in Genesi legitur",
        ],
    )
    def test_non_citations_do_not_fire(self, text: str) -> None:
        assert _locators(text) == []

    def test_other_languages_are_skipped(self) -> None:
        assert _locators("1 Cor. ix. 9", lang="fra") == []
        assert _locators("1 Cor. ix. 9", lang="eng") == []

    def test_the_vulgate_does_not_cite_itself(self) -> None:
        assert _locators("1 Cor. ix. 9", author="Vulgate") == []

    def test_implausible_chapter_is_rejected(self) -> None:
        """`_parse_cite_num` caps at 176 (Ps 119). A longer roman run is
        OCR noise, not a chapter."""

        assert _locators("Matth. mmmm. 3 dicit") == []


class TestNoOverlapWithTheArabicRule:
    """The two rules must not both fire on the same span, or every
    Arabic citation in Aquinas would be counted twice."""

    def test_arabic_citations_are_left_to_the_existing_rule(self) -> None:
        assert _locators("sicut dicitur Matth. 5-48") == []

    def test_the_existing_rule_is_unchanged_on_arabic(self) -> None:
        rule = ScriptureCiteRule()
        got = [c.target_locator for c in rule.scan(_chunk("sicut Matth. 5-48"))]
        assert "Matt 5:48" in got

    def test_the_existing_rule_does_not_fire_on_roman(self) -> None:
        """Pinned so that if the shared `_CITE_RE` is ever widened to
        Roman chapters, this test fails and whoever did it has to
        remove the sibling rule rather than double-count."""

        rule = ScriptureCiteRule()
        got = [c.target_locator for c in rule.scan(_chunk("Paulus 1 Cor. ix. 9"))]
        assert "1Cor 9:9" not in got
