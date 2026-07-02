"""Per-work configuration for Descartes ingest.

Five works land here, sourced from two pipelines:

Project Gutenberg (`perseus/download_descartes.py`):
  • Meditationes de prima philosophia (Latin, Buchenau 1907 edition)
  • Discours de la méthode (French original, 1637)
  • Méditations métaphysiques (French, Luynes 1647 translation)

Wikisource (`perseus/download_descartes_wikisource.py`):
  • Principia philosophiae (Latin, complete — all four Pars)
  • Principes de la philosophie (French Picot 1647, Pars I only;
    Parts II–IV are not on Wikisource and remain a future pass.)

Files in `data/descartes/raw_la/` and `data/descartes/raw_fr/` are
matched to a CorpusWork via `find_work(filename)`; the pipeline then runs
the file through `corpus.split_descartes` (locator='descartes') or
`corpus.split_descartes_articles` (locator='descartes_articles')
depending on the per-CorpusWork declared locator.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="meditationes",
        title="Meditationes de prima philosophia",
        translator="(Original)",
        edition_year="1641",
        filenames=("meditationes.txt",),
        fmt="txt",
        locator="descartes",
        lang="lat",
        corpus="descartes",
        author="Descartes",
    ),
    CorpusWork(
        code="discours",
        title="Discours de la méthode",
        translator="(Original)",
        edition_year="1637",
        filenames=("discours.txt",),
        fmt="txt",
        locator="descartes",
        lang="fra",
        corpus="descartes",
        author="Descartes",
    ),
    CorpusWork(
        code="meditations_fr",
        # Luynes 1647 translation — modelled as its own CorpusWork row (its
        # own `original_language='fra'`) to mirror the existing
        # Pinkard/Inwood Phenomenology pattern where translations live
        # as sibling Works.
        title="Méditations métaphysiques",
        translator="Luynes",
        edition_year="1647",
        filenames=("meditations.txt",),
        fmt="txt",
        locator="descartes",
        lang="fra",
        corpus="descartes",
        author="Descartes",
    ),
    CorpusWork(
        code="principia",
        title="Principia philosophiae",
        translator="(Original)",
        edition_year="1644",
        filenames=("principia.txt",),
        fmt="txt",
        # Article-numbered locator — `[N.NNN]` markers in the source
        # drive split_descartes_articles, which emits one chunk per
        # article (487 total across the four Pars).
        locator="descartes_articles",
        lang="lat",
        corpus="descartes",
        author="Descartes",
    ),
    CorpusWork(
        code="principes",
        # Picot 1647 French translation. Two source files cover the
        # work:
        #   • principes_pars1.txt — Wikisource Desrez transcription
        #     of Pars I (76 articles, clean text).
        #   • principes_pars2to4.txt — Cousin Tome III OCR (Pars II,
        #     III, IV; article numbering is approximate — the OCR
        #     loses the marginal article markers, so we paragraph-
        #     segment within each Partie and number sequentially).
        # Both files share the `[N.NNN]` marker format so the
        # existing `descartes_articles` splitter handles them
        # uniformly.
        title="Principes de la philosophie",
        translator="Picot",
        edition_year="1647",
        filenames=("principes_pars1.txt", "principes_pars2to4.txt"),
        fmt="txt",
        locator="descartes_articles",
        lang="fra",
        corpus="descartes",
        author="Descartes",
    ),
    CorpusWork(
        code="objections",
        # The seven sets of Objections to the Meditations and
        # Descartes' Replies — Clerselier's 1647 French translation as
        # printed in Cousin's 1824 Œuvres (fr.wikisource transcription;
        # see perseus/download_descartes_objections.py). Coverage: sets
        # I–IV complete, V objections only, VI complete. Réponses V,
        # the Septièmes (Bourdin) set, and the letter to Clerselier are
        # not transcribed on fr.wikisource — an AT VII re-source would
        # be needed for those.
        #
        # ⚠ Attribution: the Objections are NOT Descartes's — the
        # splitter types them block_type='objection' with the objector
        # (Caterus/Mersenne/Hobbes/Arnauld/Gassendi/…) in `speaker`,
        # and `retrieve.format_locator` cites them as
        # "… — objection (Hobbes)". Only the Replies speak as
        # Descartes.
        title="Objections et Réponses",
        translator="Clerselier (éd. Cousin)",
        edition_year="1647",
        filenames=(
            "objections_obj1.html",
            "objections_rep1.html",
            "objections_obj2.html",
            "objections_rep2.html",
            "objections_obj3.html",
            "objections_obj4.html",
            "objections_rep4.html",
            "objections_obj5.html",
            "objections_obj6.html",
            "objections_rep6.html",
        ),
        fmt="html",
        locator="descartes_objections",
        lang="fra",
        corpus="descartes",
        author="Descartes",
    ),
)


find_work = make_find_work(WORKS)
