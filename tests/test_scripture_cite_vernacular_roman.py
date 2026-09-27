"""Tests for the English and German Roman-numeral-chapter scripture
cite rules (#703).

`ScriptureCiteRuleEn` and `ScriptureCiteRuleDe` take an Arabic chapter
only, so every citation in the 18th–19th-c. convention — ``Gen. xiii.
5.`` (Locke), ``Matth. xviii. 17`` (Hobbes's English *De Cive*),
``Matth. XXV, 35-40`` (Kant) — went undetected: 235 such shapes across
seven authors, none caught. Siblings rather than a widening of the
shared patterns, following `ScriptureCiteRuleLatRoman` (#535) and
`ScriptureCiteRuleFrRoman`.

Every positive case below is verbatim from the corpus.
"""

from __future__ import annotations

import pytest

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.scripture_cite import (
    ScriptureCiteRuleDe,
    ScriptureCiteRuleDeRoman,
    ScriptureCiteRuleEn,
    ScriptureCiteRuleEnRoman,
    default_scripture_rules,
)


def _chunk(text: str, *, author: str = "Locke", lang: str = "eng") -> ChunkInfo:
    return ChunkInfo(
        chunk_id="test",
        author=author,
        work="W",
        lang=lang,
        section="1",
        text=text,
    )


def _en(text: str, **kw) -> list[str | None]:
    return [c.target_locator for c in ScriptureCiteRuleEnRoman().scan(_chunk(text, **kw))]


def _de(text: str, **kw) -> list[str | None]:
    kw.setdefault("lang", "deu")
    kw.setdefault("author", "Kant")
    return [c.target_locator for c in ScriptureCiteRuleDeRoman().scan(_chunk(text, **kw))]


class TestEnglishForms:
    @pytest.mark.parametrize(
        "text,locator",
        [
            ("as Abraham and Lot did, Gen. xiii. 5. separated", "Gen 13:5"),
            ("God has given us all things richly, 1 Tim. vi. 12. is the voice", "1Tim 6:12"),
            ("if there be any praise,’ &c. (Phil. iv. 8.)", "Phil 4:8"),
            ("the children of Ammon, Judg. xi. 27. and then", "Judg 11:27"),
            ("which St. Paul (1 Cor. ix. 9) interpreteth", "1Cor 9:9"),
            ("Psalm cxix. 160: _Every one of", "Ps 119:160"),
            ("in _the side of the ark_, (Deut. xxxi. 26).", "Deut 31:26"),
            ("I. Sam viii. 20. God granting", "1Sam 8:20"),
            # A book name written without a period.
            ("all nations did after God (Acts xvii. 27); than", "Acts 17:27"),
            ("the thief on the cross (Luke xxiii. 42): _Lord", "Luke 23:42"),
        ],
    )
    def test_roman_chapter_with_arabic_verse(self, text: str, locator: str) -> None:
        assert _en(text) == [locator]

    @pytest.mark.parametrize(
        "text,locator",
        [
            ("our Saviour saith (Matth. xviii. 17): _If he", "Matt 18:17"),
            ("God (Numb. i. 4) twelve men", "Num 1:4"),
            ("the Church_ (Coloss. i. 18). Sometimes", "Col 1:18"),
            ("St. Paul saith (Colos. iii. 20, 22)", "Col 3:20"),
            ("the high-priest (Zach. iii. 8): _I will", "Zech 3:8"),
            ("were commanded (Levit. xiii. 46) to be", "Lev 13:46"),
            ("his Church_ (Ephes. v. 23); and", "Eph 5:23"),
            ("as king David says, Psal. cxv. 16. has given", "Ps 115:16"),
            ("unto the eyes._ Deuteron. xxx. 11: _This", "Deut 30:11"),
            ("Isaiah (Isai. vii. 14): _The Lord", "Isa 7:14"),
            ("Jeremiah (Jerem. xxxi. 31): _Behold", "Jer 31:31"),
        ],
    )
    def test_seventeenth_century_abbreviations(self, text: str, locator: str) -> None:
        """Hobbes's abbreviations, missing from the lexicon until #703.
        `Matth` alone is 56 of the Roman-chapter cites in his English."""

        assert _en(text) == [locator]

    def test_the_arabic_rule_gains_the_abbreviations_too(self) -> None:
        """The lexicon is shared, so *Leviathan*'s Arabic cites in the
        same abbreviations resolve as well."""

        rule = ScriptureCiteRuleEn()
        got = [c.target_locator for c in rule.scan(_chunk('And (Matth. 19.13.) "they', author="Hobbes"))]
        assert got == ["Matt 19:13"]


