"""Per-work configuration for Pascal ingest.

*Pensées* from Project Gutenberg #24499 (French). Ingested via the
generic ``chapter`` splitter.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="pensees",
        title="Pensées",
        translator="(Original)",
        edition_year="1670",
        filenames=("pensees.txt",),
        fmt="txt",
        locator="chapter",
        lang="fra",
        corpus="pascal",
        author="Pascal",
    ),
)

find_work = make_find_work(WORKS)
