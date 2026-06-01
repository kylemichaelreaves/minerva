"""Per-work configuration for Lucretius ingest.

One work bilingually: *De Rerum Natura* (the only surviving
Epicurean philosophical text from antiquity), in Latin and English.

Sources:

  * Latin: Perseus dltext 1999.02.0130 — Munro 1860 critical edition.
  * English: Perseus dltext 1999.02.0131 — H. A. J. Munro's English
    translation (1864). Same source-host as the Latin so both come
    through the same `download_perseus_lucretius.py` pipeline.

Citation system: ``paragraph`` — Perseus chunks Lucretius by book +
section number; that maps cleanly onto our paragraph citation.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="dr_natura_lat",
        title="De Rerum Natura",
        translator="(Original)",
        edition_year="55 BCE",
        filenames=("dr_natura_lat.xml",),
        fmt="xml",
        locator="chapter",
        lang="lat",
        corpus="lucretius",
        author="Lucretius",
    ),
    CorpusWork(
        code="dr_natura_en",
        title="De Rerum Natura",
        translator="H. A. J. Munro",
        edition_year="1864",
        filenames=("dr_natura_en.xml",),
        fmt="xml",
        locator="chapter",
        lang="eng",
        corpus="lucretius",
        author="Lucretius",
    ),
)

find_work = make_find_work(WORKS)