class TestGermanForms:
    @pytest.mark.parametrize(
        "text,locator",
        [
            ("als durch eine neue Schöpfung (Ev. Joh. III, 5; verglichen", "John 3:5"),
            ("wohlgefällig machen könne (Matth. V, 20-48); daß", "Matt 5:20"),
            ("als ein solcher (Luc. XVI, 3-9) vorgestellt", "Luke 16:3"),
            ("der Pflicht (Matth. XXV, 35-40) gesagt wird", "Matt 25:35"),
            ("aller Güter der Erde eingesetzt (1. Mos. I, 28), doch", "Gen 1:28"),
            ("bis zu seinem Ende… Luc. IV, 18 „das angenehme", "Luke 4:18"),
        ],
    )
    def test_roman_chapter_with_arabic_verse(self, text: str, locator: str) -> None:
        assert locator in _de(text)

    def test_the_arabic_rule_gains_luc(self) -> None:
        """Kant and Nietzsche write the Latin-form ``Luc.`` for Luke."""

        rule = ScriptureCiteRuleDe()
        got = [c.target_locator for c in rule.scan(_chunk("(Luc. 17. 21 bis 22)", author="Kant", lang="deu"))]
        assert got == ["Luke 17:21"]


class TestFalsePositives:
    @pytest.mark.parametrize(
        "text",
        [
            # Not books of the Bible — the lexicon gate.
            "see Vol. ii. 3 of the edition",
            "as in Phys. iv. 11 and elsewhere",
            # A Roman numeral with no verse after it.
            "Matth. xviii. where it is said",
            # A pronoun where the verse would go: verses stay Arabic.
            "Mark ii. I said unto them",
        ],
    )
    def test_english_non_citations_do_not_fire(self, text: str) -> None:
        assert _en(text) == []

    @pytest.mark.parametrize(
        "text",
        [
            "wie es im Kap. IV, 3 heißt",
            "Bd. II, 3 der Ausgabe",
        ],
    )
    def test_german_non_citations_do_not_fire(self, text: str) -> None:
        assert _de(text) == []

    def test_mixed_case_numerals_are_rejected(self) -> None:
        """Mixed-case runs are OCR noise, as in the French sibling."""

        assert _en("Gen. xIii. 5 and") == []

    def test_other_languages_are_skipped(self) -> None:
        assert _en("Gen. xiii. 5.", lang="deu") == []
        assert _de("Matth. V, 20", lang="eng") == []

    def test_the_bibles_do_not_cite_themselves(self) -> None:
        assert _en("Gen. xiii. 5.", author="King James Bible") == []
        assert _de("Matth. V, 20", author="Luther Bibel 1912") == []


class TestNoOverlapWithTheArabicRules:
    """Both rules run on the same chunks; an Arabic citation must be
    counted once, by the existing rule."""

    def test_arabic_citations_are_left_to_the_existing_rules(self) -> None:
        assert _en("Gen. 13. 5 and") == []
        assert _de("Matth. 5, 44 und") == []

    def test_the_existing_rules_do_not_fire_on_roman(self) -> None:
        en = [c.target_locator for c in ScriptureCiteRuleEn().scan(_chunk("Gen. xiii. 5."))]
        de = [
            c.target_locator
            for c in ScriptureCiteRuleDe().scan(_chunk("Matth. V, 20", author="Kant", lang="deu"))
        ]
        assert en == [] and de == []


class TestWiring:
    """A rule nobody runs is the defect #703 was — check it is wired."""

    def test_default_rules_include_both_siblings(self) -> None:
        kinds = {type(r) for r in default_scripture_rules("x")}
        assert {ScriptureCiteRuleEnRoman, ScriptureCiteRuleDeRoman} <= kinds

    @pytest.mark.parametrize("module", ["hobbes", "locke", "hume"])
    def test_english_rule_modules_run_the_sibling(self, module: str) -> None:
        import importlib

        rules = importlib.import_module(f"minerva.refs.rules.{module}").RULES
        assert any(isinstance(r, ScriptureCiteRuleEnRoman) for r in rules)
        names = [r.name for r in rules]
        assert len(names) == len(set(names)), "rule names must stay unique"
