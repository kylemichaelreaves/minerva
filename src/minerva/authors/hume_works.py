"""Per-work configuration for Hume ingest.

Two English works from Project Gutenberg:

  • *An Enquiry Concerning Human Understanding* (#9662)
  • *A Treatise of Human Nature* (#4705)

Both use the generic ``chapter`` splitter.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="enquiry",
        title="An Enquiry Concerning Human Understanding",
        translator="(Original)",
        edition_year="1748",
        filenames=("enquiry.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="hume",
        author="Hume",
    ),
    CorpusWork(
        code="treatise",
        title="A Treatise of Human Nature",
        translator="(Original)",
        edition_year="1739",
        filenames=("treatise.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="hume",
        author="Hume",
    ),
)

find_work = make_find_work(WORKS)
