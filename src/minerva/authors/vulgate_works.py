"""Per-work configuration for the Clementine Vulgate ingest.

Source: ``github.com/BibleGet-I-O/Clementine-Vulgate`` — 73
per-book ``.lat`` files (Vulgate naming: ``Gn.lat``, ``Apc.lat``,
``Mch.lat``, etc.). Plain UTF-8, one verse per line.

Book titles use the canonical **English** forms shared with the
``new_testament_works`` and ``septuagint_works`` modules so that
cross-corpus cite resolution lands on the same ``book`` value in
``chunks`` regardless of which corpus carries the passage. The
Latin display title (e.g. "Liber Genesis", "Evangelium secundum
Matthaeum") would be nice but is deferred — when a UI wants Latin
labels it can derive them from the abbreviation.

Vulgate-specific conventions preserved by source:
* Vulgate Psalm numbering (Septuagint-derived) — Aquinas-compatible.
* Susanna and Bel as Daniel 13–14 (Dn.lat covers ch. 1–14).
* Letter of Jeremiah as Baruch ch. 6 (Bar.lat covers ch. 1–6).
* I-IV Regum → mapped to 1 Samuel / 2 Samuel / 1 Kings / 2 Kings
  (modern English book names), since downstream cross-references
  use those names regardless of corpus source.
"""

from __future__ import annotations

import dataclasses

from ..corpus_works import CorpusWork, make_find_work


@dataclasses.dataclass(frozen=True)
class _VulgateBook:
    """One Clementine Vulgate book.

    Kept private. ``WORKS`` is the public API; the splitter consults
    ``find_work`` / ``book_for_filename`` to dispatch by on-disk
    filename. ``title`` matches an entry in
    ``locations.BCV_BOOK_ORDINAL`` so cross-corpus sort works.
    """

    code: str  # snake_case slug
    title: str  # canonical English name (matches BCV table)
    filename: str  # Vulgate repo filename, e.g. "Gn.lat"


