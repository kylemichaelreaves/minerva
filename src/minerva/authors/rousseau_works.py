"""Per-work configuration for Rousseau ingest.

Six French works from fr.wikisource.org — Du contrat social plus
the Phase-2 expansion (two Discours, Économie politique, Émile,
Essai sur l'origine des langues). All scraped via
``perseus/download_rousseau_fr.py``; PG has no clean French
Rousseau (PG 4636 was a wrong-author placeholder).

All works use the generic ``chapter`` splitter — multi-section works
(Second Discourse, Émile) have uppercase LIVRE/PARTIE headings
inserted between sub-pages so the splitter chunks at those
boundaries.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="premier_discours",
        title="Discours sur les sciences et les arts",
        translator="(Original)",
        edition_year="1750",
        filenames=("premier_discours.txt",),
        fmt="txt",
        locator="chapter",
        lang="fra",
        corpus="rousseau",
        author="Rousseau",
    ),
    CorpusWork(
        code="second_discours",
        title="Discours sur l'origine de l'inégalité",
        translator="(Original)",
        edition_year="1755",
        filenames=("second_discours.txt",),
        fmt="txt",
        locator="chapter",
        lang="fra",
        corpus="rousseau",
        author="Rousseau",
    ),
    CorpusWork(
        code="economie_politique",
        title="Discours sur l'économie politique",
        translator="(Original)",
        edition_year="1755",
        filenames=("economie_politique.txt",),
        fmt="txt",
        locator="chapter",
        lang="fra",
        corpus="rousseau",
        author="Rousseau",
    ),
    CorpusWork(
        code="contrat_social",
        title="Du contrat social",
        translator="(Original)",
        edition_year="1762",
        filenames=("contrat_social.txt",),
        fmt="txt",
        locator="chapter",
        lang="fra",
        corpus="rousseau",
        author="Rousseau",
    ),
    CorpusWork(
        code="emile",
        title="Émile, ou De l'éducation",
        translator="(Original)",
        edition_year="1762",
        filenames=("emile.txt",),
        fmt="txt",
        locator="chapter",
        lang="fra",
        corpus="rousseau",
        author="Rousseau",
    ),
    CorpusWork(
        code="essai_origine_langues",
        title="Essai sur l'origine des langues",
        translator="(Original)",
        edition_year="1781",
        filenames=("essai_origine_langues.txt",),
        fmt="txt",
        locator="chapter",
        lang="fra",
        corpus="rousseau",
        author="Rousseau",
    ),
)

find_work = make_find_work(WORKS)
