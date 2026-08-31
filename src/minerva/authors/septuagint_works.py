"""Per-work configuration for the Septuagint (LXX) ingest.

Source: OpenGreekAndLatin's First1KGreek repo, group ``tlg0527``
(Swete's LXX, Cambridge 1887–1901, public domain). TEI P5 with
EpiDoc, ``<div type="textpart" subtype="chapter">`` → ``subtype=
"verse">`` nesting. One file per book.

This file scopes the LXX ingest to the **Catholic canon** (46 OT
books) plus a handful of LXX-only deuterocanonical-adjacent works
that are routinely cited by patristic and scholastic authors:
* Susanna and Bel & the Dragon (Theodotion) — Daniel 13–14 in the
  Vulgate, standalone in the LXX.
* Letter of Jeremiah — Baruch ch. 6 in the Vulgate, standalone in
  the LXX.

LXX-only works **not** ingested in this pass: 1 Esdras (tlg017),
3–4 Maccabees (tlg025, tlg026), Odes (tlg028), Psalms of Solomon
(tlg035). Add to ``_BOOKS`` if/when needed.

Old Greek (OG) recensions of Daniel / Susanna / Bel are omitted in
favor of the Theodotion text, which is the form transmitted to the
Latin tradition.

The ``tlg018`` slot is Swete's combined "Esdras II" (= MT
Ezra + MT Nehemiah). Ingested here as a single CorpusWork titled
``"Ezra-Nehemiah"`` — splitting at the Ezra/Neh boundary requires
chapter-range knowledge that isn't worth wiring up before we see
the on-disk shape. Verses land with ``book="Ezra-Nehemiah"``;
revisit once we observe how Aquinas's cites to "Esdras" / "II
Esdrae" / "Nehemiae" actually surface.
"""

from __future__ import annotations

import dataclasses

from ..corpus_works import CorpusWork, make_find_work


@dataclasses.dataclass(frozen=True)
class _LXXBook:
    """First1KGreek-side metadata for one LXX book.

    Kept private — downstream code consumes ``WORKS`` (standard ``CorpusWork``
    records). The downloader imports this dataclass to walk First1KGreek
    URLs; everything else routes through ``find_work``.
    """

    code: str  # snake_case slug used as the chunk corpus code
    title: str  # canonical English title (and `book` on Chunks)
    tlg: str  # First1KGreek directory: 'tlg001', 'tlg055', etc.


