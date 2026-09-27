"""English KJV scripture cite rules."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ._base import BaseScriptureCiteRule

_LEXICON_EN: dict[tuple[str | None, str], str] = {
    # ── Pentateuch ────────────────────────────────────────────────
    (None, "Gen"): "Genesis",
    (None, "Ex"): "Exodus",
    (None, "Exod"): "Exodus",
    (None, "Lev"): "Leviticus",
    (None, "Levit"): "Leviticus",  # 17th-c. (Hobbes), #703
    (None, "Num"): "Numbers",
    (None, "Numb"): "Numbers",  # 17th-c. (Hobbes), #703
    (None, "Deut"): "Deuteronomy",
    (None, "Deuteron"): "Deuteronomy",  # 17th-c. (Hobbes), #703
    (None, "Dt"): "Deuteronomy",
    # ── Historical ────────────────────────────────────────────────
    (None, "Josh"): "Joshua",
    (None, "Jos"): "Joshua",
    (None, "Judg"): "Judges",
    (None, "Jdg"): "Judges",
    (None, "Ruth"): "Ruth",
    (None, "Rth"): "Ruth",
    ("1", "Sam"): "1 Samuel",
    ("I", "Sam"): "1 Samuel",
    ("2", "Sam"): "2 Samuel",
    ("II", "Sam"): "2 Samuel",
    ("1", "Kgs"): "1 Kings",
    ("I", "Kgs"): "1 Kings",
    ("1", "Kings"): "1 Kings",
    ("I", "Kings"): "1 Kings",
    ("2", "Kgs"): "2 Kings",
    ("II", "Kgs"): "2 Kings",
    ("2", "Kings"): "2 Kings",
    ("II", "Kings"): "2 Kings",
    ("1", "Chr"): "1 Chronicles",
    ("I", "Chr"): "1 Chronicles",
    ("1", "Chron"): "1 Chronicles",
    ("I", "Chron"): "1 Chronicles",
    ("2", "Chr"): "2 Chronicles",
    ("II", "Chr"): "2 Chronicles",
    ("2", "Chron"): "2 Chronicles",
    ("II", "Chron"): "2 Chronicles",
    (None, "Ezra"): "Ezra",
    (None, "Neh"): "Nehemiah",
    (None, "Esth"): "Esther",
    (None, "Est"): "Esther",
    # ── Wisdom ────────────────────────────────────────────────────
    (None, "Job"): "Job",
    (None, "Ps"): "Psalms",
    (None, "Psa"): "Psalms",
    (None, "Psalm"): "Psalms",
    (None, "Psal"): "Psalms",  # 17th-c. (Hobbes, Locke), #703
    (None, "Prov"): "Proverbs",
    (None, "Pr"): "Proverbs",
    (None, "Eccl"): "Ecclesiastes",
    (None, "Ecc"): "Ecclesiastes",
    (None, "Song"): "Song of Songs",
    (None, "Cant"): "Song of Songs",
    # ── Major prophets ────────────────────────────────────────────
    (None, "Isa"): "Isaiah",
    (None, "Isai"): "Isaiah",  # 17th-c. (Hobbes), #703
    (None, "Is"): "Isaiah",
    (None, "Jer"): "Jeremiah",
    (None, "Jerem"): "Jeremiah",  # 17th-c. (Hobbes), #703
    (None, "Lam"): "Lamentations",
    (None, "Ezek"): "Ezekiel",
    (None, "Ez"): "Ezekiel",
    (None, "Dan"): "Daniel",
    # ── Minor prophets ────────────────────────────────────────────
    (None, "Hos"): "Hosea",
    (None, "Joel"): "Joel",
    (None, "Am"): "Amos",
    (None, "Amos"): "Amos",
    (None, "Obad"): "Obadiah",
    (None, "Ob"): "Obadiah",
    (None, "Jon"): "Jonah",
    (None, "Jonah"): "Jonah",
    (None, "Mic"): "Micah",
    (None, "Nah"): "Nahum",
    (None, "Hab"): "Habakkuk",
    (None, "Zeph"): "Zephaniah",
    (None, "Zep"): "Zephaniah",
    (None, "Hag"): "Haggai",
    (None, "Zech"): "Zechariah",
    (None, "Zach"): "Zechariah",  # 17th-c. (Hobbes), #703
    (None, "Zec"): "Zechariah",
    (None, "Mal"): "Malachi",
    # ── Apocrypha (1611 KJV included; modern KJV often omits) ─────
    (None, "Tob"): "Tobit",
    (None, "Jdt"): "Judith",
    (None, "Wis"): "Wisdom",
    (None, "Wisd"): "Wisdom",
    (None, "Sir"): "Sirach",
    (None, "Ecclus"): "Sirach",
    (None, "Bar"): "Baruch",
    ("1", "Macc"): "1 Maccabees",
    ("I", "Macc"): "1 Maccabees",
    ("2", "Macc"): "2 Maccabees",
    ("II", "Macc"): "2 Maccabees",
    # ── Gospels + Acts ────────────────────────────────────────────
    (None, "Mt"): "Matthew",
    (None, "Matt"): "Matthew",
    (None, "Matth"): "Matthew",  # 17th-c. (Hobbes), #703
    (None, "Mk"): "Mark",
    (None, "Mark"): "Mark",
    (None, "Lk"): "Luke",
    (None, "Lu"): "Luke",
    (None, "Luke"): "Luke",
    (None, "Jn"): "John",
    (None, "John"): "John",
    (None, "Joh"): "John",
    (None, "Acts"): "Acts",
    (None, "Ac"): "Acts",
    # ── Pauline epistles ──────────────────────────────────────────
    (None, "Rom"): "Romans",
    ("1", "Cor"): "1 Corinthians",
    ("I", "Cor"): "1 Corinthians",
    ("2", "Cor"): "2 Corinthians",
    ("II", "Cor"): "2 Corinthians",
    (None, "Cor"): "1 Corinthians",  # ambiguous-bare
    (None, "Gal"): "Galatians",
    (None, "Eph"): "Ephesians",
    (None, "Ephes"): "Ephesians",  # 17th-c. (Hobbes), #703
    (None, "Phil"): "Philippians",
    (None, "Phi"): "Philippians",
    (None, "Col"): "Colossians",
    (None, "Coloss"): "Colossians",  # 17th-c. (Hobbes), #703
    (None, "Colos"): "Colossians",
    ("1", "Thess"): "1 Thessalonians",
    ("I", "Thess"): "1 Thessalonians",
    ("2", "Thess"): "2 Thessalonians",
    ("II", "Thess"): "2 Thessalonians",
    ("1", "Tim"): "1 Timothy",
    ("I", "Tim"): "1 Timothy",
    ("2", "Tim"): "2 Timothy",
    ("II", "Tim"): "2 Timothy",
    (None, "Tim"): "1 Timothy",  # ambiguous-bare
    (None, "Tit"): "Titus",
    (None, "Titus"): "Titus",
    (None, "Phlm"): "Philemon",
    (None, "Phm"): "Philemon",
    (None, "Heb"): "Hebrews",
    (None, "Hebr"): "Hebrews",
    # ── Catholic epistles ─────────────────────────────────────────
    (None, "Jas"): "James",
    (None, "James"): "James",
    ("1", "Pet"): "1 Peter",
    ("I", "Pet"): "1 Peter",
    ("2", "Pet"): "2 Peter",
    ("II", "Pet"): "2 Peter",
    (None, "Pet"): "1 Peter",  # ambiguous-bare
    ("1", "Jn"): "1 John",
    ("I", "Jn"): "1 John",
    ("1", "John"): "1 John",
    ("I", "John"): "1 John",
    ("2", "Jn"): "2 John",
    ("II", "Jn"): "2 John",
    ("3", "Jn"): "3 John",
    ("III", "Jn"): "3 John",
    (None, "Jude"): "Jude",
    # ── Revelation ────────────────────────────────────────────────
    (None, "Rev"): "Revelation",
    (None, "Apoc"): "Revelation",
}


# ── Full book names (#704) ───────────────────────────────────────
# The dict above keys abbreviations only, so "(Matthew 19:20–22)" and
# "(Joshua xxiv. 2)" never fired: ~110 cites across Hegel, Hobbes and
# Kant. Listed by hand from `locations._BCV_BOOKS`, NOT derived from each
# book's last word — that would add "Solomon", "Songs", "Odes", "Wisdom"
# and "Dragon", and the census's back-of-book index lines ("110. Solomon
# 240, 289") are exactly what those would bind.
_FULL_NAMES_EN: tuple[str, ...] = (
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua",
    "Judges", "Nehemiah", "Tobit", "Judith", "Esther", "Psalms", "Proverbs",
    "Ecclesiastes", "Sirach", "Isaiah", "Jeremiah", "Lamentations", "Baruch",
    "Ezekiel", "Daniel", "Hosea", "Obadiah", "Micah", "Nahum", "Habakkuk",
    "Zephaniah", "Haggai", "Zechariah", "Malachi", "Matthew", "Romans",
    "Galatians", "Ephesians", "Philippians", "Colossians", "Philemon",
    "Hebrews", "Revelation", "Susanna",
)
# Numbered books, by how many there are. A bare name ("Timothy 3.2") is
# emitted at ambiguous confidence against the first, as "Tim" already is.
_NUMBERED_FULL_NAMES_EN: dict[str, int] = {
    "Samuel": 2, "Chronicles": 2, "Maccabees": 4, "Esdras": 2, "Corinthians": 2,
    "Thessalonians": 2, "Timothy": 2, "Peter": 2,
}
_ORDINALS: tuple[tuple[str, str], ...] = (("1", "I"), ("2", "II"), ("3", "III"), ("4", "IV"))



def _full_name_entries() -> dict[tuple[str | None, str], str]:
    entries: dict[tuple[str | None, str], str] = {(None, n): n for n in _FULL_NAMES_EN}
    entries[(None, "Revelations")] = "Revelation"
    for name, count in _NUMBERED_FULL_NAMES_EN.items():
        for n, (arabic, roman) in enumerate(_ORDINALS[:count], start=1):
            entries[(arabic, name)] = entries[(roman, name)] = f"{n} {name}"
        entries[(None, name)] = f"1 {name}"
    return entries


_LEXICON_EN.update(_full_name_entries())


_AMBIGUOUS_BARE_EN: frozenset[str] = frozenset(
    {"Cor", "Pet", "Tim", "Thess", "Sam", "Kgs", "Kings", "Chr", "Chron", "Macc", "Joh"}
    | set(_NUMBERED_FULL_NAMES_EN)
)


# English chap-verse separator: modern usage is colon ("Matt 5:48");
# the 1651 *Leviathan* uses a period ("Exod. 28. 3", "Mark 3.21",
# "Rom. 8.9."). Accept both. Locke and Hobbes's English *De Cive* and
# *De Corpore Politico* set the chapter in Roman ("Gen. xiii. 5.") —
# that is `ScriptureCiteRuleEnRoman` below, not this pattern. We require
# the abbrev to start with an uppercase Latin letter to skip e.g.
# clause numbering in modern editions.
_CITE_RE_EN = re.compile(
    r"(?:\b(?P<prefix>I{1,3}V?|[1-3])\s*\.?\s*)?"  # optional ordinal
    r"\b(?P<abbr>[A-Z][a-z]{1,12})\.?"  # abbrev or full name (#704)
    r"\s+"
    r"(?P<chap>\d{1,3})"
    r"\s*[:.]\s*"  # colon OR period sep
    r"(?P<verse>\d{1,3})"
    r"(?:\s*[-–]\s*\d{1,3})?"  # optional verse range
)


@dataclass(frozen=True)
class ScriptureCiteRuleEn(BaseScriptureCiteRule):
    """English scripture-citation rule (KJV target).

    Used by Hobbes/Locke/Hume rule modules. Same Candidate shape and
    binding pipeline as the Latin and German variants."""

    name: str = "scripture_cite_kjv_en"
    target_author: str = "King James Bible"
    langs: tuple[str, ...] = ("eng",)

    lexicon = _LEXICON_EN
    cite_re = _CITE_RE_EN
    ambiguous_bare = _AMBIGUOUS_BARE_EN


# Roman-numeral-chapter cites — "Gen. xiii. 5." (Locke), "Matth. xviii.
# 17" (Hobbes's English De Cive), "Psalm cxix. 160". `_CITE_RE_EN` takes
# an Arabic chapter only, so none of these fired: 235 such shapes across
# the English and German corpus, 0 detected (#703).
#
# A sibling rather than a widening of `_CITE_RE_EN`, as `lat.py` and
# `fr.py` do. The chapter group is Roman-only, so an Arabic citation is
# never counted twice, and it needs its own trailing period. The
# abbreviation's period stays optional because "Acts", "Luke" and
# "John" are written without one. The verse stays Arabic: a Roman verse
# group would read the pronoun in "Mark ii. I said" as verse 1. Swept
# over every chunk of the nine authors who run an English or German
# scripture rule before landing; every new hit was read.
_CITE_RE_EN_ROMAN = re.compile(
    r"(?:\b(?P<prefix>I{1,3}V?|[1-3])\s*\.?\s*)?"  # optional ordinal
    r"\b(?P<abbr>[A-Z][a-z]{1,12})\.?"  # abbrev or full name (#704)
    r"\s+"
    r"(?P<chap>[ivxlc]{1,7}|[IVXLC]{1,7})\."  # Roman chapter, one case
    r"\s*"
    r"(?P<verse>\d{1,3})"
    r"(?:\s*[-–]\s*\d{1,3})?"  # optional verse range
)


@dataclass(frozen=True)
class ScriptureCiteRuleEnRoman(BaseScriptureCiteRule):
    """English rule accepting a Roman-numeral chapter with an Arabic
    verse — the convention of Locke's *Second Treatise* and *Essay* and
    of Hobbes's English *De Cive* and *De Corpore Politico*."""

    name: str = "scripture_cite_kjv_en_roman"
    target_author: str = "King James Bible"
    langs: tuple[str, ...] = ("eng",)

    lexicon = _LEXICON_EN
    cite_re = _CITE_RE_EN_ROMAN
    ambiguous_bare = _AMBIGUOUS_BARE_EN
