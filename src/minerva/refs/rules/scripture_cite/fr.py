"""French Sacy scripture cite rules."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ._base import BaseScriptureCiteRule
from .de import ScriptureCiteRuleDe
from .en import ScriptureCiteRuleEn

_LEXICON_FR: dict[tuple[str | None, str], str] = {
    # Pentateuch — French abbrevs
    (None, "Gn"): "Genesis",
    (None, "Gen"): "Genesis",
    (None, "Ex"): "Exodus",
    (None, "Lv"): "Leviticus",
    (None, "Lév"): "Leviticus",
    (None, "Nb"): "Numbers",
    (None, "Nomb"): "Numbers",
    (None, "Dt"): "Deuteronomy",
    (None, "Deut"): "Deuteronomy",
    # Historical
    (None, "Jos"): "Joshua",
    (None, "Jg"): "Judges",
    (None, "Juges"): "Judges",
    (None, "Rt"): "Ruth",
    (None, "Ruth"): "Ruth",
    ("1", "S"): "1 Samuel",
    ("I", "Sam"): "1 Samuel",
    ("2", "S"): "2 Samuel",
    ("II", "Sam"): "2 Samuel",
    ("1", "R"): "1 Kings",
    ("I", "Rois"): "1 Kings",
    ("2", "R"): "2 Kings",
    ("II", "Rois"): "2 Kings",
    ("1", "Ch"): "1 Chronicles",
    ("I", "Chr"): "1 Chronicles",
    ("2", "Ch"): "2 Chronicles",
    ("II", "Chr"): "2 Chronicles",
    (None, "Esd"): "Ezra",
    (None, "Néh"): "Nehemiah",
    (None, "Neh"): "Nehemiah",
    (None, "Est"): "Esther",
    # Wisdom
    (None, "Jb"): "Job",
    (None, "Job"): "Job",
    (None, "Ps"): "Psalms",
    (None, "Pr"): "Proverbs",
    (None, "Prov"): "Proverbs",
    (None, "Ec"): "Ecclesiastes",
    (None, "Eccl"): "Ecclesiastes",
    (None, "Ct"): "Song of Songs",
    (None, "Cant"): "Song of Songs",
    # Major prophets
    (None, "Is"): "Isaiah",
    (None, "Isaïe"): "Isaiah",
    (None, "Jr"): "Jeremiah",
    (None, "Jér"): "Jeremiah",
    (None, "Lm"): "Lamentations",
    (None, "Lam"): "Lamentations",
    (None, "Ez"): "Ezekiel",
    (None, "Éz"): "Ezekiel",
    (None, "Dn"): "Daniel",
    (None, "Dan"): "Daniel",
    # Minor prophets
    (None, "Os"): "Hosea",
    (None, "Osée"): "Hosea",
    (None, "Jl"): "Joel",
    (None, "Joël"): "Joel",
    (None, "Am"): "Amos",
    (None, "Ab"): "Obadiah",
    (None, "Abd"): "Obadiah",
    (None, "Jon"): "Jonah",
    (None, "Mi"): "Micah",
    (None, "Mich"): "Micah",
    (None, "Na"): "Nahum",
    (None, "Ha"): "Habakkuk",
    (None, "Hab"): "Habakkuk",
    (None, "So"): "Zephaniah",
    (None, "Soph"): "Zephaniah",
    (None, "Ag"): "Haggai",
    (None, "Agg"): "Haggai",
    (None, "Za"): "Zechariah",
    (None, "Zach"): "Zechariah",
    (None, "Ml"): "Malachi",
    (None, "Mal"): "Malachi",
    # Apocrypha (Sacy is a Catholic Bible — deuterocanon included)
    (None, "Tb"): "Tobit",
    (None, "Tob"): "Tobit",
    (None, "Jdt"): "Judith",
    (None, "Sg"): "Wisdom",
    (None, "Sap"): "Wisdom",
    (None, "Si"): "Sirach",
    (None, "Sir"): "Sirach",
    (None, "Eccli"): "Sirach",
    (None, "Ba"): "Baruch",
    (None, "Bar"): "Baruch",
    ("1", "M"): "1 Maccabees",
    ("I", "Macc"): "1 Maccabees",
    ("2", "M"): "2 Maccabees",
    ("II", "Macc"): "2 Maccabees",
    # Gospels + Acts
    (None, "Mt"): "Matthew",
    (None, "Matth"): "Matthew",
    (None, "Mc"): "Mark",
    (None, "Marc"): "Mark",
    (None, "Lc"): "Luke",
    (None, "Luc"): "Luke",
    (None, "Jn"): "John",
    (None, "Jean"): "John",
    (None, "Ac"): "Acts",
    (None, "Act"): "Acts",
    # Pauline epistles
    (None, "Rm"): "Romans",
    (None, "Rom"): "Romans",
    ("1", "Co"): "1 Corinthians",
    ("I", "Cor"): "1 Corinthians",
    ("2", "Co"): "2 Corinthians",
    ("II", "Cor"): "2 Corinthians",
    (None, "Co"): "1 Corinthians",  # ambiguous-bare
    (None, "Ga"): "Galatians",
    (None, "Gal"): "Galatians",
    (None, "Ep"): "Ephesians",
    (None, "Eph"): "Ephesians",
    (None, "Ph"): "Philippians",
    (None, "Phil"): "Philippians",
    (None, "Col"): "Colossians",
    ("1", "Th"): "1 Thessalonians",
    ("I", "Thess"): "1 Thessalonians",
    ("2", "Th"): "2 Thessalonians",
    ("II", "Thess"): "2 Thessalonians",
    ("1", "Tm"): "1 Timothy",
    ("I", "Tim"): "1 Timothy",
    ("2", "Tm"): "2 Timothy",
    ("II", "Tim"): "2 Timothy",
    (None, "Tt"): "Titus",
    (None, "Tit"): "Titus",
    (None, "Phm"): "Philemon",
    (None, "Philém"): "Philemon",
    (None, "He"): "Hebrews",
    (None, "Héb"): "Hebrews",
    # Catholic epistles
    (None, "Jc"): "James",
    (None, "Jacq"): "James",
    (None, "Jac"): "James",
    ("1", "P"): "1 Peter",
    ("I", "Pierre"): "1 Peter",
    ("2", "P"): "2 Peter",
    ("II", "Pierre"): "2 Peter",
    ("1", "Jn"): "1 John",
    ("I", "Jean"): "1 John",
    ("2", "Jn"): "2 John",
    ("II", "Jean"): "2 John",
    ("3", "Jn"): "3 John",
    ("III", "Jean"): "3 John",
    (None, "Jude"): "Jude",
    (None, "Jud"): "Jude",
    # Revelation
    (None, "Ap"): "Revelation",
    (None, "Apoc"): "Revelation",
}


_AMBIGUOUS_BARE_FR: frozenset[str] = frozenset(
    {
        "Co",
        "Cor",
        "Th",
        "Thess",
        "Tm",
        "Tim",
        "P",
        "Pierre",
        "S",
        "Sam",
        "R",
        "Rois",
        "Ch",
        "Chr",
        "M",
        "Macc",
        "Jude",
        "Jud",
    }
)


# French regex tolerates BOTH "Rom 1, 18" (comma) AND "Rom 1:18" (colon)
# because Pascal mixes the two conventions across his work.
_CITE_RE_FR = re.compile(
    r"(?:\b(?P<prefix>I{1,3}V?|[1-3])\s*\.?\s*)?"
    r"\b(?P<abbr>[A-ZÉÈÀ][A-Za-zéèàç]{1,8})\.?"
    r"\s+"
    r"(?P<chap>\d{1,3})"
    r"\s*[,:]\s*"  # comma OR colon
    r"(?P<verse>\d{1,3})"
    r"(?:\s*[-–]\s*\d{1,3})?"
)


@dataclass(frozen=True)
class ScriptureCiteRuleFr(BaseScriptureCiteRule):
    """French scripture-citation rule (Sacy target).

    Used by Pascal/Rousseau rule modules. Tolerates both comma- and
    colon-separated chapter:verse forms because Pascal mixes them
    across the Pensées."""

    name: str = "scripture_cite_sacy_fr"
    target_author: str = "Sacy"
    langs: tuple[str, ...] = ("fra",)

    lexicon = _LEXICON_FR
    cite_re = _CITE_RE_FR
    ambiguous_bare = _AMBIGUOUS_BARE_FR


# 19th-c French scholarly convention (Renan's citations): a comma
# after the book name and the CHAPTER in lowercase Roman — "Luc,
# xxiii, 34", "Matth., xxvi, 39". `_parse_cite_num` in the base rule
# converts the Roman token; the lexicon gate on the book abbreviation
# keeps stray letter-runs from firing (a match needs a recognized
# book name AND a following digit verse).
_CITE_RE_FR_ROMAN = re.compile(
    # Chapters appear in lowercase ("Luc, xxiii") AND uppercase
    # ("Matth., XXIV") roman — the two alternates below don't allow
    # mixed case (mixed-case runs are OCR noise). Verses stay
    # digits-only: a roman verse group would swallow French "il"
    # ("Marc, ii, il dit…" → Mark 2:49).
    r"(?:\b(?P<prefix>I{1,3}V?|[1-3])\s*\.?\s*)?"
    r"\b(?P<abbr>[A-ZÉÈÀ][A-Za-zéèàç]{1,8})\.?,?"
    r"\s+"
    r"(?P<chap>\d{1,3}|[ivxlc]{1,7}|[IVXLC]{1,7})"
    r"\s*[,:.]\s*"
    r"(?P<verse>\d{1,3})"
    r"(?:\s*[-–]\s*\d{1,3})?"
)


@dataclass(frozen=True)
class ScriptureCiteRuleFrRoman(BaseScriptureCiteRule):
    """French rule accepting Roman-numeral chapters and a comma after
    the book abbreviation — the 19th-c convention Renan uses
    throughout (Vie de Jésus, L'Antéchrist, Histoire du peuple
    d'Israël)."""

    name: str = "scripture_cite_sacy_fr_roman"
    target_author: str = "Sacy"
    langs: tuple[str, ...] = ("fra",)

    lexicon = _LEXICON_FR
    cite_re = _CITE_RE_FR_ROMAN
    ambiguous_bare = _AMBIGUOUS_BARE_FR


def default_scripture_rules(
    prefix: str,
) -> tuple[BaseScriptureCiteRule, ...]:
    """Standard vernacular scripture cite rules for 19th-c authors.

    Includes DE + EN + both French shapes. Every rule is lang-gated,
    so a source corpus only ever fires the rules for languages it
    actually contains — including all four here used to silently
    hand a *French* author (Renan, via the YAML loader) only German
    and English rules, making ~1,265 cite-bearing chunks invisible."""
    return (
        ScriptureCiteRuleDe(name=f"{prefix}_scripture_cite_de"),
        ScriptureCiteRuleEn(name=f"{prefix}_scripture_cite_en"),
        ScriptureCiteRuleFr(name=f"{prefix}_scripture_cite_fr"),
        ScriptureCiteRuleFrRoman(name=f"{prefix}_scripture_cite_fr_roman"),
    )
