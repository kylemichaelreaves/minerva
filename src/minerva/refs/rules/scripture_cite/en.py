"""English KJV scripture cite rules."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from .. import Candidate, ChunkInfo
from .lexicon import _CONF_AMBIGUOUS, _CONF_FULL, _sbl_abbr_for

_LEXICON_EN: dict[tuple[str | None, str], str] = {
    # ── Pentateuch ────────────────────────────────────────────────
    (None, "Gen"): "Genesis",
    (None, "Ex"): "Exodus", (None, "Exod"): "Exodus",
    (None, "Lev"): "Leviticus",
    (None, "Num"): "Numbers",
    (None, "Deut"): "Deuteronomy", (None, "Dt"): "Deuteronomy",
    # ── Historical ────────────────────────────────────────────────
    (None, "Josh"): "Joshua", (None, "Jos"): "Joshua",
    (None, "Judg"): "Judges", (None, "Jdg"): "Judges",
    (None, "Ruth"): "Ruth", (None, "Rth"): "Ruth",
    ("1", "Sam"): "1 Samuel", ("I", "Sam"): "1 Samuel",
    ("2", "Sam"): "2 Samuel", ("II", "Sam"): "2 Samuel",
    ("1", "Kgs"): "1 Kings", ("I", "Kgs"): "1 Kings",
    ("1", "Kings"): "1 Kings", ("I", "Kings"): "1 Kings",
    ("2", "Kgs"): "2 Kings", ("II", "Kgs"): "2 Kings",
    ("2", "Kings"): "2 Kings", ("II", "Kings"): "2 Kings",
    ("1", "Chr"): "1 Chronicles", ("I", "Chr"): "1 Chronicles",
    ("1", "Chron"): "1 Chronicles", ("I", "Chron"): "1 Chronicles",
    ("2", "Chr"): "2 Chronicles", ("II", "Chr"): "2 Chronicles",
    ("2", "Chron"): "2 Chronicles", ("II", "Chron"): "2 Chronicles",
    (None, "Ezra"): "Ezra",
    (None, "Neh"): "Nehemiah",
    (None, "Esth"): "Esther", (None, "Est"): "Esther",
    # ── Wisdom ────────────────────────────────────────────────────
    (None, "Job"): "Job",
    (None, "Ps"): "Psalms", (None, "Psa"): "Psalms", (None, "Psalm"): "Psalms",
    (None, "Prov"): "Proverbs", (None, "Pr"): "Proverbs",
    (None, "Eccl"): "Ecclesiastes", (None, "Ecc"): "Ecclesiastes",
    (None, "Song"): "Song of Songs", (None, "Cant"): "Song of Songs",
    # ── Major prophets ────────────────────────────────────────────
    (None, "Isa"): "Isaiah", (None, "Is"): "Isaiah",
    (None, "Jer"): "Jeremiah",
    (None, "Lam"): "Lamentations",
    (None, "Ezek"): "Ezekiel", (None, "Ez"): "Ezekiel",
    (None, "Dan"): "Daniel",
    # ── Minor prophets ────────────────────────────────────────────
    (None, "Hos"): "Hosea",
    (None, "Joel"): "Joel",
    (None, "Am"): "Amos", (None, "Amos"): "Amos",
    (None, "Obad"): "Obadiah", (None, "Ob"): "Obadiah",
    (None, "Jon"): "Jonah", (None, "Jonah"): "Jonah",
    (None, "Mic"): "Micah",
    (None, "Nah"): "Nahum",
    (None, "Hab"): "Habakkuk",
    (None, "Zeph"): "Zephaniah", (None, "Zep"): "Zephaniah",
    (None, "Hag"): "Haggai",
    (None, "Zech"): "Zechariah", (None, "Zec"): "Zechariah",
    (None, "Mal"): "Malachi",
    # ── Apocrypha (1611 KJV included; modern KJV often omits) ─────
    (None, "Tob"): "Tobit",
    (None, "Jdt"): "Judith",
    (None, "Wis"): "Wisdom", (None, "Wisd"): "Wisdom",
    (None, "Sir"): "Sirach", (None, "Ecclus"): "Sirach",
    (None, "Bar"): "Baruch",
    ("1", "Macc"): "1 Maccabees", ("I", "Macc"): "1 Maccabees",
    ("2", "Macc"): "2 Maccabees", ("II", "Macc"): "2 Maccabees",
    # ── Gospels + Acts ────────────────────────────────────────────
    (None, "Mt"): "Matthew", (None, "Matt"): "Matthew",
    (None, "Mk"): "Mark", (None, "Mark"): "Mark",
    (None, "Lk"): "Luke", (None, "Lu"): "Luke", (None, "Luke"): "Luke",
    (None, "Jn"): "John", (None, "John"): "John", (None, "Joh"): "John",
    (None, "Acts"): "Acts", (None, "Ac"): "Acts",
    # ── Pauline epistles ──────────────────────────────────────────
    (None, "Rom"): "Romans",
    ("1", "Cor"): "1 Corinthians", ("I", "Cor"): "1 Corinthians",
    ("2", "Cor"): "2 Corinthians", ("II", "Cor"): "2 Corinthians",
    (None, "Cor"): "1 Corinthians",  # ambiguous-bare
    (None, "Gal"): "Galatians",
    (None, "Eph"): "Ephesians",
    (None, "Phil"): "Philippians", (None, "Phi"): "Philippians",
    (None, "Col"): "Colossians",
    ("1", "Thess"): "1 Thessalonians", ("I", "Thess"): "1 Thessalonians",
    ("2", "Thess"): "2 Thessalonians", ("II", "Thess"): "2 Thessalonians",
    ("1", "Tim"): "1 Timothy", ("I", "Tim"): "1 Timothy",
    ("2", "Tim"): "2 Timothy", ("II", "Tim"): "2 Timothy",
    (None, "Tim"): "1 Timothy",  # ambiguous-bare
    (None, "Tit"): "Titus", (None, "Titus"): "Titus",
    (None, "Phlm"): "Philemon", (None, "Phm"): "Philemon",
    (None, "Heb"): "Hebrews", (None, "Hebr"): "Hebrews",
    # ── Catholic epistles ─────────────────────────────────────────
    (None, "Jas"): "James", (None, "James"): "James",
    ("1", "Pet"): "1 Peter", ("I", "Pet"): "1 Peter",
    ("2", "Pet"): "2 Peter", ("II", "Pet"): "2 Peter",
    (None, "Pet"): "1 Peter",  # ambiguous-bare
    ("1", "Jn"): "1 John", ("I", "Jn"): "1 John",
    ("1", "John"): "1 John", ("I", "John"): "1 John",
    ("2", "Jn"): "2 John", ("II", "Jn"): "2 John",
    ("3", "Jn"): "3 John", ("III", "Jn"): "3 John",
    (None, "Jude"): "Jude",
    # ── Revelation ────────────────────────────────────────────────
    (None, "Rev"): "Revelation", (None, "Apoc"): "Revelation",
}


_AMBIGUOUS_BARE_EN: frozenset[str] = frozenset(
    {"Cor", "Pet", "Tim", "Thess", "Sam", "Kgs", "Kings", "Chr",
     "Chron", "Macc", "Joh"}
)


# English chap-verse separator: modern usage is colon ("Matt 5:48");
# 17th-c. English (Hobbes Leviathan, Locke) frequently uses period
# ("Gen. 3. 5", "Mark 3.21", "Rom. 8.9."). Accept both. We require
# the abbrev to start with an uppercase Latin letter to skip e.g.
# clause numbering in modern editions.
_CITE_RE_EN = re.compile(
    r"(?:\b(?P<prefix>I{1,3}V?|[1-3])\s*\.?\s*)?"  # optional ordinal
    r"\b(?P<abbr>[A-Z][a-z]{1,8})\.?"              # English abbrev
    r"\s+"
    r"(?P<chap>\d{1,3})"
    r"\s*[:.]\s*"                                   # colon OR period sep
    r"(?P<verse>\d{1,3})"
    r"(?:\s*[-–]\s*\d{1,3})?"                       # optional verse range
)


@dataclass(frozen=True)
class ScriptureCiteRuleEn:
    """English scripture-citation rule (KJV target).

    Used by Hobbes/Locke/Hume rule modules. Same Candidate shape and
    binding pipeline as the Latin and German variants."""

    name: str = "scripture_cite_kjv_en"
    target_author: str = "King James Bible"
    langs: tuple[str, ...] = ("eng",)
    _key: str = field(init=False, default="")

    def __post_init__(self) -> None:
        object.__setattr__(self, "_key", f"scripture_cite_en/{self.name}")

    def scan(self, chunk: ChunkInfo) -> Iterable[Candidate]:
        if self.langs and chunk.lang not in self.langs:
            return
        if chunk.author == self.target_author:
            return
        for m in _CITE_RE_EN.finditer(chunk.text):
            prefix = m.group("prefix")
            abbr = m.group("abbr")
            book = _LEXICON_EN.get((prefix, abbr))
            if book is None:
                continue
            sbl = _sbl_abbr_for(book)
            if sbl is None:
                continue

            chap = int(m.group("chap"))
            verse = int(m.group("verse"))
            target_locator = f"{sbl} {chap}:{verse}"
            conf = _CONF_FULL
            if prefix is None and abbr in _AMBIGUOUS_BARE_EN:
                conf = _CONF_AMBIGUOUS

            yield Candidate(
                source_chunk_id=chunk.chunk_id,
                source_span_start=m.start(),
                source_span_end=m.end(),
                source_form_snapshot=m.group(0),
                target_author=self.target_author,
                target_work=book,
                target_locator=target_locator,
                reference_type="cites",
                confidence=conf,
                source_method="rule_strong" if conf >= 0.85 else "rule_weak",
            )
