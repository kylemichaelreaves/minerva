"""Per-work configuration for Henri de Boulainvilliers ingest.

Posthumous works (Boulainvilliers died 1722; everything below is
1727+ publication). The Frankish-conquest two-race thesis in the
*Histoire* / *Essai* is the proximate historical source for
Nietzsche's master-morality / blond-beast material in *Genealogie
der Moral* I.5/I.11; the *Lettres* extend the political-historical
argument in epistolary form and are the one work with a contemporary
PD English translation (Dryden the Younger, 1739).

Source acquisition (Phase B):

  * **Histoire de l'ancien gouvernement de la France** — first
    edition 1727 (3 vols, La Haye / Amsterdam, Le Mort de Liège).
    Bundled with the *Etat de la France* in some editions; the 1727
    archive.org item ``etatdelafranceda01boul`` includes it as a
    preliminary set of essays. Cleaner OCR may be available in the
    1752 reissue (multiple ``etatdelafrance0*boul`` items).
  * **Essai sur la noblesse de France** — 1732 (Amsterdam). Often
    bound with the *Histoire* in the same volume; sometimes
    separate. archive.org items overlap with the *Histoire*.
  * **Lettres sur les anciens parlemens de France** — 1753 French
    edition; 1739 English Dryden translation
    (``bim_eighteenth-century_an-historical-account-of_boulainvilliers-henri-_1739_1``
    on archive.org).

Citation system: ``paragraph``. The standard 18th-c French scholarly
citation for Boulainvilliers is volume + book + chapter
(``Histoire t. I, liv. II, ch. 5``); ``book`` holds the
volume/livre label, ``section`` the chapter + paragraph.

See ``add-boulainvilliers-plan`` memory for the full ingest plan,
including the bidirectional refs-rule audit (Nietzsche / Marx /
Hegel → Boulainvilliers rules in addition to this module's own
outgoing rules in ``refs/rules/boulainvilliers.py``).
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    # ─── Histoire de l'ancien gouvernement de la France ─────────────
    CorpusWork(
        code="histoire_anc_gouv_fra",
        title="Histoire de l'ancien gouvernement de la France",
        translator="(Original)",
        edition_year="1727",
        filenames=("histoire_anc_gouv_fra.txt",),
        fmt="txt",
        locator="chapter",
        lang="fra",
        corpus="boulainvilliers",
        author="Boulainvilliers",
        citation_system="paragraph",
    ),
    # ─── Essai sur la noblesse de France ───────────────────────────
    # 1732 first edition (Amsterdam, anonymous). Sourced from Gallica
    # `bd6t5770025p` via the user's manually-fetched EPUB (a modern
    # re-edition with proper introduction + Chapitre 1 / 2 / 3
    # divisions). The pipeline's EPUB branch failed on the EPUB's
    # accented filename (``Tabledesmatières.html``), so we pre-extract
    # to plain text with ALL-CAPS ``CHAPITRE N`` heading anchors that
    # the chapter splitter's secondary branch
    # (``[A-Z][A-Z \\-—:,'.]{6,80}``) latches onto. Extraction
    # script: ``scripts/extract-essai-noblesse.py`` (one-shot).
    CorpusWork(
        code="essai_noblesse_fra",
        title="Essai sur la noblesse de France",
        translator="(Original)",
        edition_year="1732",
        filenames=("essai_noblesse_fra.txt",),
        fmt="txt",
        locator="chapter",
        lang="fra",
        corpus="boulainvilliers",
        author="Boulainvilliers",
        citation_system="paragraph",
    ),
    # ─── Lettres sur les anciens parlemens de France ────────────────
    CorpusWork(
        code="lettres_parlemens_fra",
        title="Lettres sur les anciens parlemens de France",
        translator="(Original)",
        edition_year="1753",
        filenames=("lettres_parlemens_fra.txt",),
        fmt="txt",
        locator="chapter",
        lang="fra",
        corpus="boulainvilliers",
        author="Boulainvilliers",
        citation_system="paragraph",
    ),
    # ─── An historical account of the antient parliaments of France
    #     (Dryden the Younger, 1739) — only PD English translation of
    #     any Boulainvilliers work. Bibliographic id on archive.org:
    #     bim_eighteenth-century_an-historical-account-of_boulainvilliers-henri-_1739_1
    CorpusWork(
        code="lettres_parlemens_eng",
        title="Lettres sur les anciens parlemens de France",
        translator="John Dryden the Younger",
        edition_year="1739",
        filenames=("lettres_parlemens_eng.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="boulainvilliers",
        author="Boulainvilliers",
        citation_system="paragraph",
    ),
)


find_work = make_find_work(WORKS)
