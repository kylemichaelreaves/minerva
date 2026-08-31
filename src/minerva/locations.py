"""Structured locators for term occurrences.

The schema stores a locator as a discriminator (`location_kind`) plus a
JSON payload (`location_payload`) and a denormalized canonical-orderable
sort key (`location_sort_key`). This module is the single source of
truth for both shapes: it validates payloads and emits sort keys.

Versioning policy
-----------------
The sort-key encoding is identified by ``SORT_KEY_VERSION``. A change
to any of the per-kind encoders MUST bump this constant. The bump is
the signal that every previously-curated ``term_occurrences`` row holds
a stale ``location_sort_key`` and needs reindexing — there is no
implicit migration. The follow-on operation is to scan the table, parse
each ``location_payload``, recompute ``location_sort_key`` with the new
version, and write it back. That's an explicit reindex event, not
something the runtime should patch over.

Add a new citation system the same way:
1. add a key under :data:`SORT_KEY_FORMATTERS`,
2. add a CHECK-constraint entry in the schema migration that introduces
   it,
3. bump :data:`SORT_KEY_VERSION` if any existing kind's encoding
   changes — adding a fresh kind doesn't require a bump.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

# Bump this when ANY existing sort-key encoder changes. Adding a NEW
# kind doesn't require a bump (existing rows' sort keys remain valid;
# the new kind has no rows yet).
SORT_KEY_VERSION = 1


class LocationError(ValueError):
    """Payload doesn't satisfy the schema for its declared kind."""


# ---------- bcv canonical book table ----------
#
# Maps full English book name → (ordinal, SBL-style short abbreviation).
# Used by the `bcv` sort-key encoder and the section-string parser.
# Ordering follows the Catholic-canon Vulgate order through book 73
# (Revelation), then extends with LXX-only books (Psalm 151 placed at
# 23.5 by ordinal slot in the Psalms vicinity is too clever — keep
# them numerically after Revelation so existing sort positions don't
# shift if more LXX-only books are added).
#
# The ordinal is the sort-key prefix; the abbreviation is what we
# parse from `chunks.section` strings like "Gen 1:1". Keep both
# stable — they're embedded in the sort key and in stored locator
# strings respectively.

