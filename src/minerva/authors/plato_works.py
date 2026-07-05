"""Per-work configuration for the German Plato source (corpus-label pipeline).

Plato's Greek + English come through Perseus TEI (``ingest/registry.py``
``plato`` source). The German *translations* ride the corpus-label pipeline:
the complete "Platon: die Werke" PDF (Schleiermacher, with Susemihl/Georgii
for some dialogues). It is a single file holding every dialogue + the
Letters, so a **multi-work** structure-aware splitter
(``corpus/split_platon_werke.py``) reads it and emits chunks for all works,
canonicalizing each title to its Latinized-Greek name (``authors/plato_titles``)
so the German attaches as a ``deu`` translation on the same works row as the
Greek edition and the English translation.

(Superseded the earlier single-work MDZ hOCR "Der Staat" entry — the PDF
covers Politeia and every other dialogue, Stephanus-aligned.)
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="platon_werke_de",
        # title/translator/year are per-dialogue; the splitter computes
        # them. This carrier only routes the file to the splitter.
        title="Platon: die Werke",
        translator="Schleiermacher",
        edition_year="1818",
        filenames=("Platon_Werke.pdf",),
        fmt="pdf",
        locator="platon_werke",
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
