"""Per-work configuration for the German Plato sources (corpus-label pipeline).

Plato's Greek + English come through Perseus TEI (``ingest/registry.py``
``plato`` source) and carry no works-table. This module covers the German
*translations* that ride the corpus-label pipeline — currently Schleiermacher's
*Der Staat* (Republic), sourced as MDZ hOCR (``bsb10237333``) and split by
``split_stephanus_de`` so its chunks land Stephanus-aligned under the existing
"Republic" work (id 81, ``stephanus`` citation), grouped with the Greek edition
and the English translation.

``title`` MUST match the Greek work's title exactly ("Republic") — that's the
join key in ``store._resolve_work_refs``; any drift would orphan the German as
a separate work instead of attaching it as a translation.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="republic_de",
        title="Republic",  # exact match to the Greek/English work (id 81)
        translator="Schleiermacher",
        edition_year="1855",
        filenames=("republic_schleiermacher_mdz.hocr",),
        fmt="hocr",
        locator="stephanus_de",
        lang="deu",
        corpus="plato",
        author="Plato",
    ),
)

find_work = make_find_work(WORKS, case_insensitive=True)


def find_works(filename: str) -> list[CorpusWork]:
    """All Works that claim this filename. Order matches ``WORKS``."""
    lower = filename.lower()
    return [w for w in WORKS if any(c.lower() == lower for c in w.filenames)]
