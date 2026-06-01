"""Per-work configuration for Augustine ingest.

Three Latin works land from `perseus/download_augustine.py`, all
sourced from la.wikisource.org's Maurist-edition transcriptions:

  • Confessiones (13 Libri; canonical citation Book.Chapter.Paragraph,
    e.g. `Conf. VIII.7.16`). Wikisource carries paragraph-level
    structure inline, so each Wikisource paragraph → one chunk.
  • De civitate Dei (22 Libri; canonical `Civ. Dei XIX.13`).
    Wikisource carries chapter-level structure (`[I]`, `[II]`, …
    inline at each chapter's first paragraph), so the chapter is
    our granularity ceiling.
  • De Trinitate (15 Libri; canonical `Trin. IX.4.7`). Wikisource
    carries `<RomanChapter> <ArabicParagraph>` H2 headings at chapter
    starts and bare paragraph numbers between — one chunk per
    paragraph.

All three ingest via the `augustine` locator (see
`corpus/split_augustine.py`), which consumes the
`[CONF.b.c.p]` / `[CIV.b.c]` / `[TRIN.b.c.p]` marker shapes the
downloader emits.

Augustine's shorter works (De doctrina Christiana, De libero arbitrio,
De magistro, Enchiridion, Soliloquia, De vera religione, etc.) are
NOT in this pass — they live on Wikisource with less consistent
internal structure, and the three works above already cover the bulk
of philosophical-theological citations. Future passes can extend
WORKS without touching the splitter (the marker shape generalises).
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="confessiones",
        title="Confessiones",
        translator="(Original)",
        edition_year="397-401",
        filenames=("confessiones.txt",),
        fmt="txt",
        locator="augustine",
        lang="lat",
        corpus="augustine",
        author="Augustine",
        citation_system="augustine",
    ),
    CorpusWork(
        code="civitate_dei",
        title="De civitate Dei",
        translator="(Original)",
        edition_year="412-426",
        filenames=("civitate_dei.txt",),
        fmt="txt",
        locator="augustine",
        lang="lat",
        corpus="augustine",
        author="Augustine",
        citation_system="augustine",
    ),
    CorpusWork(
        code="trinitate",
        title="De Trinitate",
        translator="(Original)",
        edition_year="399-419",
        filenames=("trinitate.txt",),
        fmt="txt",
        locator="augustine",
        lang="lat",
        corpus="augustine",
        author="Augustine",
        citation_system="augustine",
    ),
)


find_work = make_find_work(WORKS)
