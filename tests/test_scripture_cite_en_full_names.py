"""Tests for full book names in the English scripture lexicon (#704).

`_LEXICON_EN` keyed only abbreviations, so ``(Matthew 19:20–22)``,
``Genesis 2:22–23`` and ``(Joshua xxiv. 2)`` never fired — about 110
cites across Hegel, Hobbes and Kant. The abbreviation group also capped
a name at nine letters, which alone kept ten books out of reach
(``Corinthians``, ``Revelation``, ``Deuteronomy``, …) whatever the
lexicon said.

Positive cases are verbatim from the corpus.
"""

from __future__ import annotations

import pytest

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.scripture_cite import ScriptureCiteRuleEn, ScriptureCiteRuleEnRoman
from minerva.refs.rules.scripture_cite.lexicon import _CONF_AMBIGUOUS


def _cands(text: str, rule=None):
    rule = rule or ScriptureCiteRuleEn()
    return list(rule.scan(ChunkInfo("t", "Hegel", "W", "eng", "1", text)))


def _locs(text: str, rule=None) -> list[str | None]:
    return [c.target_locator for c in _cands(text, rule)]


@pytest.mark.parametrize(
    "text,locator",
    [
        ("reat possessions.’ (Matthew 19:20–22; ", "Matt 19:20"),
        ("1. Cf. Genesis 2:22–23. ", "Gen 2:22"),
        ("”, saith the Lord’ (Romans 12:19); cf", "Rom 12:19"),
        ("stripe for stripe’ (Exodus 21:24). 2.", "Exod 21:24"),
        ("e, and recompense’ (Deuteronomy 32:35). 4.", "Deut 32:35"),
        ("e out of my mouth’ (Revelation 3:16). 30", "Rev 3:16"),
        ("he Tirans.\" 38. Cf. Philippians 2: 6 7. G", "Phil 2:6"),
        ("d consequences 94-6 1 Corinthians 2: 10 85 n", "1Cor 2:10"),
        ("kwell,1955). 9. Cf. Psalms 127:2: ‘It", "Ps 127:2"),
        ("deceased Giants; as Proverbs 21.16. \"Th", "Prov 21:16"),
        ("e words of Solomon (Ecclesiastes 12.7.) \"T", "Eccl 12:7"),
        ("appears by that of 2 Esdras 14.21. \"Th", "2Esd 14:21"),
        ("2:17; Isaiah 10:22; Hosea 1:10; Rom", "Isa 10:22"),
    ],
)
def test_full_names_with_arabic_chapters(text: str, locator: str) -> None:
    assert locator in _locs(text)


@pytest.mark.parametrize(
    "text,locator",
    [
        ("ships of his youth (Joshua xxiv. 2), 8 ", "Josh 24:2"),
        ("ble of the bramble (Judges ix. 14, 15)", "Judg 9:14"),
        ("Moses, argue thus, (Numbers xvi. 3): _Y", "Num 16:3"),
        ("t in their goings._ Micah v. 4, 5, ", "Mic 5:4"),
        ("inion_, &c. Haggai (Haggai ii. 6-7): ", "Hag 2:6"),
        ("d is in his heart._ Jeremiah xxx. 33: _I ", "Jer 30:33"),
    ],
)
def test_full_names_with_roman_chapters(text: str, locator: str) -> None:
    assert _locs(text, ScriptureCiteRuleEnRoman()) == [locator]


def test_a_bare_numbered_book_is_ambiguous() -> None:
    """"Timothy 3.2" is 1 or 2 Timothy; the rule must not claim to know."""

    (c,) = _cands("The eighth place is, Timothy 3.2. \"A")
    assert c.target_locator == "1Tim 3:2"
    assert c.confidence == _CONF_AMBIGUOUS


def test_an_ordinal_pins_a_numbered_book() -> None:
    (c,) = _cands("as it is written in 2 Corinthians 5:17 that")
    assert c.target_locator == "2Cor 5:17"
    assert c.confidence > _CONF_AMBIGUOUS


@pytest.mark.parametrize(
    "text",
    [
        # Back-of-book index lines the census found: a surname, then a
        # given name that is also a book, then page numbers.
        "Abelard, Peter 43, 45-6, 58",
        "Turner, Samuel 296 . 108, 297",
        "110. Solomon 240, 289, 321",
        # Not books: the last word of a multi-word title is never added.
        "1. Horace, Odes 1.3.",
        "Abdiel Abbadonna (Songs 2.627-31, ",
        "the Wisdom 3. 4 of the ancients",
    ],
)
def test_index_lines_and_title_fragments_do_not_fire(text: str) -> None:
    assert _locs(text) == []
    assert _locs(text, ScriptureCiteRuleEnRoman()) == []