_BOOKS: tuple[_VulgateBook, ...] = (
    # ----- Pentateuch -----
    _VulgateBook("genesis", "Genesis", "Gn.lat"),
    _VulgateBook("exodus", "Exodus", "Ex.lat"),
    _VulgateBook("leviticus", "Leviticus", "Lv.lat"),
    _VulgateBook("numbers", "Numbers", "Nm.lat"),
    _VulgateBook("deuteronomy", "Deuteronomy", "Dt.lat"),
    # ----- Historical -----
    _VulgateBook("joshua", "Joshua", "Jos.lat"),
    _VulgateBook("judges", "Judges", "Jdc.lat"),
    _VulgateBook("ruth", "Ruth", "Rt.lat"),
    # I-IV Regum in the Vulgate maps to modern 1 Samuel through 2 Kings.
    _VulgateBook("1samuel", "1 Samuel", "1Rg.lat"),
    _VulgateBook("2samuel", "2 Samuel", "2Rg.lat"),
    _VulgateBook("1kings", "1 Kings", "3Rg.lat"),
    _VulgateBook("2kings", "2 Kings", "4Rg.lat"),
    _VulgateBook("1chronicles", "1 Chronicles", "1Par.lat"),
    _VulgateBook("2chronicles", "2 Chronicles", "2Par.lat"),
    _VulgateBook("ezra", "Ezra", "Esr.lat"),
    _VulgateBook("nehemiah", "Nehemiah", "Neh.lat"),
    _VulgateBook("tobit", "Tobit", "Tob.lat"),
    _VulgateBook("judith", "Judith", "Jdt.lat"),
    _VulgateBook("esther", "Esther", "Est.lat"),
    _VulgateBook("1maccabees", "1 Maccabees", "1Mcc.lat"),
    _VulgateBook("2maccabees", "2 Maccabees", "2Mcc.lat"),
    # ----- Wisdom -----
    _VulgateBook("job", "Job", "Job.lat"),
    _VulgateBook("psalms", "Psalms", "Ps.lat"),
    _VulgateBook("proverbs", "Proverbs", "Pr.lat"),
    _VulgateBook("ecclesiastes", "Ecclesiastes", "Ecl.lat"),
    _VulgateBook("song_of_songs", "Song of Songs", "Ct.lat"),
    _VulgateBook("wisdom", "Wisdom", "Sap.lat"),
    _VulgateBook("sirach", "Sirach", "Sir.lat"),
    # ----- Major prophets -----
    _VulgateBook("isaiah", "Isaiah", "Is.lat"),
    _VulgateBook("jeremiah", "Jeremiah", "Jr.lat"),
    _VulgateBook("lamentations", "Lamentations", "Lam.lat"),
    # Bar.lat carries Baruch 1–6; ch. 6 is the Letter of Jeremiah
    # in Vulgate convention. Stored under "Baruch" — a separate
    # "Letter of Jeremiah" CorpusWork would mis-align the chapter ordinal.
    _VulgateBook("baruch", "Baruch", "Bar.lat"),
    _VulgateBook("ezekiel", "Ezekiel", "Ez.lat"),
    # Dn.lat carries Daniel 1–14; ch. 13 is Susanna and ch. 14 is
    # Bel & the Dragon in Vulgate convention.
    _VulgateBook("daniel", "Daniel", "Dn.lat"),
    # ----- Minor prophets -----
    _VulgateBook("hosea", "Hosea", "Os.lat"),
    _VulgateBook("joel", "Joel", "Joel.lat"),
    _VulgateBook("amos", "Amos", "Am.lat"),
    _VulgateBook("obadiah", "Obadiah", "Abd.lat"),
    _VulgateBook("jonah", "Jonah", "Jon.lat"),
    _VulgateBook("micah", "Micah", "Mch.lat"),
    _VulgateBook("nahum", "Nahum", "Nah.lat"),
    _VulgateBook("habakkuk", "Habakkuk", "Hab.lat"),
    _VulgateBook("zephaniah", "Zephaniah", "Soph.lat"),
    _VulgateBook("haggai", "Haggai", "Agg.lat"),
    _VulgateBook("zechariah", "Zechariah", "Zach.lat"),
    _VulgateBook("malachi", "Malachi", "Mal.lat"),
    # ----- Gospels + Acts -----
    _VulgateBook("matthew", "Matthew", "Mt.lat"),
    _VulgateBook("mark", "Mark", "Mc.lat"),
    _VulgateBook("luke", "Luke", "Lc.lat"),
    _VulgateBook("john", "John", "Jo.lat"),
    _VulgateBook("acts", "Acts", "Act.lat"),
    # ----- Pauline epistles -----
    _VulgateBook("romans", "Romans", "Rom.lat"),
    _VulgateBook("1corinthians", "1 Corinthians", "1Cor.lat"),
    _VulgateBook("2corinthians", "2 Corinthians", "2Cor.lat"),
    _VulgateBook("galatians", "Galatians", "Gal.lat"),
    _VulgateBook("ephesians", "Ephesians", "Eph.lat"),
    _VulgateBook("philippians", "Philippians", "Phlp.lat"),
    _VulgateBook("colossians", "Colossians", "Col.lat"),
    _VulgateBook("1thessalonians", "1 Thessalonians", "1Thes.lat"),
    _VulgateBook("2thessalonians", "2 Thessalonians", "2Thes.lat"),
    _VulgateBook("1timothy", "1 Timothy", "1Tim.lat"),
    _VulgateBook("2timothy", "2 Timothy", "2Tim.lat"),
    _VulgateBook("titus", "Titus", "Tit.lat"),
    _VulgateBook("philemon", "Philemon", "Phlm.lat"),
    # ----- Hebrews -----
    _VulgateBook("hebrews", "Hebrews", "Hbr.lat"),
    # ----- Catholic epistles -----
    _VulgateBook("james", "James", "Jac.lat"),
    _VulgateBook("1peter", "1 Peter", "1Ptr.lat"),
    _VulgateBook("2peter", "2 Peter", "2Ptr.lat"),
    _VulgateBook("1john", "1 John", "1Jo.lat"),
    _VulgateBook("2john", "2 John", "2Jo.lat"),
    _VulgateBook("3john", "3 John", "3Jo.lat"),
    _VulgateBook("jude", "Jude", "Jud.lat"),
    # ----- Revelation -----
    _VulgateBook("revelation", "Revelation", "Apc.lat"),
)


WORKS: tuple[CorpusWork, ...] = tuple(
    CorpusWork(
        code=b.code,
        title=b.title,
        translator="(Original)",
        edition_year="1592",  # Clementine recension
        filenames=(b.filename,),
        fmt="txt",
        locator="vulgate",  # informational; dispatch is via vulgate.parse_dir
        lang="lat",
        corpus="vulgate",
        author="Vulgate",
        citation_system="bcv",
    )
    for b in _BOOKS
)


_BOOK_BY_FILENAME = {b.filename: b for b in _BOOKS}

find_work = make_find_work(WORKS)


def book_for_filename(filename: str) -> _VulgateBook | None:
    """Reverse-lookup used by the Vulgate splitter to translate
    on-disk filenames into canonical book titles."""
    return _BOOK_BY_FILENAME.get(filename)


def all_books() -> tuple[_VulgateBook, ...]:
    """For tooling / downloaders — every Vulgate book we ingest."""
    return _BOOKS
