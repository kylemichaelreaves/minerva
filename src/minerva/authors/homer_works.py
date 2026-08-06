"""Per-work configuration for Homer ingest.

Two epics land from `perseus/download_perseus_homer.py`, both sourced
from the Perseus Digital Library's TEI.2 bundles:

  • Iliad   — 24 books, ~15,693 lines, ~426 Perseus-cards per book
  • Odyssey — 24 books, ~12,110 lines, ~400 Perseus-cards per book

Each card is one chunk. Canonical citation: ``Il. 1.33`` or
``Od. 12.108`` — book.starting-line, the standard scholarly form.
The TEI parser (`src/minerva/tei.py`) emits this directly via the
``unit="card"`` milestone handler.

Citation system: ``paragraph``. Homer's traditional ``book.line``
locator isn't novel enough to warrant a new value in the
``works.citation_system`` CHECK list — the section field stores the
plain ``<book>.<line>`` string and the reader displays it verbatim.

Per-work licensing: the Perseus bundles are CC-BY-NC; see the TEI
`<publicationStmt>` in each XML file before redistributing.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    # ─── Iliad ─────────────────────────────────────────────────────
    CorpusWork(
        code="iliad_grc",
        title="Iliad",
        translator="(Original)",
        edition_year="1920",  # Allen ed., Oxford
        filenames=("perseus_homer_01_iliad_gr.xml",),
        fmt="xml",
        locator="perseus",
        lang="grc",
        corpus="homer",
        author="Homer",
        citation_system="paragraph",
    ),
    CorpusWork(
        code="iliad_eng",
        title="Iliad",
        translator="A. T. Murray",
        edition_year="1924",  # Loeb Classical Library
        filenames=("perseus_homer_01_iliad_en.xml",),
        fmt="xml",
        locator="perseus",
        lang="eng",
        corpus="homer",
        author="Homer",
        citation_system="paragraph",
    ),
    # ─── Odyssey ───────────────────────────────────────────────────
    CorpusWork(
        code="odyssey_grc",
        title="Odyssey",
        translator="(Original)",
        edition_year="1919",  # Allen ed., Oxford
        filenames=("perseus_homer_02_odyssey_gr.xml",),
        fmt="xml",
        locator="perseus",
        lang="grc",
        corpus="homer",
        author="Homer",
        citation_system="paragraph",
    ),
    CorpusWork(
        code="odyssey_eng",
        title="Odyssey",
        translator="A. T. Murray",
        edition_year="1919",  # Loeb Classical Library
        filenames=("perseus_homer_02_odyssey_en.xml",),
        fmt="xml",
        locator="perseus",
        lang="eng",
        corpus="homer",
        author="Homer",
        citation_system="paragraph",
    ),
)


find_work = make_find_work(WORKS)
