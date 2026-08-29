"""Per-work configuration for Theognis ingest.

One work bilingually — the Theognidea anthology of ~1389 elegiac
couplets (6th c. BCE), traditionally attributed to Theognis of Megara
but actually a partly-pseudepigraphal collection compiled around him.
Subject of Nietzsche's 1867 *Zur Geschichte der Theognideischen
Spruchsammlung*, the philological work that earned him his Leipzig
doctorate.

Sources:

  * Greek (re-sourced 2026-08-29, #431): ``el.wikisource.org``'s
    Ἐλεγεῖαι Θεόγνιδος. Complete canonical sequence (lines 1-1389,
    both books), human-transcribed, no critical apparatus.
    Supersedes F. T. Welcker's *Theognidis Reliquiae* (1826), whose
    archive.org OCR turned out to be corrupted — Latin letters
    substituted into Greek words and Welcker's own Latin commentary
    interleaved with the poems as body text (26.9% of the file's
    letters). NOTE: no PerseusDL/First1KGreek source exists for
    Theognis (TLG 0002, not 0238 as an earlier version of this note
    claimed — confirmed against the Perseus Catalog and re-verified
    empty in the canonical-greekLit / First1KGreek repos 2026-08-29).
    The Bergk and Edmonds Loeb editions the original plan recommended
    turned out to be either copyrighted (Edmonds 1931 is gated as
    borrowable on archive.org until end of 2027) or OCR-broken (Bergk
    1854 anthology has Greek glyphs mapped to Roman lookalikes).
  * English: J. Banks, *The Works of Hesiod, Callimachus, and
    Theognis* (1856; ``worksofhesiodca00hesi``). Complete prose
    translation. Page headers give canonical-line-range anchors
    we use as section markers. Not re-sourced — #431 is specifically
    about the Greek text's quality, and Banks isn't flagged as
    corrupted.

Scope: full anthology, both Book 1 (lines 1-1230) and the pseudo-
Theognidean Book 2 (1231-1389). Nietzsche's dissertation argues
specifically about how both books were compiled into the surviving
collection — both are needed for his references to resolve.

Citation system: ``paragraph``. The line-numbered locator
(``Thgn. 1135-1150``) maps onto the section field as ``line-range``
strings; the reader displays them verbatim.

See ``add-theognis-plan`` memory for the full ingest plan.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="theognidea_grc",
        title="Theognidea",
        translator="(Original)",
        edition_year="6th c. BCE (el.wikisource.org ed.)",
        filenames=("theognidea_grc.txt",),
        fmt="txt",
        locator="chapter",
        lang="grc",
        corpus="theognis",
        author="Theognis",
        citation_system="paragraph",
    ),
    CorpusWork(
        code="theognidea_eng",
        title="Theognidea",
        translator="J. Banks",
        edition_year="1856",
        filenames=("theognidea_eng.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="theognis",
        author="Theognis",
        citation_system="paragraph",
    ),
)


find_work = make_find_work(WORKS)