_BCV_BOOKS: tuple[tuple[str, int, str], ...] = (
    # ----- Pentateuch / Torah -----
    ("Genesis", 1, "Gen"),
    ("Exodus", 2, "Exod"),
    ("Leviticus", 3, "Lev"),
    ("Numbers", 4, "Num"),
    ("Deuteronomy", 5, "Deut"),
    # ----- Historical books -----
    ("Joshua", 6, "Josh"),
    ("Judges", 7, "Judg"),
    ("Ruth", 8, "Ruth"),
    ("1 Samuel", 9, "1Sam"),
    ("2 Samuel", 10, "2Sam"),
    ("1 Kings", 11, "1Kgs"),
    ("2 Kings", 12, "2Kgs"),
    ("1 Chronicles", 13, "1Chr"),
    ("2 Chronicles", 14, "2Chr"),
    ("Ezra", 15, "Ezra"),
    ("Nehemiah", 16, "Neh"),
    ("Tobit", 17, "Tob"),
    ("Judith", 18, "Jdt"),
    ("Esther", 19, "Esth"),
    ("1 Maccabees", 20, "1Macc"),
    ("2 Maccabees", 21, "2Macc"),
    # ----- Wisdom -----
    ("Job", 22, "Job"),
    ("Psalms", 23, "Ps"),
    ("Proverbs", 24, "Prov"),
    ("Ecclesiastes", 25, "Eccl"),
    ("Song of Songs", 26, "Song"),
    ("Wisdom", 27, "Wis"),
    ("Sirach", 28, "Sir"),
    # ----- Prophets -----
    ("Isaiah", 29, "Isa"),
    ("Jeremiah", 30, "Jer"),
    ("Lamentations", 31, "Lam"),
    ("Baruch", 32, "Bar"),
    ("Ezekiel", 33, "Ezek"),
    ("Daniel", 34, "Dan"),
    ("Hosea", 35, "Hos"),
    ("Joel", 36, "Joel"),
    ("Amos", 37, "Amos"),
    ("Obadiah", 38, "Obad"),
    ("Jonah", 39, "Jonah"),
    ("Micah", 40, "Mic"),
    ("Nahum", 41, "Nah"),
    ("Habakkuk", 42, "Hab"),
    ("Zephaniah", 43, "Zeph"),
    ("Haggai", 44, "Hag"),
    ("Zechariah", 45, "Zech"),
    ("Malachi", 46, "Mal"),
    # ----- New Testament -----
    ("Matthew", 47, "Matt"),
    ("Mark", 48, "Mark"),
    ("Luke", 49, "Luke"),
    ("John", 50, "John"),
    ("Acts", 51, "Acts"),
    ("Romans", 52, "Rom"),
    ("1 Corinthians", 53, "1Cor"),
    ("2 Corinthians", 54, "2Cor"),
    ("Galatians", 55, "Gal"),
    ("Ephesians", 56, "Eph"),
    ("Philippians", 57, "Phil"),
    ("Colossians", 58, "Col"),
    ("1 Thessalonians", 59, "1Thess"),
    ("2 Thessalonians", 60, "2Thess"),
    ("1 Timothy", 61, "1Tim"),
    ("2 Timothy", 62, "2Tim"),
    ("Titus", 63, "Titus"),
    ("Philemon", 64, "Phlm"),
    ("Hebrews", 65, "Heb"),
    ("James", 66, "Jas"),
    ("1 Peter", 67, "1Pet"),
    ("2 Peter", 68, "2Pet"),
    ("1 John", 69, "1John"),
    ("2 John", 70, "2John"),
    ("3 John", 71, "3John"),
    ("Jude", 72, "Jude"),
    ("Revelation", 73, "Rev"),
    # ----- LXX-only / appendices (ordinals continue from 74 so
    # earlier slots stay stable as additions accrue). -----
    ("1 Esdras", 74, "1Esd"),
    ("2 Esdras", 75, "2Esd"),
    ("3 Maccabees", 76, "3Macc"),
    ("4 Maccabees", 77, "4Macc"),
    ("Prayer of Manasseh", 78, "PrMan"),
    ("Psalm 151", 79, "Ps151"),
    ("Letter of Jeremiah", 80, "EpJer"),
    ("Odes", 81, "Ode"),
    ("Psalms of Solomon", 82, "PsSol"),
    # Susanna and Bel & the Dragon appear in the LXX as standalone
    # works (Swete prints them separately); the Vulgate treats them
    # as Daniel 13–14. Stored separately here so LXX cites resolve;
    # Vulgate cites to "Dan 13" / "Dan 14" can be aliased later.
    ("Susanna", 83, "Sus"),
    ("Bel and the Dragon", 84, "Bel"),
    # Swete's "Esdras II" — the combined Ezra+Nehemiah work as the LXX
    # transmits it. Distinct from the standalone Ezra (15) and Nehemiah
    # (16) entries above, which the Vulgate splits.
    ("Ezra-Nehemiah", 85, "EzraNeh"),
)


BCV_BOOK_ORDINAL: dict[str, int] = {name: ordinal for name, ordinal, _abbr in _BCV_BOOKS}
BCV_BOOK_ABBR: dict[str, str] = {name: abbr for name, _ordinal, abbr in _BCV_BOOKS}
# Reverse lookup so the section-string parser can map "Gen" → "Genesis".
BCV_ABBR_TO_BOOK: dict[str, str] = {abbr: name for name, _ordinal, abbr in _BCV_BOOKS}


