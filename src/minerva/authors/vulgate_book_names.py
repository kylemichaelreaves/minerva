"""Latin display names for the Clementine Vulgate's 73 books.

Maps the canonical English-script book title that the chunks store
(``work='Genesis'``, ``work='1 Samuel'``, ``work='Matthew'``) to the
Latin title used by Reader heading + sidebar
(``display_title='Genesis'``, ``display_title='I Samuelis'``,
``display_title='Evangelium secundum Matthaeum'``).

Conventions:

* Pentateuch and small-name books keep their Latin spellings
  (``Genesis``, ``Exodus``, ``Iob``, ``Iudith``).
* Numbered series use Roman-numeral prefixes — that's the convention
  the Clementine Vulgate prints (``I Samuelis`` not ``1 Samuelis``).
* Gospels render with the full ``Evangelium secundum X`` formula
  since that's how the Vulgate titles them.
* Pauline epistles use the ``Ad <addressee>`` shape; catholic
  epistles use the genitive (``Epistula Iacobi`` shortens to
  ``Iacobi``).
* Apocalypse takes its Greek-loanword title.

The Reader API renders these as ``display_title`` (Latin); the
English book name continues to live in ``display_subtitle`` so a
non-Latinist can still browse the sidebar.
"""

from __future__ import annotations

# english title (= chunks_full.work) → Latin display title
_VULGATE_LATIN: dict[str, str] = {
    # Pentateuch
    "Genesis": "Genesis",
    "Exodus": "Exodus",
    "Leviticus": "Leviticus",
    "Numbers": "Numeri",
    "Deuteronomy": "Deuteronomium",
    # Historical books
    "Joshua": "Iosue",
    "Judges": "Iudices",
    "Ruth": "Ruth",
    "1 Samuel": "I Samuelis",
    "2 Samuel": "II Samuelis",
    "1 Kings": "I Regum",
    "2 Kings": "II Regum",
    "1 Chronicles": "I Paralipomenon",
    "2 Chronicles": "II Paralipomenon",
    "Ezra": "Esdrae",
    "Nehemiah": "Nehemiae",
    "Tobit": "Tobiae",
    "Judith": "Iudith",
    "Esther": "Esther",
    "1 Maccabees": "I Machabaeorum",
    "2 Maccabees": "II Machabaeorum",
    # Wisdom books
    "Job": "Iob",
    "Psalms": "Psalmi",
    "Proverbs": "Proverbia",
    "Ecclesiastes": "Ecclesiastes",
    "Song of Songs": "Canticum Canticorum",
    "Wisdom": "Sapientia",
    "Sirach": "Ecclesiasticus",
    # Prophets
    "Isaiah": "Isaias",
    "Jeremiah": "Ieremias",
    "Lamentations": "Lamentationes",
    "Baruch": "Baruch",
    "Ezekiel": "Ezechiel",
    "Daniel": "Daniel",
    "Hosea": "Osee",
    "Joel": "Ioel",
    "Amos": "Amos",
    "Obadiah": "Abdias",
    "Jonah": "Ionas",
    "Micah": "Michaeas",
    "Nahum": "Nahum",
    "Habakkuk": "Habacuc",
    "Zephaniah": "Sophonias",
    "Haggai": "Aggaeus",
    "Zechariah": "Zacharias",
    "Malachi": "Malachias",
    # Gospels
    "Matthew": "Evangelium secundum Matthaeum",
    "Mark": "Evangelium secundum Marcum",
    "Luke": "Evangelium secundum Lucam",
    "John": "Evangelium secundum Ioannem",
    # Acts + Pauline epistles
    "Acts": "Actus Apostolorum",
    "Romans": "Ad Romanos",
    "1 Corinthians": "I ad Corinthios",
    "2 Corinthians": "II ad Corinthios",
    "Galatians": "Ad Galatas",
    "Ephesians": "Ad Ephesios",
    "Philippians": "Ad Philippenses",
    "Colossians": "Ad Colossenses",
    "1 Thessalonians": "I ad Thessalonicenses",
    "2 Thessalonians": "II ad Thessalonicenses",
    "1 Timothy": "I ad Timotheum",
    "2 Timothy": "II ad Timotheum",
    "Titus": "Ad Titum",
    "Philemon": "Ad Philemonem",
    "Hebrews": "Ad Hebraeos",
    # Catholic epistles
    "James": "Iacobi",
    "1 Peter": "I Petri",
    "2 Peter": "II Petri",
    "1 John": "I Ioannis",
    "2 John": "II Ioannis",
    "3 John": "III Ioannis",
    "Jude": "Iudae",
    # Apocalypse
    "Revelation": "Apocalypsis",
}


def latin_name(english_work: str) -> str | None:
    """Return the Vulgate's Latin title for an English book name.
    ``None`` when the work isn't in the canonical 73-book set
    (caller falls back to the English title)."""

    return _VULGATE_LATIN.get(english_work)
