"""Per-work configuration for Arthur de Gobineau ingest.

Single work, four volumes — *Essai sur l'inégalité des races
humaines* (1853-1855, Paris: Firmin Didot). The 1884 reissue / 1853
first edition both digitized on archive.org as ``essaisurlingaliN``
items where N runs 1-4.

The Essai is the racial-determinism reformulation of Boulainvilliers's
Frankish-conquest thesis that Nietzsche absorbs (and then partly
distances himself from). The aristocratic / blood / Aryan material
in GM I.5 ("blond beast"), Götzen-Dämmerung "Was den Deutschen
abgeht", and the Nachlass fragments on Rasse draws on Gobineau
directly.

Citation system: ``paragraph``. The standard French scholarly
citation is volume + book + chapter (``Essai t. II, liv. III, ch. 5``);
``book`` holds the volume identifier here, ``section`` carries
chapter + paragraph.

See ``add-gobineau-renan-plan`` memory for source acquisition log
and the bidirectional refs audit (Nietzsche/Marx → Gobineau rules in
addition to this module's outgoing rules in
``refs/rules/gobineau.py``).
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work


def _vol(n: int) -> CorpusWork:
    return CorpusWork(
        code=f"essai_inegalite_vol{n}_fra",
        title=f"Essai sur l'inégalité des races humaines, vol. {n}",
        translator="(Original)",
        edition_year="1853-1855 (Paris, Firmin Didot)",
        filenames=(f"essai_inegalite_vol{n}_fra.txt",),
        fmt="txt",
        locator="chapter",
        lang="fra",
        corpus="gobineau",
        author="Gobineau",
        citation_system="paragraph",
        # Verso and recto running heads of all four volumes (#578).
        ocr_reflow=("De l'inégalité", "Des races humaines"),
    )


WORKS: tuple[CorpusWork, ...] = (_vol(1), _vol(2), _vol(3), _vol(4))


find_work = make_find_work(WORKS)