# ---------- Tanakh canonical order ----------
#
# The Hebrew Bible orders books Torah → Nevi'im → Ketuvim — a
# different canonical sequence from the Christian / Vulgate order
# encoded in ``BCV_BOOK_ORDINAL``. We keep ``BCV_BOOK_ORDINAL`` as
# the cross-corpus alignment key (so a Gen 1:1 chunk in MT sorts
# with its LXX/Vulgate equivalents), and use ``TANAKH_BOOK_ORDINAL``
# only for the Reader sidebar's display order when the author is
# "Hebrew Bible".
#
# The book names below match ``BCV_BOOK_ORDINAL`` exactly so the
# locator-system contract (Gen 1:1 ↔ same chunk across corpora)
# stays intact. Books that the Tanakh does not include (Tobit,
# Judith, the Maccabees, the New Testament, the LXX-only
# appendices) are simply absent from this table.
_TANAKH_BOOKS: tuple[str, ...] = (
    # Torah
    "Genesis",
    "Exodus",
    "Leviticus",
    "Numbers",
    "Deuteronomy",
    # Nevi'im — Former Prophets
    "Joshua",
    "Judges",
    "1 Samuel",
    "2 Samuel",
    "1 Kings",
    "2 Kings",
    # Nevi'im — Latter Prophets (Major)
    "Isaiah",
    "Jeremiah",
    "Ezekiel",
    # Nevi'im — The Twelve (Latter Minor)
    "Hosea",
    "Joel",
    "Amos",
    "Obadiah",
    "Jonah",
    "Micah",
    "Nahum",
    "Habakkuk",
    "Zephaniah",
    "Haggai",
    "Zechariah",
    "Malachi",
    # Ketuvim — Poetic
    "Psalms",
    "Proverbs",
    "Job",
    # Ketuvim — Five Megillot
    "Song of Songs",
    "Ruth",
    "Lamentations",
    "Ecclesiastes",
    "Esther",
    # Ketuvim — Later books
    "Daniel",
    "Ezra",
    "Nehemiah",
    "1 Chronicles",
    "2 Chronicles",
)
TANAKH_BOOK_ORDINAL: dict[str, int] = {name: i for i, name in enumerate(_TANAKH_BOOKS, start=1)}


# ---------- per-kind formatters ----------
#
# Each formatter takes the payload dict and returns the
# canonically-orderable string. The dict's `kind` field (if present) is
# ignored; the caller already routed on it. The sort key embeds a
# single-letter system prefix so cross-kind ORDER BY produces a stable
# (if not philologically meaningful) order — useful in admin queries.


def _stephanus(p: dict[str, Any]) -> str:
    # Plato (and Stephanus-paginated Aristotle): {page: 514, section: 'a'}.
    page = _require_int(p, "page", minimum=1, maximum=9999)
    section = _require_choice(p, "section", choices=("a", "b", "c", "d", "e"))
    return f"S{page:04d}{section}"


def _bekker(p: dict[str, Any]) -> str:
    # Aristotle: {page: 1094, column: 'a' | 'b', line: 1..40}.
    page = _require_int(p, "page", minimum=1, maximum=9999)
    column = _require_choice(p, "column", choices=("a", "b"))
    line = _require_int(p, "line", minimum=1, maximum=200)
    return f"B{page:04d}{column}{line:03d}"


def _kant_ab(p: dict[str, Any]) -> str:
    # Kant 1st Critique: {edition: 'A' | 'B', page: 1..900}.
    # A1 sorts before B1 — useful when both editions cite the same passage.
    edition = _require_choice(p, "edition", choices=("A", "B"))
    page = _require_int(p, "page", minimum=1, maximum=999)
    return f"K{edition}{page:04d}"


def _sz_marginal(p: dict[str, Any]) -> str:
    # Heidegger, Sein und Zeit marginal pagination: {page: 1..438}.
    page = _require_int(p, "page", minimum=1, maximum=999)
    return f"H{page:04d}"


def _paragraph(p: dict[str, Any]) -> str:
    # Hegel, Husserl, etc.: {symbol: '§' | '¶', number: 1.., suffix?: str}.
    symbol = _require_choice(p, "symbol", choices=("§", "¶"))
    number = _require_int(p, "number", minimum=1, maximum=9999)
    suffix = p.get("suffix") or ""
    if suffix and not isinstance(suffix, str):
        raise LocationError(f"paragraph suffix must be a string, got {type(suffix).__name__}")
    return f"P{symbol}{number:05d}{suffix}"


def _surah_ayah(p: dict[str, Any]) -> str:
    # Quran surah:ayah — {surah: 1..114, ayah: 0..286, ayah_suffix?: ""}.
    # The Quran has fixed canonical surah numbering (1=Al-Fatiha,
    # 114=An-Nas) and ayah numbering inside each surah; no book-name
    # lookup is needed, unlike bcv. ``ayah=0`` accommodates the
    # Basmala-as-first-line convention some editions adopt (Surah 1
    # ayah 0); standard Uthmani numbering starts ayahs at 1. Suffix
    # is reserved for variant-numbering systems that split a single
    # ayah across multiple chunks; unused in the baseline ingest.
    surah = _require_int(p, "surah", minimum=1, maximum=114)
    ayah = _require_int(p, "ayah", minimum=0, maximum=300)
    suffix = p.get("ayah_suffix") or ""
    if suffix and not isinstance(suffix, str):
        raise LocationError(f"surah_ayah ayah_suffix must be a string, got {type(suffix).__name__}")
    return f"Q{surah:03d}{ayah:04d}{suffix}"


