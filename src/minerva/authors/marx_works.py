"""Per-work configuration for Marx ingest.

14 German works across four source pipelines:

* Wikisource (3): Manifest der Kommunistischen Partei (1848),
  Thesen über Feuerbach (1845), Zur Kritik der Hegel'schen
  Rechtsphilosophie. Einleitung (1844). Single-page de.wikisource
  pages; class-aware extractor handles editorial chrome.

* Projekt Gutenberg-DE (6): Zur Kritik der politischen Ökonomie
  (1859), Der achtzehnte Brumaire des Louis Bonaparte (1852), Lohn,
  Preis und Profit (1865), Lohnarbeit und Kapital (1849), Das Elend
  der Philosophie (1847), Die heilige Familie (1845). Multi-chapter
  pages under projekt-gutenberg.org/authors/karl-marx/books/<slug>/
  chapter/<n>; concatenated with KAPITEL N headers.

* MEW chapter pages (3): Das Kapital Bd 1 / Bd 2 / Bd 3 — MEW 23–25
  per-chapter HTML from the Wayback snapshot of mlwerke.de
  (`perseus/download_kapital_mew.py` → `data/marx/raw_mew/`,
  parsed by `corpus/split_kapital_mew.py` with MEW page numbers and
  Marx's own footnotes as `remark` chunks). Replaced the 2026-07
  Internet-Archive Fraktur-OCR source (55 mega-chunks of scan noise
  in the 1867 six-chapter structure).

* mlwerke.de / web.archive.org snapshots (2): Die deutsche
  Ideologie (14 sub-pages of MEW Bd 3 via web.archive.org snapshot
  of mlwerke.de), Ökonomisch-philosophische Manuskripte 1844
  (11 sub-pages on marxists.org native HTML).

Gap: Grundrisse der Kritik der politischen Ökonomie — no clean
plain-text German source found on archive.org or marxists.org.
Deferred to a future round (likely needs DTA TEI scraping).

All works use the generic ``chapter`` splitter EXCEPT the three
Kapital OCR files which route via the state-machine parser. The
distinction is made at the ingest dispatch level (raw_deu vs
raw_deu_ocr directories), not in this works module.
"""

from __future__ import annotations

