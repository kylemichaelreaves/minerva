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
    # The Greek is First1KGreek ``tlg0614.tlg001.1st1K-grc1`` —
    # Schneidewin's *Fabulae Aesopeae*, EpiDoc TEI P5, re-sourced
    # 2026-08-15. It is parsed by ``tei_p5.parse_dir`` (the same path as
    # the Phaedrus half) and so has NO ``CorpusWork`` entry here; only
    # its title override lives below, in ``TEI_P5_WORK_TITLES``.
    #
    # **Correction, 2026-08-15.** This block used to read "No clean TEI
    # source exists on PerseusDL / First1KGreek / Diorisis / Scaife CTS
    # for TLG 1670; archive.org OCR is the only PD path." The probes were
    # real and the conclusion was wrong, because **Babrius is tlg0614,
    # not tlg1670** — under the number searched, both repos genuinely
    # 404. Cost of the error: the archive.org Crusius OCR carried its
    # critical apparatus into the corpus as text. 498 chunks and 501,783
    # characters were indexed as Babrius, of which the Schneidewin
    # edition says roughly 72,000 are (#398).
    #
    # The English is still Davies 1860 (``bib_fict_4103078``) via
    # archive.org OCR; First1KGreek carries no translation. Its known
    # limitation stands: 92 of the expected ~143 fables, because the
    # extractor's all-caps-title detector misses OCR-mangled title
    # lines — and it is chunked one verse line per chunk (#399).
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

#: Work titles for `tei_p5.parse_dir`'s flat layout, which otherwise
#: derives the title from the file stem. Babrius's Greek needs to match
#: the `Fables (Babrius)` its English half carries, or the two halves
#: stop grouping as one work in the Reader and the citation graph.
#:
#: Phaedrus is deliberately absent. `phaedrus_lat.xml` derives
#: `Phaedrus`, which is what it has been ingested as since 2026-05-29;
#: aligning it with the `Fables (Phaedrus)` in `WORKS` above would move
#: all 232 of its `chunk_id`s for a cosmetic gain. That mismatch between
#: config and index predates this file's re-source and is left alone.
TEI_P5_WORK_TITLES: dict[str, str] = {"babrius_grc.xml": "Fables (Babrius)"}
