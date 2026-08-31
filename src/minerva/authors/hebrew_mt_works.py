"""Per-work configuration for the Hebrew Masoretic Text ingest.

Source: Westminster Leningrad Codex via Open Scriptures Hebrew Bible
(OSHB) — github.com/openscriptures/morphhb, CC-BY 4.0. 39 books.

Citation system: ``bcv`` (shared with Septuagint / Vulgate / New
Testament). The English book names below match
``locations.BCV_BOOK_ORDINAL`` exactly so the same BCV section string
(``"Gen 1:1"``) lands on the same chunk across all four corpora —
that's the cross-corpus alignment the cross-references engine relies
on for LXX ↔ MT ↔ Vulgate.

The display order in the Reader sidebar follows the **Tanakh canon**
(Torah → Nevi'im → Ketuvim) via ``TANAKH_BOOK_ORDINAL`` in
``locations.py``; the per-book BCV ordinal is still used for sort
keys (so chunks sort with their LXX / Vulgate equivalents), but the
sidebar listing is Tanakh-ordered when the author is "Hebrew Bible".
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class _MTBook:
    """OSHB-side metadata for one Tanakh book.

    Carries three names for each book:

    * ``english`` — canonical name in the cross-corpus locator system
      (must match ``locations.BCV_BOOK_ORDINAL``). This is the chunk
      key — ``chunks.section`` strings like ``"Gen 1:1"`` resolve
      across MT / LXX / Vulgate because all three corpora use this
      same name. Never lowercase or stringify-modify it.
    * ``hebrew_script`` — the traditional Hebrew name in unpointed
      Hebrew script (בראשית, שמות, …). Used for the Reader heading
      and sidebar label.
    * ``hebrew_transliterated`` — Latin-script transliteration of
      the Hebrew name (Bereshit, Shemot, …). Used for the Reader
      heading subtitle alongside the English name.

    The display logic for the Hebrew Bible heading composes the
    subtitle as ``f"{hebrew_transliterated} · {english}"`` so the
    user sees both the romanization and the cross-corpus English id.
    """

    osis_filename: str  # OSHB filename (Gen.xml, 1Sam.xml, …)
    osis_id: str  # osisID prefix on each verse (Gen, 1Sam, …)
    english: str  # canonical BCV book name (Genesis, 1 Samuel, …)
    hebrew_script: str  # Hebrew script title (בראשית, שמות, …)
    hebrew_transliterated: str  # Latin-script transliteration (Bereshit, …)
    section: str  # Tanakh canon section: torah | neviim | ketuvim


# 39 books in Tanakh canonical order: Torah → Nevi'im (Former, then
# Latter, then Twelve) → Ketuvim (poetic books, megillot, late books).
# Hebrew script names use the unpointed (consonantal) form for
# titling — title niqqud is non-standard and the sidebar/heading
# reads cleaner without it. The pointed text is in the chunks
# themselves.
_BOOKS: tuple[_MTBook, ...] = (
    # ───────── Torah (Pentateuch) ─────────
    _MTBook("Gen.xml", "Gen", "Genesis", "בראשית", "Bereshit", "torah"),
    _MTBook("Exod.xml", "Exod", "Exodus", "שמות", "Shemot", "torah"),
    _MTBook("Lev.xml", "Lev", "Leviticus", "ויקרא", "Vayikra", "torah"),
    _MTBook("Num.xml", "Num", "Numbers", "במדבר", "Bamidbar", "torah"),
    _MTBook("Deut.xml", "Deut", "Deuteronomy", "דברים", "Devarim", "torah"),
    # ───────── Nevi'im — Former Prophets ─────────
    _MTBook("Josh.xml", "Josh", "Joshua", "יהושע", "Yehoshua", "neviim"),
    _MTBook("Judg.xml", "Judg", "Judges", "שופטים", "Shofetim", "neviim"),
    _MTBook("1Sam.xml", "1Sam", "1 Samuel", "שמואל א", "Shmuel I", "neviim"),
    _MTBook("2Sam.xml", "2Sam", "2 Samuel", "שמואל ב", "Shmuel II", "neviim"),
    _MTBook("1Kgs.xml", "1Kgs", "1 Kings", "מלכים א", "Melakhim I", "neviim"),
    _MTBook("2Kgs.xml", "2Kgs", "2 Kings", "מלכים ב", "Melakhim II", "neviim"),
    # ───────── Nevi'im — Latter Prophets (Major) ─────────
    _MTBook("Isa.xml", "Isa", "Isaiah", "ישעיה", "Yeshayahu", "neviim"),
    _MTBook("Jer.xml", "Jer", "Jeremiah", "ירמיה", "Yirmeyahu", "neviim"),
    _MTBook("Ezek.xml", "Ezek", "Ezekiel", "יחזקאל", "Yechezkel", "neviim"),
    # ───────── Nevi'im — The Twelve (Latter Minor) ─────────
    _MTBook("Hos.xml", "Hos", "Hosea", "הושע", "Hoshea", "neviim"),
    _MTBook("Joel.xml", "Joel", "Joel", "יואל", "Yoel", "neviim"),
    _MTBook("Amos.xml", "Amos", "Amos", "עמוס", "Amos", "neviim"),
    _MTBook("Obad.xml", "Obad", "Obadiah", "עבדיה", "Ovadyah", "neviim"),
    _MTBook("Jonah.xml", "Jonah", "Jonah", "יונה", "Yonah", "neviim"),
    _MTBook("Mic.xml", "Mic", "Micah", "מיכה", "Mikhah", "neviim"),
    _MTBook("Nah.xml", "Nah", "Nahum", "נחום", "Nachum", "neviim"),
    _MTBook("Hab.xml", "Hab", "Habakkuk", "חבקוק", "Chavakuk", "neviim"),
    _MTBook("Zeph.xml", "Zeph", "Zephaniah", "צפניה", "Tzefanyah", "neviim"),
    _MTBook("Hag.xml", "Hag", "Haggai", "חגי", "Chaggai", "neviim"),
    _MTBook("Zech.xml", "Zech", "Zechariah", "זכריה", "Zekharyah", "neviim"),
    _MTBook("Mal.xml", "Mal", "Malachi", "מלאכי", "Malakhi", "neviim"),
    # ───────── Ketuvim — Poetic ─────────
    _MTBook("Ps.xml", "Ps", "Psalms", "תהלים", "Tehillim", "ketuvim"),
    _MTBook("Prov.xml", "Prov", "Proverbs", "משלי", "Mishlei", "ketuvim"),
    _MTBook("Job.xml", "Job", "Job", "איוב", "Iyov", "ketuvim"),
    # ───────── Ketuvim — Five Megillot ─────────
    _MTBook("Song.xml", "Song", "Song of Songs", "שיר השירים", "Shir haShirim", "ketuvim"),
    _MTBook("Ruth.xml", "Ruth", "Ruth", "רות", "Ruth", "ketuvim"),
    _MTBook("Lam.xml", "Lam", "Lamentations", "איכה", "Eikhah", "ketuvim"),
    _MTBook("Eccl.xml", "Eccl", "Ecclesiastes", "קהלת", "Kohelet", "ketuvim"),
    _MTBook("Esth.xml", "Esth", "Esther", "אסתר", "Esther", "ketuvim"),
    # ───────── Ketuvim — Later Books ─────────
    _MTBook("Dan.xml", "Dan", "Daniel", "דניאל", "Daniel", "ketuvim"),
    _MTBook("Ezra.xml", "Ezra", "Ezra", "עזרא", "Ezra", "ketuvim"),
    _MTBook("Neh.xml", "Neh", "Nehemiah", "נחמיה", "Nechemyah", "ketuvim"),
    _MTBook("1Chr.xml", "1Chr", "1 Chronicles", "דברי הימים א", "Divrei haYamim I", "ketuvim"),
    _MTBook("2Chr.xml", "2Chr", "2 Chronicles", "דברי הימים ב", "Divrei haYamim II", "ketuvim"),
)


_BY_FILENAME: dict[str, _MTBook] = {b.osis_filename: b for b in _BOOKS}
_BY_OSIS_ID: dict[str, _MTBook] = {b.osis_id: b for b in _BOOKS}
_BY_ENGLISH: dict[str, _MTBook] = {b.english: b for b in _BOOKS}


def find_book(filename: str) -> _MTBook | None:
    """Lookup a book by OSHB filename. Returns ``None`` for unknown
    files (the parser logs and skips)."""
    return _BY_FILENAME.get(filename)


def find_book_by_osis_id(osis_id: str) -> _MTBook | None:
    """Lookup a book by the ``osisID`` prefix on a verse element."""
    return _BY_OSIS_ID.get(osis_id)


def find_book_by_english(name: str) -> _MTBook | None:
    """Lookup a book by its canonical English BCV name (Genesis,
    1 Samuel, …). Used by the Reader handler to look up Hebrew
    + transliterated display titles for the sidebar / heading."""
    return _BY_ENGLISH.get(name)


# Public list used by author_ordering + downloader integration tests.
BOOKS: tuple[_MTBook, ...] = _BOOKS
