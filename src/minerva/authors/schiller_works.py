"""Per-work configuration for Friedrich Schiller's theoretical writings.

Maps the zeno.org-sourced HTML files in ``data/schiller/raw_deu/`` (fetched
by ``perseus/download_schiller_de.py``) to work metadata. All are German
originals (Schiller died 1805; public domain) and route through the
``split_zeno`` parser via ``locator="chapter"`` — the same path Hegel's and
Kant's zeno German texts use.

Scope: Schiller's aesthetic philosophy — the Aesthetic Education letters plus
the major companion essays. ``edition_year`` is the composition/first-print
year used for display ordering within the author.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

_COMMON = {
    "fmt": "html",
    "locator": "chapter",
    "lang": "deu",
    "corpus": "schiller",
    "author": "Schiller",
}

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="aesthetische_erziehung",
        title="Über die ästhetische Erziehung des Menschen",
        translator="(Original)",
        edition_year="1795",
        filenames=("aesthetische_erziehung_de.html",),
        **_COMMON,
    ),
    CorpusWork(
        code="naive_sentimentalische",
        title="Über naive und sentimentalische Dichtung",
        translator="(Original)",
        edition_year="1795",
        filenames=("naive_sentimentalische_de.html",),
        **_COMMON,
    ),
    CorpusWork(
        code="anmut_wuerde",
        title="Über Anmut und Würde",
        translator="(Original)",
        edition_year="1793",
        filenames=("anmut_wuerde_de.html",),
        **_COMMON,
    ),
    CorpusWork(
        code="kallias",
        title="Kallias oder über die Schönheit",
        translator="(Original)",
        edition_year="1793",
        filenames=("kallias_de.html",),
        **_COMMON,
    ),
    CorpusWork(
        code="ueber_erhabene",
        title="Über das Erhabene",
        translator="(Original)",
        edition_year="1801",
        filenames=("ueber_erhabene_de.html",),
        **_COMMON,
    ),
    CorpusWork(
        code="vom_erhabenen",
        title="Vom Erhabenen",
        translator="(Original)",
        edition_year="1793",
        filenames=("vom_erhabenen_de.html",),
        **_COMMON,
    ),
    CorpusWork(
        code="pathetische",
        title="Über das Pathetische",
        translator="(Original)",
        edition_year="1793",
        filenames=("pathetische_de.html",),
        **_COMMON,
    ),
    CorpusWork(
        code="tragische_kunst",
        title="Über die tragische Kunst",
        translator="(Original)",
        edition_year="1792",
        filenames=("tragische_kunst_de.html",),
        **_COMMON,
    ),
    CorpusWork(
        code="tragische_gegenstaende",
        title="Über den Grund des Vergnügens an tragischen Gegenständen",
        translator="(Original)",
        edition_year="1792",
        filenames=("tragische_gegenstaende_de.html",),
        **_COMMON,
    ),
    CorpusWork(
        code="philosophische_briefe",
        title="Philosophische Briefe",
        translator="(Original)",
        edition_year="1786",
        filenames=("philosophische_briefe_de.html",),
        **_COMMON,
    ),
)

find_work = make_find_work(WORKS, case_insensitive=True)


def find_works(filename: str) -> list[CorpusWork]:
    """All Works that claim this filename. Order matches ``WORKS``."""
    lower = filename.lower()
    return [w for w in WORKS if any(c.lower() == lower for c in w.filenames)]