def _bcv(p: dict[str, Any]) -> str:
    # Biblical book:chapter:verse — {book: "Genesis", chapter: 1,
    # verse: 1, verse_suffix?: "a"|"b"|...}. The book is the
    # canonical English name (full, not the SBL abbreviation) which
    # we look up in `BCV_BOOK_ORDINAL` to get a stable 3-digit
    # ordinal that orders LXX, NT, and Vulgate consistently. Verse
    # supports an optional alpha suffix for Esther A-F additions,
    # Daniel 3 (Song of the Three Youths), etc.
    book = p.get("book")
    if not isinstance(book, str) or not book:
        raise LocationError(f"bcv book must be a non-empty string, got {book!r}")
    ordinal = BCV_BOOK_ORDINAL.get(book)
    if ordinal is None:
        raise LocationError(
            f"bcv book {book!r} not in canonical table; valid books: {sorted(BCV_BOOK_ORDINAL)}"
        )
    chapter = _require_int(p, "chapter", minimum=0, maximum=200)
    verse = _require_int(p, "verse", minimum=0, maximum=300)
    suffix = p.get("verse_suffix") or ""
    if suffix and not isinstance(suffix, str):
        raise LocationError(f"bcv verse_suffix must be a string, got {type(suffix).__name__}")
    return f"V{ordinal:03d}{chapter:04d}{verse:04d}{suffix}"


SORT_KEY_FORMATTERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "stephanus": _stephanus,
    "bekker": _bekker,
    "kant_ab": _kant_ab,
    "sz_marginal": _sz_marginal,
    "paragraph": _paragraph,
    "bcv": _bcv,
    "surah_ayah": _surah_ayah,
}


# ---------- section-string parsers ----------
#
# Inverse of the formatters above: take the locator string stored in
# `chunks.section` (Stephanus '514a', paragraph '§44', etc.) and
# return the structured payload + sort key. Used by the curator CLI
# when tagging an occurrence — the curator names a section, we
# compute the payload from the work's citation_system.


_STEPHANUS_SECTION_RE = re.compile(r"^\s*(\d+)\s*([a-e])\s*$")
_BEKKER_SECTION_RE = re.compile(r"^\s*(\d+)\s*([ab])\s*(\d+)?\s*$")
_KANT_AB_SECTION_RE = re.compile(r"^\s*([AB])\s*(\d+)\s*$")
_SZ_MARGINAL_RE = re.compile(r"^\s*(?:SZ\s*)?(\d+)\s*$")
_PARAGRAPH_RE = re.compile(r"^\s*([§¶])\s*(\d+)([a-z]?)\s*$")
# bcv section strings: "Gen 1:1", "1Cor 13:4", "Esth A:1". The book
# token is alphanumeric (digits may prefix or suffix); chapter:verse
# is two integers with an optional alpha verse suffix.
_BCV_SECTION_RE = re.compile(r"^\s*([1-4]?[A-Za-z]+)\s+(\d+)\s*:\s*(\d+)([a-z]?)\s*$")
# surah_ayah section strings: "Q 2:255", "2:255", "Surah 2:255". An
# optional Q/Quran/Surah prefix is accepted because Arabic-philosophy
# citations to the Quran are conventionally written "Q 2:255" — the
# parser tolerates both forms so the same regex works for chunk
# metadata strings and inline rule matches.
_SURAH_AYAH_SECTION_RE = re.compile(
    r"^\s*(?:Q\s*|Quran\s*|Surah\s*)?(\d+)\s*:\s*(\d+)([a-z]?)\s*$",
    re.IGNORECASE,
)