# Order roughly follows the Vulgate / Catholic canonical sequence,
# not Swete's printed order. The order here only determines
# downloader iteration; canonical sort is via
# `locations.BCV_BOOK_ORDINAL`.
_BOOKS: tuple[_LXXBook, ...] = (
    # ----- Pentateuch -----
    _LXXBook("genesis", "Genesis", "tlg001"),
    _LXXBook("exodus", "Exodus", "tlg002"),
    _LXXBook("leviticus", "Leviticus", "tlg003"),
    _LXXBook("numbers", "Numbers", "tlg004"),
    _LXXBook("deuteronomy", "Deuteronomy", "tlg005"),
    # ----- Historical -----
    _LXXBook("joshua", "Joshua", "tlg006"),
    _LXXBook("judges", "Judges", "tlg008"),
    _LXXBook("ruth", "Ruth", "tlg010"),
    _LXXBook("1samuel", "1 Samuel", "tlg011"),  # Regnorum I
    _LXXBook("2samuel", "2 Samuel", "tlg012"),  # Regnorum II
    _LXXBook("1kings", "1 Kings", "tlg013"),  # Regnorum III
    _LXXBook("2kings", "2 Kings", "tlg014"),  # Regnorum IV
    _LXXBook("1chronicles", "1 Chronicles", "tlg015"),  # Paralipomenon I
    _LXXBook("2chronicles", "2 Chronicles", "tlg016"),  # Paralipomenon II
    _LXXBook("ezra_nehemiah", "Ezra-Nehemiah", "tlg018"),  # Esdras II = Ezra+Neh
    _LXXBook("esther", "Esther", "tlg019"),  # Greek Esther w/ additions
    _LXXBook("judith", "Judith", "tlg020"),
    _LXXBook("tobit", "Tobit", "tlg021"),
    _LXXBook("1maccabees", "1 Maccabees", "tlg023"),
    _LXXBook("2maccabees", "2 Maccabees", "tlg024"),
    # ----- Wisdom -----
    _LXXBook("psalms", "Psalms", "tlg027"),
    _LXXBook("proverbs", "Proverbs", "tlg029"),
    # tlg030 (Ecclesiastes/Qoheleth) — First1KGreek has the CTS
    # metadata stub but no actual TEI text. Backfill from STEPBible
    # or another source in a follow-up pass.
    _LXXBook("song_of_songs", "Song of Songs", "tlg031"),
    _LXXBook("job", "Job", "tlg032"),
    _LXXBook("wisdom", "Wisdom", "tlg033"),
    _LXXBook("sirach", "Sirach", "tlg034"),
    # ----- Major prophets -----
    _LXXBook("isaiah", "Isaiah", "tlg048"),
    _LXXBook("jeremiah", "Jeremiah", "tlg049"),
    _LXXBook("baruch", "Baruch", "tlg050"),
    _LXXBook("lamentations", "Lamentations", "tlg051"),
    _LXXBook("letter_of_jeremiah", "Letter of Jeremiah", "tlg052"),
    _LXXBook("ezekiel", "Ezekiel", "tlg053"),
    _LXXBook("daniel", "Daniel", "tlg057"),  # Theodotion recension
    _LXXBook("susanna", "Susanna", "tlg055"),  # Theodotion (Dan 13 in Vg)
    _LXXBook("bel", "Bel and the Dragon", "tlg059"),  # Theodotion (Dan 14 in Vg)
    # ----- Minor prophets (LXX printing order, but stored canonically) -----
    _LXXBook("hosea", "Hosea", "tlg036"),
    _LXXBook("amos", "Amos", "tlg037"),
    _LXXBook("micah", "Micah", "tlg038"),
    _LXXBook("joel", "Joel", "tlg039"),
    _LXXBook("obadiah", "Obadiah", "tlg040"),
    _LXXBook("jonah", "Jonah", "tlg041"),
    _LXXBook("nahum", "Nahum", "tlg042"),
    _LXXBook("habakkuk", "Habakkuk", "tlg043"),
    _LXXBook("zephaniah", "Zephaniah", "tlg044"),
    _LXXBook("haggai", "Haggai", "tlg045"),
    _LXXBook("zechariah", "Zechariah", "tlg046"),
    _LXXBook("malachi", "Malachi", "tlg047"),
)


def _filename_for(b: _LXXBook) -> str:
    """First1KGreek's canonical filename for one LXX book."""
    return f"tlg0527.{b.tlg}.1st1K-grc1.xml"


WORKS: tuple[CorpusWork, ...] = tuple(
    CorpusWork(
        code=b.code,
        title=b.title,
        translator="(Original)",
        edition_year="1887",  # Swete, Cambridge (vols 1887–1901)
        filenames=(_filename_for(b),),
        fmt="xml",
        # `locator` is informational only — biblical files dispatch
        # through `tei_lxx.parse_dir`, not the corpus.pipeline splitter
        # table.
        locator="lxx",
        lang="grc",
        corpus="septuagint",
        author="Septuagint",
        citation_system="bcv",
    )
    for b in _BOOKS
)


_BOOK_BY_FILENAME = {_filename_for(b): b for b in _BOOKS}

find_work = make_find_work(WORKS)


def book_for_filename(filename: str) -> _LXXBook | None:
    """Reverse-lookup used by the TEI P5 LXX parser to translate the
    on-disk filename into the canonical book title that goes into
    the chunk's ``book`` field (and into the SBL abbreviation lookup
    in ``locations.BCV_BOOK_ABBR``)."""
    return _BOOK_BY_FILENAME.get(filename)


def all_books() -> tuple[_LXXBook, ...]:
    """For the downloader — every LXX book we want to fetch."""
    return _BOOKS
