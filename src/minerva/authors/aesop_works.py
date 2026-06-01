"""Per-work configuration for Aesop ingest.

The Aesopic tradition exists as multiple text-streams, none of which
is Aesop's original. We ingest the two canonical verse collections —
the broader prose tradition (Halm 1852 / Chambry 1925) is a Phase 2
addition once the verse pair is wired up.

Sources (planned — Phase B will verify URLs and fetch):

  * **Babrius** (1st-2nd c. CE) — Greek choliambic verse, ~143
    fables. Crusius 1897 / Halm 1852 editions are PD; available via
    Perseus or First1KGreek (TLG 1670). Davies 1860 English
    translation is PD; otherwise Crusius's facing-page from archive.org.
  * **Phaedrus** (1st c. CE) — Latin iambic verse, ~94 fables.
    Perseus PHI 0975 carries the Bährens edition; English by Smart
    (1828) is PD on Project Gutenberg.

Numbering: the **Perry index** (Perry 1952, 584-entry standardisation)
is the canonical cross-walk between collections. Each ``section``
records the per-collection citation (e.g. ``Babr. 47`` or ``Phaedr.
IV.4``) with a Perry equivalent in parentheses where known. The
famous *Boastful Athlete* fable (the source of Hegel's ``Hic Rhodus,
hic salta``) is Babrius 47 / Perry 33.

Author attribution: all four works are catalogued as ``author="Aesop"``
with Babrius and Phaedrus credited via ``translator`` — philosophers
cite "Aesop", not "Babrius's version of Aesop", and our citation graph
should match that convention.

Citation system: ``paragraph``. Per-collection fable numbers go into
``section``; ``book`` carries the collection name for the Reader's
breadcrumb.

See ``add-aesop-plan`` memory for the full ingest plan, including the
``_ORIGINAL_LANG_BY_CORPUS`` resolution (single ``aesop`` slug with
per-chunk lang tagging vs. ``aesop-grc`` / ``aesop-lat`` split).
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    # ─── Phaedrus (Latin verse + Perseus English) ──────────────────
    # Sourced 2026-05-29 from PerseusDL/canonical-latinLit phi0975
    # (Perseus edition perseus-lat2 + perseus-eng1).
    CorpusWork(
        code="phaedrus_lat",
        title="Fables (Phaedrus)",
        translator="(Phaedrus, Latin verse)",
        edition_year="1st c. CE (Perseus phi0975 / Bährens-derived)",
        filenames=("phaedrus_lat.xml",),
        fmt="xml",
        locator="chapter",
        lang="lat",
        corpus="aesop",
        author="Aesop",
        citation_system="paragraph",
    ),
    CorpusWork(
        code="phaedrus_eng",
        title="Fables (Phaedrus)",
        translator="C. Smart (Perseus perseus-eng1)",
        edition_year="1828",
        filenames=("phaedrus_eng.xml",),
        fmt="xml",
        locator="chapter",
        lang="eng",
        corpus="aesop",
        author="Aesop",
        citation_system="paragraph",
    ),

    # ─── Babrius (Greek verse + English) ──────────────────────────
    # Sourced 2026-06-01 from archive.org OCR — Crusius 1897 critical
    # edition (``babriifabvlaeaes00babruoft``) for the Greek and
    # Davies 1860 (``bib_fict_4103078``) for English verse. No clean
    # TEI source exists on PerseusDL / First1KGreek / Diorisis /
    # Scaife CTS for TLG 1670; archive.org OCR is the only PD path.
    #
    # KNOWN LIMITATIONS:
    #   * Crusius's critical apparatus interleaves with verses and
    #     leaks through the extractor's heuristic filter; Greek file
    #     ships with ~496 "fables" vs ~143 real ones, the surplus
    #     being apparatus-block fragments mistaken for fable starts.
    #     Hand-curation is the safety net.
    #   * Davies 1860 emits 92 of the expected ~143 fables — the
    #     extractor's all-caps-title detector misses cases where
    #     OCR mangled the title line. Better-than-zero coverage.
    CorpusWork(
        code="babrius_grc",
        title="Fables (Babrius)",
        translator="(Babrius, Greek verse)",
        edition_year="2nd c. CE (Crusius ed., 1897)",
        filenames=("babrius_grc.txt",),
        fmt="txt",
        locator="chapter",
        lang="grc",
        corpus="aesop",
        author="Aesop",
        citation_system="paragraph",
    ),
    CorpusWork(
        code="babrius_eng",
        title="Fables (Babrius)",
        translator="J. Davies",
        edition_year="1860",
        filenames=("babrius_eng.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="aesop",
        author="Aesop",
        citation_system="paragraph",
    ),
)


find_work = make_find_work(WORKS)