def parse_section(kind: str, section: str) -> dict[str, Any]:
    """Inverse of :data:`SORT_KEY_FORMATTERS`. Parse a locator string
    into the structured payload that the formatter would round-trip.

    The shapes are deliberately strict — we'd rather refuse an
    ambiguous string than silently misparse. Bekker accepts an
    optional line number (``1094a13``); when absent it defaults to 1.
    """

    if kind == "stephanus":
        m = _STEPHANUS_SECTION_RE.match(section)
        if m is None:
            raise LocationError(f"can't parse {section!r} as Stephanus (expected '514a' shape)")
        return {"kind": "stephanus", "page": int(m.group(1)), "section": m.group(2)}

    if kind == "bekker":
        m = _BEKKER_SECTION_RE.match(section)
        if m is None:
            raise LocationError(
                f"can't parse {section!r} as Bekker (expected '1094a' or '1094a13')"
            )
        page = int(m.group(1))
        col = m.group(2)
        line = int(m.group(3)) if m.group(3) else 1
        return {"kind": "bekker", "page": page, "column": col, "line": line}

    if kind == "kant_ab":
        m = _KANT_AB_SECTION_RE.match(section)
        if m is None:
            raise LocationError(f"can't parse {section!r} as Kant A/B (expected 'A123' or 'B456')")
        return {"kind": "kant_ab", "edition": m.group(1), "page": int(m.group(2))}

    if kind == "sz_marginal":
        m = _SZ_MARGINAL_RE.match(section)
        if m is None:
            raise LocationError(
                f"can't parse {section!r} as SZ marginal (expected '123' or 'SZ 123')"
            )
        return {"kind": "sz_marginal", "page": int(m.group(1))}

    if kind == "paragraph":
        m = _PARAGRAPH_RE.match(section)
        if m is None:
            raise LocationError(f"can't parse {section!r} as paragraph (expected '§44' or '¶17a')")
        symbol, number, suffix = m.group(1), int(m.group(2)), m.group(3) or ""
        payload: dict[str, Any] = {"kind": "paragraph", "symbol": symbol, "number": number}
        if suffix:
            payload["suffix"] = suffix
        return payload

    if kind == "surah_ayah":
        m = _SURAH_AYAH_SECTION_RE.match(section)
        if m is None:
            raise LocationError(
                f"can't parse {section!r} as surah_ayah (expected '2:255' or 'Q 2:255')"
            )
        return {
            "kind": "surah_ayah",
            "surah": int(m.group(1)),
            "ayah": int(m.group(2)),
            **({"ayah_suffix": m.group(3)} if m.group(3) else {}),
        }

    if kind == "bcv":
        m = _BCV_SECTION_RE.match(section)
        if m is None:
            raise LocationError(
                f"can't parse {section!r} as bcv (expected 'Gen 1:1' or '1Cor 13:4a')"
            )
        abbr = m.group(1)
        book = BCV_ABBR_TO_BOOK.get(abbr)
        if book is None:
            raise LocationError(
                f"bcv book abbreviation {abbr!r} not in canonical table; "
                f"valid: {sorted(BCV_ABBR_TO_BOOK)}"
            )
        payload_bcv: dict[str, Any] = {
            "kind": "bcv",
            "book": book,
            "chapter": int(m.group(2)),
            "verse": int(m.group(3)),
        }
        suffix_v = m.group(4) or ""
        if suffix_v:
            payload_bcv["verse_suffix"] = suffix_v
        return payload_bcv

    raise LocationError(
        f"unknown location_kind {kind!r}; valid kinds: {sorted(SORT_KEY_FORMATTERS)}"
    )


def format_sort_key(kind: str, payload: dict[str, Any]) -> str:
    """Encode a (kind, payload) pair into the canonical orderable form.

    Pure function: same inputs ⇒ same output forever, modulo
    ``SORT_KEY_VERSION``. Raises :class:`LocationError` if the kind is
    unknown or the payload doesn't satisfy that kind's schema.
    """

    encoder = SORT_KEY_FORMATTERS.get(kind)
    if encoder is None:
        raise LocationError(
            f"unknown location_kind {kind!r}; valid kinds: {sorted(SORT_KEY_FORMATTERS)}"
        )
    return encoder(payload)


# ---------- payload validation helpers ----------


def _require_int(p: dict[str, Any], key: str, *, minimum: int, maximum: int) -> int:
    if key not in p:
        raise LocationError(f"missing required field {key!r}")
    val = p[key]
    if isinstance(val, bool) or not isinstance(val, int):
        raise LocationError(f"field {key!r} must be int, got {type(val).__name__}")
    if val < minimum or val > maximum:
        raise LocationError(f"field {key!r}={val!r} out of range [{minimum}, {maximum}]")
    return val


def _require_choice(p: dict[str, Any], key: str, *, choices: tuple[str, ...]) -> str:
    if key not in p:
        raise LocationError(f"missing required field {key!r}")
    val = p[key]
    if val not in choices:
        raise LocationError(f"field {key!r}={val!r} must be one of {choices}")
    return val
