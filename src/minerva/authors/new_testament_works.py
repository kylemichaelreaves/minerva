"""Per-work configuration for the New Testament ingest.

Source: SBLGNT (Mike Holmes ed., 2nd ed. 2010) as packaged in
``LogosBible/SBLGNT``'s per-book XML files. License: SBLGNT EULA
(free academic / non-commercial use); see the downloader for the
distribution note.

One CorpusWork per canonical NT book — 27 in total — sharing the
``new_testament`` corpus and the ``bcv`` citation system. The
``filenames`` field carries the SBLGNT-repo filename (``Matt.xml``
through ``Rev.xml``) which the splitter uses for dispatch via
``find_work``.

Format quirks consumed by ``sblgnt.py``:
* ``<verse-number id="Matthew 1:1">`` milestones delimit verses.
* ``<w>`` / ``<suffix>`` siblings carry pre-tokenised words.
* Verses can cross ``<p>`` boundaries.
"""

from __future__ import annotations

import dataclasses

from ..corpus_works import CorpusWork, make_find_work


@dataclasses.dataclass(frozen=True)
class _NTBook:
    """SBLGNT-side metadata for one NT book.

    Kept private — downstream code consumes ``WORKS`` (standard
    ``CorpusWork`` records). The splitter consults ``find_work`` /
    ``book_for_filename`` to map an on-disk filename to its
    canonical title and SBL abbreviation.
    """

    code: str  # snake_case slug
    title: str  # canonical English name (and chunk `book` field)
    filename: str  # SBLGNT repo filename, e.g. "Matt.xml"


_BOOKS: tuple[_NTBook, ...] = (
    # ----- Gospels -----
    _NTBook("matthew", "Matthew", "Matt.xml"),
    _NTBook("mark", "Mark", "Mark.xml"),
    _NTBook("luke", "Luke", "Luke.xml"),
    _NTBook("john", "John", "John.xml"),
    # ----- Acts -----
    _NTBook("acts", "Acts", "Acts.xml"),
    # ----- Pauline epistles -----
    _NTBook("romans", "Romans", "Rom.xml"),
    _NTBook("1corinthians", "1 Corinthians", "1Cor.xml"),
    _NTBook("2corinthians", "2 Corinthians", "2Cor.xml"),
    _NTBook("galatians", "Galatians", "Gal.xml"),
    _NTBook("ephesians", "Ephesians", "Eph.xml"),
    _NTBook("philippians", "Philippians", "Phil.xml"),
    _NTBook("colossians", "Colossians", "Col.xml"),
    _NTBook("1thessalonians", "1 Thessalonians", "1Thess.xml"),
    _NTBook("2thessalonians", "2 Thessalonians", "2Thess.xml"),
    _NTBook("1timothy", "1 Timothy", "1Tim.xml"),
    _NTBook("2timothy", "2 Timothy", "2Tim.xml"),
    _NTBook("titus", "Titus", "Titus.xml"),
    _NTBook("philemon", "Philemon", "Phlm.xml"),
    # ----- Hebrews -----
    _NTBook("hebrews", "Hebrews", "Heb.xml"),
    # ----- Catholic epistles -----
    _NTBook("james", "James", "Jas.xml"),
    _NTBook("1peter", "1 Peter", "1Pet.xml"),
    _NTBook("2peter", "2 Peter", "2Pet.xml"),
    _NTBook("1john", "1 John", "1John.xml"),
    _NTBook("2john", "2 John", "2John.xml"),
    _NTBook("3john", "3 John", "3John.xml"),
    _NTBook("jude", "Jude", "Jude.xml"),
    # ----- Revelation -----
    _NTBook("revelation", "Revelation", "Rev.xml"),
)


WORKS: tuple[CorpusWork, ...] = tuple(
    CorpusWork(
        code=b.code,
        title=b.title,
        translator="(Original)",
        edition_year="2010",  # SBLGNT 2nd ed.
        filenames=(b.filename,),
        fmt="xml",
        # `locator` is informational only — NT files dispatch through
        # `sblgnt.parse_dir`, not the corpus.pipeline splitter table.
        locator="sblgnt",
        lang="grc",
        corpus="new_testament",
        author="New Testament",
        citation_system="bcv",
    )
    for b in _BOOKS
)


_BOOK_BY_FILENAME = {b.filename: b for b in _BOOKS}

find_work = make_find_work(WORKS)


def book_for_filename(filename: str) -> _NTBook | None:
    """Reverse-lookup used by the SBLGNT splitter to translate the
    on-disk filename into the canonical book title that goes into
    the chunk's ``book`` field (and into the SBL abbreviation lookup
    in ``locations.BCV_BOOK_ABBR``)."""
    return _BOOK_BY_FILENAME.get(filename)


def all_books() -> tuple[_NTBook, ...]:
    """For tooling / downloaders — every NT book we want to ingest."""
    return _BOOKS