import re

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    # ─── Wikisource (clean HTML) ──────────────────────────────────
    CorpusWork(
        code="kritik_hegel_rechtsphil_einl",
        title="Zur Kritik der Hegel'schen Rechtsphilosophie. Einleitung",
        translator="(Original)",
        edition_year="1844",
        filenames=("kritik_hegel_rechtsphil_einl.txt",),
        fmt="txt",
        locator="chapter",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    CorpusWork(
        code="oek_phil_manuskripte_1844",
        title="Ökonomisch-philosophische Manuskripte",
        translator="(Original)",
        edition_year="1844",
        filenames=("oek_phil_manuskripte_1844.txt",),
        fmt="txt",
        locator="chapter",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    CorpusWork(
        code="thesen_feuerbach",
        title="Thesen über Feuerbach",
        translator="(Original)",
        edition_year="1845",
        filenames=("thesen_feuerbach.txt",),
        fmt="txt",
        locator="chapter",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    CorpusWork(
        code="heilige_familie",
        title="Die heilige Familie",
        translator="(Original)",
        edition_year="1845",
        filenames=("heilige_familie.txt",),
        fmt="txt",
        locator="chapter",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    CorpusWork(
        code="deutsche_ideologie",
        title="Die deutsche Ideologie",
        translator="(Original)",
        edition_year="1845-46",
        filenames=("deutsche_ideologie.txt",),
        fmt="txt",
        locator="chapter",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    CorpusWork(
        code="elend_philosophie",
        title="Das Elend der Philosophie",
        translator="(Original)",
        edition_year="1847",
        filenames=("elend_philosophie.txt",),
        fmt="txt",
        locator="chapter",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    CorpusWork(
        code="manifest",
        title="Manifest der Kommunistischen Partei",
        translator="(Original)",
        edition_year="1848",
        filenames=("manifest.txt",),
        fmt="txt",
        locator="chapter",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    CorpusWork(
        code="lohnarbeit_kapital",
        title="Lohnarbeit und Kapital",
        translator="(Original)",
        edition_year="1849",
        filenames=("lohnarbeit_kapital.txt",),
        fmt="txt",
        locator="chapter",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    CorpusWork(
        code="brumaire",
        title="Der achtzehnte Brumaire des Louis Bonaparte",
        translator="(Original)",
        edition_year="1852",
        filenames=("brumaire.txt",),
        fmt="txt",
        locator="chapter",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    CorpusWork(
        code="zur_kritik_pol_oekonomie",
        title="Zur Kritik der politischen Ökonomie",
        translator="(Original)",
        edition_year="1859",
        filenames=("zur_kritik_pol_oekonomie.txt",),
        fmt="txt",
        locator="chapter",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    CorpusWork(
        code="lohn_preis_profit",
        title="Lohn, Preis und Profit",
        translator="(Original)",
        edition_year="1865",
        filenames=("lohn_preis_profit.txt",),
        fmt="txt",
        locator="chapter",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    # ─── Grundrisse-derived selections (zeno.org) ─────────────────
    # The full Grundrisse is not freely available as plain text (the
    # standard Dietz Verlag edition is still in copyright). Zeno.org
    # carries the two most-cited standalone pieces: the 1857
    # Einleitung (methodological introduction, often regarded as
    # Marx's most important methodological text) and the "Formen"
    # chapter on pre-capitalist economic formations (Hobsbawm
    # published this in English as a standalone).
    #
    # `fmt="html"` routes through the pipeline's `split_zeno_pages`,
    # which uses the ZENO_PAGE markers `download_marx_zeno.py` writes.
    CorpusWork(
        code="einleitung_grundrisse",
        title="Einleitung zur Kritik der politischen Ökonomie",
        translator="(Original)",
        edition_year="1857",
        filenames=("einleitung_grundrisse.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    CorpusWork(
        code="formen_vorkapitalistisch",
        title="Formen, die der kapitalistischen Produktion vorhergehen",
        translator="(Original)",
        edition_year="1858",
        filenames=("formen_vorkapitalistisch.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    # ─── Das Kapital I–III: MEW 23–25 from mlwerke.de (Wayback) ───
    # Replaces the Internet-Archive OCR of the 1867 first edition
    # (55 mega-chunks of scan noise in the six-chapter structure
    # nobody cites). Files are per-chapter HTML named by MEW start
    # page (me23_049.htm = "Die Ware", MEW 23 p. 49); the wildcard
    # matching lives in `find_work` below — `filenames` stays empty.
    # See perseus/download_kapital_mew.py + corpus/split_kapital_mew.py.
    CorpusWork(
        code="kapital_bd1",
        title="Das Kapital, Band I",
        translator="(Original)",
        edition_year="1867",
        filenames=(),
        fmt="html",
        locator="kapital_mew",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    CorpusWork(
        code="kapital_bd2",
        title="Das Kapital, Band II",
        translator="(Original)",
        edition_year="1885",
        filenames=(),
        fmt="html",
        locator="kapital_mew",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
    CorpusWork(
        code="kapital_bd3",
        title="Das Kapital, Band III",
        translator="(Original)",
        edition_year="1894",
        filenames=(),
        fmt="html",
        locator="kapital_mew",
        lang="deu",
        corpus="marx",
        author="Marx",
    ),
)

_base_find_work = make_find_work(WORKS)

_KAPITAL_BY_PREFIX = {
    "me23": next(w for w in WORKS if w.code == "kapital_bd1"),
    "me24": next(w for w in WORKS if w.code == "kapital_bd2"),
    "me25": next(w for w in WORKS if w.code == "kapital_bd3"),
}

_KAPITAL_FILE_RE = re.compile(r"^(me2[345])_\d+\.html?$")


def find_work(filename: str) -> CorpusWork | None:
    """Exact-name lookup plus the MEW-chapter wildcard: any
    ``me{23,24,25}_NNN.htm`` file belongs to its Kapital volume (the
    per-chapter page set is ~110 files, enumerated by the downloader —
    not worth hard-coding)."""

    w = _base_find_work(filename)
    if w is not None:
        return w
    m = _KAPITAL_FILE_RE.match(filename)
    if m:
        return _KAPITAL_BY_PREFIX[m.group(1)]
    return None
