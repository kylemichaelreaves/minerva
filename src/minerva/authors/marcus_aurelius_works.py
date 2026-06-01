"""Per-work configuration for Marcus Aurelius ingest.

One work bilingually: *Τὰ εἰς ἑαυτόν* (*Meditations*, 12 books) in
Greek + English.

Sources:

  * Greek: el.wikisource — 12 separate book sub-pages, one per book.
    Concatenated by ``download_marcus_aurelius.py`` into a single
    .txt file with ``ΒΙΒΛΙΟΝ N`` headers between books.
  * English: PG 2680 (anonymous Long-derivative translation) — single
    plain-text file with chapter divisions intact.

Citation system: ``paragraph`` — each numbered section within each
book becomes a chunk.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="meditations_grc",
        title="Meditations",
        translator="(Original)",
        edition_year="170-180 CE",
        filenames=("meditations_grc.txt",),
        fmt="txt",
        locator="chapter",
        lang="grc",
        corpus="marcus_aurelius",
        author="Marcus Aurelius",
    ),
    CorpusWork(
        code="meditations_en",
        title="Meditations",
        translator="George Long",
        edition_year="1862",
        filenames=("meditations_en.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="marcus_aurelius",
        author="Marcus Aurelius",
    ),
)

find_work = make_find_work(WORKS)
