"""Per-work configuration for Locke ingest.

Two English works from Project Gutenberg:

  • *An Essay Concerning Human Understanding* (#10615)
  • *Second Treatise of Government* (#7370)

Both use the generic ``chapter`` splitter.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="essay",
        title="An Essay Concerning Human Understanding",
        translator="(Original)",
        edition_year="1689",
        filenames=("essay.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="locke",
        author="Locke",
    ),
    CorpusWork(
        code="second_treatise",
        title="Second Treatise of Government",
        translator="(Original)",
        edition_year="1689",
        filenames=("second_treatise.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="locke",
        author="Locke",
    ),
)

find_work = make_find_work(WORKS)
