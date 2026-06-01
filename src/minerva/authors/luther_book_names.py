"""German display names for the Luther Bibel (1545 + 1912).

Maps the canonical English book title that the chunks store
(``work='Genesis'``, ``work='Psalms'``, ``work='Matthew'``) to the
German title the Reader heading + sidebar should render
(``display_title='1. Mose'``, ``display_title='Psalmen'``,
``display_title='Matthäus'``).

Conventions used here mirror the actual Luther typography:

* The Torah books are by tradition called ``1. Mose`` through
  ``5. Mose`` in the Luther Bibel — that's the heading the printed
  edition uses. We render that as the primary display title and put
  the Latin-derived alternative (``Genesis``/``Exodus``/…) in the
  English subtitle slot for clarity to non-German readers.
* Numbered series use ``1.``/``2.`` with a period (Luther house
  style), unlike the Vulgate's Roman numerals.
* The Pauline + catholic epistles drop the ``Brief des / Brief an``
  framing the Lutherbibel sometimes prefixes, since the bare
  addressee form (``Römer``, ``Galater``, ``Jakobus``) is what the
  Lutherbibel's running heads use.

The 1545 (Letzte-Hand, Frühneuhochdeutsch) and 1912 editions share
the same canon and the same modern-German book names — the 1545's
*orthography* is archaic (``Genesi``, ``Mose``, ``Psalter``) but
the printed running titles in modern reprints anglicise to the
standard names. Distinguishing 1545's archaic spellings here would
fight the modern user-facing UI for no retrieval benefit.
"""

from __future__ import annotations

# english title (= chunks_full.work) → German display title
_LUTHER_GERMAN: dict[str, str] = {
    # Pentateuch — Luther's "Bücher Mose"
    "Genesis": "1. Mose",
    "Exodus": "2. Mose",
    "Leviticus": "3. Mose",
    "Numbers": "4. Mose",
    "Deuteronomy": "5. Mose",
    # Historical books
    "Joshua": "Josua",
    "Judges": "Richter",
    "Ruth": "Rut",
    "1 Samuel": "1. Samuel",
    "2 Samuel": "2. Samuel",
    "1 Kings": "1. Könige",
    "2 Kings": "2. Könige",
    "1 Chronicles": "1. Chronik",
    "2 Chronicles": "2. Chronik",
    "Ezra": "Esra",
    "Nehemiah": "Nehemia",
    "Esther": "Ester",
    # Wisdom books
    "Job": "Hiob",
    "Psalms": "Psalmen",
    "Proverbs": "Sprüche",
    "Ecclesiastes": "Prediger",
    "Song of Songs": "Hohelied",
    # Prophets
    "Isaiah": "Jesaja",
    "Jeremiah": "Jeremia",
    "Lamentations": "Klagelieder",
    "Ezekiel": "Hesekiel",
    "Daniel": "Daniel",
    "Hosea": "Hosea",
    "Joel": "Joel",
    "Amos": "Amos",
    "Obadiah": "Obadja",
    "Jonah": "Jona",
    "Micah": "Micha",
    "Nahum": "Nahum",
    "Habakkuk": "Habakuk",
    "Zephaniah": "Zefanja",
    "Haggai": "Haggai",
    "Zechariah": "Sacharja",
    "Malachi": "Maleachi",
    # Gospels
    "Matthew": "Matthäus",
    "Mark": "Markus",
    "Luke": "Lukas",
    "John": "Johannes",
    # Acts + Pauline epistles
    "Acts": "Apostelgeschichte",
    "Romans": "Römer",
    "1 Corinthians": "1. Korinther",
    "2 Corinthians": "2. Korinther",
    "Galatians": "Galater",
    "Ephesians": "Epheser",
    "Philippians": "Philipper",
    "Colossians": "Kolosser",
    "1 Thessalonians": "1. Thessalonicher",
    "2 Thessalonians": "2. Thessalonicher",
    "1 Timothy": "1. Timotheus",
    "2 Timothy": "2. Timotheus",
    "Titus": "Titus",
    "Philemon": "Philemon",
    "Hebrews": "Hebräer",
    # Catholic epistles
    "James": "Jakobus",
    "1 Peter": "1. Petrus",
    "2 Peter": "2. Petrus",
    "1 John": "1. Johannes",
    "2 John": "2. Johannes",
    "3 John": "3. Johannes",
    "Jude": "Judas",
    # Apocalypse
    "Revelation": "Offenbarung",
}


def german_name(english_work: str) -> str | None:
    """Return the Lutherbibel's German title for an English book
    name. ``None`` for works outside the canonical 66 (the
    Lutherbibel canon excludes the OT Apocrypha that the Vulgate
    keeps); caller falls back to the English title."""

    return _LUTHER_GERMAN.get(english_work)
