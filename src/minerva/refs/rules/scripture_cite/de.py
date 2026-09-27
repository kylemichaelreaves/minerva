"""German Luther-Bible scripture cite rules."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ._base import BaseScriptureCiteRule

_LEXICON_DE: dict[tuple[str | None, str], str] = {
    # ── Pentateuch — Mose-number form ─────────────────────────────
    ("1", "Mose"): "Genesis",
    ("I", "Mose"): "Genesis",
    ("2", "Mose"): "Exodus",
    ("II", "Mose"): "Exodus",
    ("3", "Mose"): "Leviticus",
    ("III", "Mose"): "Leviticus",
    ("4", "Mose"): "Numbers",
    ("IV", "Mose"): "Numbers",
    ("5", "Mose"): "Deuteronomy",
    ("V", "Mose"): "Deuteronomy",
    # The shortened "Mos." (Kant: "1. Mos. I, 28"), #703.
    ("1", "Mos"): "Genesis",
    ("I", "Mos"): "Genesis",
    ("2", "Mos"): "Exodus",
    ("II", "Mos"): "Exodus",
    ("3", "Mos"): "Leviticus",
    ("III", "Mos"): "Leviticus",
    ("4", "Mos"): "Numbers",
    ("IV", "Mos"): "Numbers",
    ("5", "Mos"): "Deuteronomy",
    ("V", "Mos"): "Deuteronomy",
    # ── Pentateuch — scholarly abbreviations ──────────────────────
    (None, "Gen"): "Genesis",
    (None, "Ex"): "Exodus",
    (None, "Lev"): "Leviticus",
    (None, "Num"): "Numbers",
    (None, "Dtn"): "Deuteronomy",
    (None, "Deut"): "Deuteronomy",
    # ── Historical ────────────────────────────────────────────────
    (None, "Jos"): "Joshua",
    (None, "Ri"): "Judges",
    (None, "Richt"): "Judges",
    (None, "Ruth"): "Ruth",
    (None, "Rut"): "Ruth",
    ("1", "Sam"): "1 Samuel",
    ("I", "Sam"): "1 Samuel",
    ("2", "Sam"): "2 Samuel",
    ("II", "Sam"): "2 Samuel",
    ("1", "Kön"): "1 Kings",
    ("I", "Kön"): "1 Kings",
    ("1", "Koen"): "1 Kings",  # ASCII fallback
    ("2", "Kön"): "2 Kings",
    ("II", "Kön"): "2 Kings",
    ("2", "Koen"): "2 Kings",
    ("1", "Chr"): "1 Chronicles",
    ("I", "Chr"): "1 Chronicles",
    ("2", "Chr"): "2 Chronicles",
    ("II", "Chr"): "2 Chronicles",
    (None, "Esra"): "Ezra",
    (None, "Neh"): "Nehemiah",
    (None, "Est"): "Esther",
    # ── Wisdom ────────────────────────────────────────────────────
    (None, "Hi"): "Job",
    (None, "Hiob"): "Job",
    (None, "Ps"): "Psalms",
    (None, "Psalm"): "Psalms",
    (None, "Spr"): "Proverbs",
    (None, "Sprüche"): "Proverbs",
    (None, "Pred"): "Ecclesiastes",
    (None, "Koh"): "Ecclesiastes",
    (None, "Hld"): "Song of Songs",
    (None, "Hl"): "Song of Songs",
    # ── Major prophets ────────────────────────────────────────────
    (None, "Jes"): "Isaiah",
    (None, "Is"): "Isaiah",
    (None, "Jer"): "Jeremiah",
    (None, "Klgl"): "Lamentations",
    (None, "Klagel"): "Lamentations",
    (None, "Ez"): "Ezekiel",
    (None, "Hes"): "Ezekiel",  # Hesekiel — old Luther
    (None, "Dan"): "Daniel",
    # ── Minor prophets ────────────────────────────────────────────
    (None, "Hos"): "Hosea",
    (None, "Joel"): "Joel",
    (None, "Am"): "Amos",
    (None, "Ob"): "Obadiah",
    (None, "Obd"): "Obadiah",
    (None, "Jona"): "Jonah",
    (None, "Mi"): "Micah",
    (None, "Mich"): "Micah",
    (None, "Nah"): "Nahum",
    (None, "Hab"): "Habakkuk",
    (None, "Zef"): "Zephaniah",
    (None, "Zeph"): "Zephaniah",
    (None, "Hag"): "Haggai",
    (None, "Sach"): "Zechariah",
    (None, "Mal"): "Malachi",
    # ── Apocrypha ─────────────────────────────────────────────────
    (None, "Tob"): "Tobit",
    (None, "Tobias"): "Tobit",
    (None, "Jdt"): "Judith",
    (None, "Weish"): "Wisdom",
    (None, "Sir"): "Sirach",
    (None, "JesSir"): "Sirach",
    (None, "Bar"): "Baruch",
    ("1", "Makk"): "1 Maccabees",
    ("I", "Makk"): "1 Maccabees",
    ("2", "Makk"): "2 Maccabees",
    ("II", "Makk"): "2 Maccabees",
    # ── Gospels + Acts ────────────────────────────────────────────
    (None, "Mt"): "Matthew",
    (None, "Matth"): "Matthew",
    (None, "Matt"): "Matthew",
    (None, "Mk"): "Mark",
    (None, "Mark"): "Mark",
    (None, "Lk"): "Luke",
    (None, "Luk"): "Luke",
    (None, "Luc"): "Luke",  # Latin form (Kant, Nietzsche), #703
    (None, "Joh"): "John",  # bare "Joh" is ambiguous (Gospel vs 1-3 John)
    (None, "Apg"): "Acts",
    # ── Pauline epistles ──────────────────────────────────────────
    (None, "Röm"): "Romans",
    (None, "Rom"): "Romans",
    ("1", "Kor"): "1 Corinthians",
    ("I", "Kor"): "1 Corinthians",
    ("2", "Kor"): "2 Corinthians",
    ("II", "Kor"): "2 Corinthians",
    (None, "Kor"): "1 Corinthians",  # ambiguous-bare
    (None, "Gal"): "Galatians",
    (None, "Eph"): "Ephesians",
    (None, "Phil"): "Philippians",
    (None, "Kol"): "Colossians",
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
    (None, "Phlm"): "Philemon",
    (None, "Philem"): "Philemon",
    (None, "Hebr"): "Hebrews",
    (None, "Heb"): "Hebrews",
    (None, "Hbr"): "Hebrews",
    # ── Catholic epistles ─────────────────────────────────────────
    (None, "Jak"): "James",
    (None, "Jac"): "James",
    ("1", "Petr"): "1 Peter",
    ("I", "Petr"): "1 Peter",
    ("1", "Pet"): "1 Peter",
    ("2", "Petr"): "2 Peter",
    ("II", "Petr"): "2 Peter",
    ("2", "Pet"): "2 Peter",
    (None, "Petr"): "1 Peter",  # ambiguous-bare
    ("1", "Joh"): "1 John",
    ("I", "Joh"): "1 John",
    ("2", "Joh"): "2 John",
    ("II", "Joh"): "2 John",
    ("3", "Joh"): "3 John",
    ("III", "Joh"): "3 John",
    (None, "Jud"): "Jude",
    # ── Revelation ────────────────────────────────────────────────
    (None, "Offb"): "Revelation",
    (None, "Apk"): "Revelation",
    (None, "Off"): "Revelation",
}


# Bare abbrevs whose default canonical resolution is ambiguous —
# emitted at low confidence.
_AMBIGUOUS_BARE_DE: frozenset[str] = frozenset(
    {"Joh", "Petr", "Pet", "Kor", "Tim", "Thess", "Makk", "Sam", "Kön", "Koen", "Chr", "Mose"}
)


# German cite regex. The CHAP–VERSE separator is mostly a comma
# (19th-c. convention — Hegel "Matth. 7, 20") but Kant and earlier
# Lutheran convention use a period ("Joh. 3. 17"). We accept either,
# plus whitespace-only separation; the period form would otherwise
# collide with chunk-final punctuation in some authors but the
# ``\d{1,3}\s*[.,]\s*\d{1,3}`` shape only matches when followed by
# more digits — see test in scripts/survey_unmatched_scripture_cites.
_CITE_RE_DE = re.compile(
    r"(?:\b(?P<prefix>I{1,3}V?|[1-5])\.?\s*)?"  # optional ordinal (incl. 4/5 Mose)
    r"\b(?P<abbr>[A-ZÄÖÜ][A-Za-zäöüß]{1,8})\.?"  # German abbrev
    r"\s+"
    r"(?P<chap>\d{1,3})"
    r"\s*[,.]\s*"  # comma OR period sep
    r"(?P<verse>\d{1,3})"
    r"(?:\s*[-–]\s*\d{1,3})?"  # optional verse range
)


@dataclass(frozen=True)
class ScriptureCiteRuleDe(BaseScriptureCiteRule):
    """Fires on German vernacular scripture-cite syntax in chunk text.

    Used by Hegel/Kant/Marx/Nietzsche rule modules. Locator binding
    against :mod:`luther_1912` chunks happens in
    ``insert_candidate`` exactly like the Latin rule.

    ``target_author`` defaults to ``"Luther Bibel 1912"`` (the
    modernized resolution target). The Reader can render the same
    verse in 1545 via the sidebar's edition picker — citation rules
    don't try to disambiguate which edition the source author had in
    hand, since the verse text is identical for cite-resolution
    purposes."""

    name: str = "scripture_cite_luther_de"
    target_author: str = "Luther Bibel 1912"
    langs: tuple[str, ...] = ("deu",)

    lexicon = _LEXICON_DE
    cite_re = _CITE_RE_DE
    ambiguous_bare = _AMBIGUOUS_BARE_DE


# Roman-numeral-chapter cites — "Matth. XXV, 35-40", "Ev. Joh. III, 5"
# (Kant), "Luc. IV, 18" (Nietzsche). `_CITE_RE_DE` takes an Arabic
# chapter only (#703). A sibling for the reasons `en.py` gives: the
# chapter group is Roman-only so nothing is counted twice, the verse
# stays Arabic, and mixed-case numerals are rejected as OCR noise. The
# abbreviation keeps its period here — German always prints one, and
# requiring it keeps "Kap. IV, 3"-shaped prose behind the lexicon and a
# second gate.
_CITE_RE_DE_ROMAN = re.compile(
    r"(?:\b(?P<prefix>I{1,3}V?|[1-5])\.?\s*)?"  # optional ordinal
    r"\b(?P<abbr>[A-ZÄÖÜ][A-Za-zäöüß]{1,8})\."  # German abbrev
    r"\s*"
    r"(?P<chap>[ivxlc]{1,7}|[IVXLC]{1,7})"  # Roman chapter, one case
    r"\s*[,.]\s*"  # comma OR period sep
    r"(?P<verse>\d{1,3})"
    r"(?:\s*[-–]\s*\d{1,3})?"  # optional verse range
)


@dataclass(frozen=True)
class ScriptureCiteRuleDeRoman(BaseScriptureCiteRule):
    """German rule accepting a Roman-numeral chapter with an Arabic
    verse — Kant's *Religion* and Nietzsche's convention."""

    name: str = "scripture_cite_luther_de_roman"
    target_author: str = "Luther Bibel 1912"
    langs: tuple[str, ...] = ("deu",)

    lexicon = _LEXICON_DE
    cite_re = _CITE_RE_DE_ROMAN
    ambiguous_bare = _AMBIGUOUS_BARE_DE
