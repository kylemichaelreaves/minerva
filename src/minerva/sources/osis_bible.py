"""Shared OSIS-XML scripture parser.

OSIS 2.1.1 is the SBL-blessed canonical XML schema for biblical texts.
Many public-domain Bibles ship in OSIS — Luther 1545, Luther 1912,
KJV, Lemaistre de Sacy, Crampon, etc. all live in this shape:

    <osis xmlns="http://www.bibletechnologies.net/2003/OSIS/namespace">
      <osisText osisIDWork="..." xml:lang="...">
        <header>...</header>
        <div type="book" osisID="Gen">
          <chapter osisID="Gen.1">
            <verse osisID="Gen.1.1">Am Anfang schuf Gott…</verse>
            …
          </chapter>
          …
        </div>
        …
      </osisText>
    </osis>

This module captures the parse logic once. Per-edition modules
(:mod:`luther_1912`, :mod:`luther_1545`, :mod:`kjv`, :mod:`sacy`)
supply only the edition-specific knobs — corpus id, author label,
year, language — and inherit the rest.

The osisID system is **standardized** across Bibles, so unlike the
older Zefania ``bnumber`` convention every OSIS edition uses the
same book identifiers (Gen, Exod, Matt, Rev, …). The OSIS_TO_ENGLISH
table below maps every osisID we care about to the canonical English
book title shared with ``vulgate_works`` / ``hebrew_mt`` /
``septuagint_works`` / ``new_testament_works`` so cross-corpus
queries continue to align.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from xml.etree import ElementTree as ET

from minerva.tei import Chunk, _make_chunk_id, _norm_text

# OSIS namespace; lookups in iter() need this prefix.
_OSIS_NS = "{http://www.bibletechnologies.net/2003/OSIS/namespace}"


# OSIS book ID → canonical English book name. The right side matches
# entries in :data:`locations._BCV_BOOKS` so cross-corpus joins land
# the same verse across Vulgate / LXX / Luther / KJV / Sacy.
#
# Per-edition canon coverage: each Bible carries a subset of these
# (KJV 1769 = Protestant 66; Luther 1912 / Sacy / Vulgate carry the
# deuterocanon). Books outside the per-edition canon simply don't
# appear in the source XML, so the lookup table can be one big union.
OSIS_TO_ENGLISH: dict[str, str] = {
    # ── Pentateuch ────────────────────────────────────────────────
    "Gen": "Genesis",
    "Exod": "Exodus",
    "Lev": "Leviticus",
    "Num": "Numbers",
    "Deut": "Deuteronomy",
    # ── Historical ────────────────────────────────────────────────
    "Josh": "Joshua",
    "Judg": "Judges",
    "Ruth": "Ruth",
    "1Sam": "1 Samuel",
    "2Sam": "2 Samuel",
    "1Kgs": "1 Kings",
    "2Kgs": "2 Kings",
    "1Chr": "1 Chronicles",
    "2Chr": "2 Chronicles",
    "Ezra": "Ezra",
    "Neh": "Nehemiah",
    "Esth": "Esther",
    # ── Wisdom ────────────────────────────────────────────────────
    "Job": "Job",
    "Ps": "Psalms",
    "Prov": "Proverbs",
    "Eccl": "Ecclesiastes",
    "Song": "Song of Songs",
    # ── Major prophets ────────────────────────────────────────────
    "Isa": "Isaiah",
    "Jer": "Jeremiah",
    "Lam": "Lamentations",
    "Ezek": "Ezekiel",
    "Dan": "Daniel",
    # ── Minor prophets ────────────────────────────────────────────
    "Hos": "Hosea",
    "Joel": "Joel",
    "Amos": "Amos",
    "Obad": "Obadiah",
    "Jonah": "Jonah",
    "Mic": "Micah",
    "Nah": "Nahum",
    "Hab": "Habakkuk",
    "Zeph": "Zephaniah",
    "Hag": "Haggai",
    "Zech": "Zechariah",
    "Mal": "Malachi",
    # ── Deuterocanon / Apocrypha (Catholic + 1611 KJV + Luther) ───
    "Tob": "Tobit",
    "Jdt": "Judith",
    "Wis": "Wisdom",
    "Sir": "Sirach",
    "Bar": "Baruch",
    # EpJer = Letter of Jeremiah; we fold into Baruch ch. 6 as the
    # Vulgate / Luther 1912 / Sacy conventions do (see vulgate_works
    # docstring). Mapping it to "Baruch" lets the cross-corpus join
    # continue to work; the Letter is then accessible at Bar 6:N.
    "EpJer": "Baruch",
    "1Macc": "1 Maccabees",
    "2Macc": "2 Maccabees",
    # ── Gospels + Acts ────────────────────────────────────────────
    "Matt": "Matthew",
    "Mark": "Mark",
    "Luke": "Luke",
    "John": "John",
    "Acts": "Acts",
    # ── Pauline epistles ──────────────────────────────────────────
    "Rom": "Romans",
    "1Cor": "1 Corinthians",
    "2Cor": "2 Corinthians",
    "Gal": "Galatians",
    "Eph": "Ephesians",
    "Phil": "Philippians",
    "Col": "Colossians",
    "1Thess": "1 Thessalonians",
    "2Thess": "2 Thessalonians",
    "1Tim": "1 Timothy",
    "2Tim": "2 Timothy",
    "Titus": "Titus",
    "Phlm": "Philemon",
    "Heb": "Hebrews",
    # ── Catholic epistles ─────────────────────────────────────────
    "Jas": "James",
    "1Pet": "1 Peter",
    "2Pet": "2 Peter",
    "1John": "1 John",
    "2John": "2 John",
    "3John": "3 John",
    "Jude": "Jude",
    # ── Revelation ────────────────────────────────────────────────
    "Rev": "Revelation",
}


def _verse_text(verse: ET.Element) -> str:
    """Extract verse text from an OSIS ``<verse>`` element.

    OSIS verses use either:

    * **Container form** — ``<verse osisID="Gen.1.1">text</verse>``.
      The verse text is the concatenated text of the element.
    * **Milestone form** — ``<verse osisID="..." sID="..."/>text<verse eID=".../>``.
      Less common in modern OSIS dumps; gratis-bible uses the
      container form universally, so we don't handle milestones here
      (would need a state machine over the chapter's child sequence).

    Editorial / footnote elements (``<note>``, ``<reference>``) are
    skipped — their content is apparatus, not verse text."""

    parts: list[str] = []
    if verse.text:
        parts.append(verse.text)
    for child in verse:
        local = child.tag.split("}", 1)[-1] if "}" in child.tag else child.tag
        local_lc = local.lower()
        if local_lc in {"note", "reference", "rdg"}:
            # Drop note/reference content but keep tail (text after </note>
            # back in the verse flow).
            if child.tail:
                parts.append(child.tail)
            continue
        # Other elements (e.g. <w>, <transChange>, <hi>) carry verse
        # content — include their text and tail.
        parts.append("".join(child.itertext()))
        if child.tail:
            parts.append(child.tail)
    return _norm_text("".join(parts))


def parse_file(
    path: Path,
    *,
    corpus: str,
    author: str,
    lang: str,
    edition_year: str,
    translator: str,
) -> Iterator[Chunk]:
    """Yield one Chunk per ``<verse osisID="...">`` in an OSIS Bible file.

    Books whose ``osisID`` isn't in :data:`OSIS_TO_ENGLISH` are
    skipped with a warning (most likely a deuterocanonical book we
    don't yet recognise; logged so coverage gaps are visible)."""

    from minerva.locations import BCV_BOOK_ABBR

    tree = ET.parse(path)
    root = tree.getroot()

    for book_div in root.iter(f"{_OSIS_NS}div"):
        if book_div.get("type") != "book":
            continue
        osis_book = book_div.get("osisID")
        if not osis_book:
            continue
        title = OSIS_TO_ENGLISH.get(osis_book)
        if title is None:
            print(f"{corpus}: skipping unknown osisID={osis_book!r}")
            continue
        sbl = BCV_BOOK_ABBR.get(title)
        if sbl is None:
            print(f"{corpus}: book {title!r} not in BCV_BOOK_ABBR; add it to locations._BCV_BOOKS")
            continue

        # OSIS verse osisIDs encode the locator: "Gen.1.1" → book=Gen,
        # chapter=1, verse=1. Parse them directly rather than walking
        # the parent <chapter> elements; this lets us skip empty
        # chapters cleanly.
        for verse in book_div.iter(f"{_OSIS_NS}verse"):
            osis_id = verse.get("osisID")
            if not osis_id:
                # milestone-form <verse eID="..."/> — skip; the
                # container-form pass already captured the content.
                continue
            # osisID can be a range like "Gen.1.1-Gen.1.3" for verse
            # spans; we'd want to emit one chunk per verse. Split on
            # the range delimiter and prefer the first part — corpora
            # we ingest don't use ranges, but be defensive.
            primary = osis_id.split("-", 1)[0]
            parts = primary.split(".")
            if len(parts) < 3:
                # Sometimes "Gen.1" appears on a chapter-only verse
                # (rare; an editorial scaffold). Skip — we want
                # full verse-level granularity.
                continue
            try:
                chap = int(parts[1])
                vnum = int(parts[2])
            except ValueError:
                continue
            text = _verse_text(verse)
            if not text:
                continue
            section = f"{sbl} {chap}:{vnum}"
            chunk_id = _make_chunk_id(
                path.name,
                osis_book.lower(),
                lang,
                title,
                section,
                "",
                text[:120],
            )
            yield Chunk(
                chunk_id=chunk_id,
                corpus=corpus,
                author=author,
                work=title,
                lang=lang,
                section=section,
                book=title,
                page=None,
                speaker=None,
                text=text,
                source_file=path.name,
                translator=translator,
                edition_year=edition_year,
                citation_system="bcv",
            )


def parse_dir(
    directory: Path,
    *,
    corpus: str,
    author: str,
    lang: str,
    edition_year: str,
    translator: str,
) -> Iterator[Chunk]:
    """Walk a directory yielding Chunks for every ``*.xml`` OSIS file.

    Conventionally one file per edition; loop tolerates multiples in
    case a future fork-and-split downloader emits per-book XML."""

    for entry in sorted(directory.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".xml"):
            continue
        yield from parse_file(
            entry,
            corpus=corpus,
            author=author,
            lang=lang,
            edition_year=edition_year,
            translator=translator,
        )
