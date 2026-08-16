"""Per-work configuration for Nietzsche ingest.

25 German zeno.org works (below) plus hand-curated eKGWB Nachlass
notebooks: any `nachlass_kgw_<year>_<group>.html` saved from
nietzschesource.org and dropped into the raw dir is recognised by
`find_work` and parsed by the `ekgwb` splitter into one chunk per
`NF-<year>,<group>[<n>]` fragment. Local-only; see the find_work note.

The 25 zeno works are organized as:

* **Mature published oeuvre (14 works)** — every philosophical book
  Nietzsche himself published, from *Die Geburt der Tragödie* (1872)
  to the 1888 "harvest year" books (GD, AC, EH, NW). Plus
  Dionysos-Dithyramben (1888 late poems, often grouped with EH).
* **Nachlass (1 work)** — *Aus dem Nachlaß der Achtzigerjahre*, the
  canonical published 1880s Nachlass selection. 32 zeno sub-pages.
  This is the published Naumann-edition selection, NOT the modern
  KGW/eKGWB Nachlass (which is 30k+ pages and only accessible via
  the JS-rendered nietzschesource.org).
* **Early essays + lectures (8 works)** — pre-1872 lectures and the
  1872-73 essays often classified as "early Nachlass" in standard
  scholarship (Über Wahrheit und Lüge, Philosophie im tragischen
  Zeitalter, etc.).
* **Briefe (1 work)** — correspondence, 29 zeno sub-pages.

All works use `fmt="html"` so the corpus pipeline routes them through
`split_zeno_pages` (chapter boundaries at `<!-- ZENO_PAGE: -->`
markers written by `perseus/download_nietzsche_de.py`).

The full eKGWB Nachlass (Colli/Montinari critical edition's notebook
volumes), the *Wille zur Macht* compilation as a standalone work, and
English translations are explicitly out of scope this round.
"""

from __future__ import annotations

