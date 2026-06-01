"""Per-work configuration for Epictetus ingest.

Two works in Greek + English:

  * *Dissertationes / Discourses* (Διατριβαί) — Arrian's compilation
    of Epictetus's teaching, in 4 books. The primary Stoic text we
    have in the corpus.
  * *Enchiridion* (Ἐγχειρίδιον) — the "Handbook" — a short Stoic
    catechism compiled by Arrian; bundled with the Discourses on
    Perseus.

Sources:

  * Greek: Perseus dltext 1999.01.0235 — Schenkl edition. Bundles
    Dissertationes + Enchiridion + Fragments in one TEI file.
  * English: Perseus dltext 1999.01.0237 — George Long's translation
    (1877). Same packaging (Discourses + Enchiridion + Fragments).

We register a single CorpusWork per language pointing at the
combined Perseus file. The chunk-text splitter will section the
content at TEI ``<div>`` boundaries which line up with the work
boundary inside each file.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="discourses_grc",
        title="Discourses and Enchiridion",
        translator="(Original)",
        edition_year="2nd c. CE",
        filenames=("discourses_grc.xml",),
        fmt="xml",
        locator="chapter",
        lang="grc",
        corpus="epictetus",
        author="Epictetus",
    ),
    CorpusWork(
        code="discourses_en",
        title="Discourses and Enchiridion",
        translator="George Long",
        edition_year="1877",
        filenames=("discourses_en.xml",),
        fmt="xml",
        locator="chapter",
        lang="eng",
        corpus="epictetus",
        author="Epictetus",
    ),
)

find_work = make_find_work(WORKS)