import re

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    # ─── Mature published oeuvre (14) ────────────────────────────
    CorpusWork(
        code="geburt_tragodie",
        title="Die Geburt der Tragödie",
        translator="(Original)",
        edition_year="1872",
        filenames=("geburt_tragodie.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="unzeitgemaesse_betrachtungen",
        title="Unzeitgemäße Betrachtungen",
        translator="(Original)",
        edition_year="1873-1876",
        filenames=("unzeitgemaesse_betrachtungen.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="menschliches_allzumenschliches",
        title="Menschliches, Allzumenschliches",
        translator="(Original)",
        edition_year="1878-1880",
        filenames=("menschliches_allzumenschliches.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="morgenroete",
        title="Morgenröte",
        translator="(Original)",
        edition_year="1881",
        filenames=("morgenroete.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="froehliche_wissenschaft",
        title="Die fröhliche Wissenschaft",
        translator="(Original)",
        edition_year="1882",
        filenames=("froehliche_wissenschaft.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="zarathustra",
        title="Also sprach Zarathustra",
        translator="(Original)",
        edition_year="1883-1885",
        filenames=("zarathustra.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="jenseits_gut_boese",
        title="Jenseits von Gut und Böse",
        translator="(Original)",
        edition_year="1886",
        filenames=("jenseits_gut_boese.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="genealogie_moral",
        title="Zur Genealogie der Moral",
        translator="(Original)",
        edition_year="1887",
        filenames=("genealogie_moral.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="fall_wagner",
        title="Der Fall Wagner",
        translator="(Original)",
        edition_year="1888",
        filenames=("fall_wagner.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="goetzen_daemmerung",
        title="Götzen-Dämmerung",
        translator="(Original)",
        edition_year="1888",
        filenames=("goetzen_daemmerung.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="antichrist",
        title="Der Antichrist",
        translator="(Original)",
        edition_year="1888",
        filenames=("antichrist.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="ecce_homo",
        title="Ecce Homo",
        translator="(Original)",
        edition_year="1888",  # written 1888; first published 1908
        filenames=("ecce_homo.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="nietzsche_contra_wagner",
        title="Nietzsche contra Wagner",
        translator="(Original)",
        edition_year="1888",
        filenames=("nietzsche_contra_wagner.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="dionysos_dithyramben",
        title="Dionysos-Dithyramben",
        translator="(Original)",
        edition_year="1888",
        filenames=("dionysos_dithyramben.html",),
        fmt="html",
        locator="chapter",
        # Verse: every line is a "paragraph" to the chapter splitter, so
        # this came out as 783 chunks at a 27-character median and 779 of
        # them fell below the 60-char retrieval floor — the work was in
        # the index and unreachable (#417). 600 gives 40 chunks at a
        # 610-char median; the only Nietzsche work that needs this.
        min_paragraph_chars=600,
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),

    # ─── Nachlass (1) ─────────────────────────────────────────────
    CorpusWork(
        code="nachlass_achtzigerjahre",
        title="Aus dem Nachlaß der Achtzigerjahre",
        translator="(Original)",
        edition_year="1880-1888",  # writing dates; Naumann-edition selection
        filenames=("nachlass_achtzigerjahre.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),

    # ─── Early essays / lectures / "early Nachlass" (8) ───────────
    CorpusWork(
        code="wahrheit_luege",
        title="Über Wahrheit und Lüge im außermoralischen Sinn",
        translator="(Original)",
        edition_year="1873",
        filenames=("wahrheit_luege.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="philosophie_tragisches_zeitalter",
        title="Die Philosophie im tragischen Zeitalter der Griechen",
        translator="(Original)",
        edition_year="1873",
        filenames=("philosophie_tragisches_zeitalter.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="zukunft_bildung",
        title="Über die Zukunft unserer Bildungs-Anstalten",
        translator="(Original)",
        edition_year="1872",
        filenames=("zukunft_bildung.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="fuenf_vorreden",
        title="Fünf Vorreden zu fünf ungeschriebenen Büchern",
        translator="(Original)",
        edition_year="1872",
        filenames=("fuenf_vorreden.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="homer_philologie",
        title="Homer und die klassische Philologie",
        translator="(Original)",
        edition_year="1869",
        filenames=("homer_philologie.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="mahnruf_deutschen",
        title="Mahnruf an die Deutschen",
        translator="(Original)",
        edition_year="1873",
        filenames=("mahnruf_deutschen.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="wir_philologen",
        title="Wir Philologen",
        translator="(Original)",
        edition_year="1875",  # Nachlass essay drafted ~1875
        filenames=("wir_philologen.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),
    CorpusWork(
        code="wissenschaft_weisheit",
        title="Wissenschaft und Weisheit im Kampfe",
        translator="(Original)",
        edition_year="1875",
        filenames=("wissenschaft_weisheit.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),

    # ─── Correspondence (1) ──────────────────────────────────────
    CorpusWork(
        code="briefe",
        title="Briefe",
        translator="(Original)",
        edition_year="1858-1889",
        filenames=("briefe.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
    ),

    # ─── KGW Nachlass — hand-curated eKGWB notebooks ──────────────
    # Individual Nachgelassene-Fragmente notebook groups saved by hand
    # from nietzschesource.org (eKGWB) for personal research, parsed by
    # `split_ekgwb` into one chunk per fragment keyed on its canonical
    # `NF-<year>,<group>[<n>]` siglum. Local-only (data/ is gitignored),
    # not redistributed. Add a notebook by dropping its saved .html into
    # data/nietzsche/raw_deu/ and appending a CorpusWork here. All share
    # the title "Nachgelassene Fragmente (KGW)" so they read as one work
    # subdivided by siglum; `book` (from the splitter) names the group.
    CorpusWork(
        code="nachlass_kgw_1884_25",
        title="Nachgelassene Fragmente (KGW)",
        translator="(Original)",
        # Constant across all notebooks: they're one edition (the single
        # critical edition), and the schema allows one edition per
        # (work, language). The specific year lives in the `book` label
        # and the NF-<year> siglum, both derived from the page header.
        edition_year="1869-1889",
        filenames=("nachlass_kgw_1884_25.html",),
        fmt="html",
        locator="ekgwb",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
        citation_system="paragraph",
    ),
)

_base_find_work = make_find_work(WORKS)

# Drop-and-go for additional eKGWB Nachlass notebooks: any file named
# `nachlass_kgw_<year>_<group>.html` dropped into data/nietzsche/raw_deu/
# is recognised without editing WORKS. The `ekgwb` splitter derives the
# group label and per-fragment NF-<year> sigla from the page header
# itself, so the filename's year/group are only a routing convention —
# all notebooks resolve to the single shared work + edition (see the
# edition_year note above).
_NACHLASS_KGW_RE = re.compile(r"^nachlass_kgw_\d{4}_\d+\.html$")


def find_work(filename: str) -> CorpusWork | None:
    w = _base_find_work(filename)
    if w is not None:
        return w
    if _NACHLASS_KGW_RE.match(filename) is None:
        return None
    return CorpusWork(
        code=filename[:-5],
        title="Nachgelassene Fragmente (KGW)",
        translator="(Original)",
        edition_year="1869-1889",
        filenames=(filename,),
        fmt="html",
        locator="ekgwb",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
        citation_system="paragraph",
    )
