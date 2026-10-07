"""Per-work configuration for Arthur de Gobineau ingest.

Single work, four tomes — *Essai sur l'inégalité des races humaines*,
first edition (Paris: Firmin Didot; Hanover: Rumpler): tomes I-II 1853,
tomes III-IV 1855. One CorpusWork per tome, titled by tome. Each comes
from its own archive.org scan, chosen by its title page — the archive.org
ids' ``01``..``06`` are Google disambiguators, not volume numbers (#742).
The 1884 two-tome reset is a different setting and is not used. Sources
and the per-tome guards are in ``perseus/download_gobineau_renan.py``.

The Essai is the racial-determinism reformulation of Boulainvilliers's
Frankish-conquest thesis that Nietzsche absorbs (and then partly
distances himself from). The aristocratic / blood / Aryan material
in GM I.5 ("blond beast"), Götzen-Dämmerung "Was den Deutschen
abgeht", and the Nachlass fragments on Rasse draws on Gobineau
directly.

Citation system: ``paragraph``. The standard French scholarly
citation is volume + book + chapter (``Essai t. II, liv. III, ch. 5``).
The tome is the *work* here, as with Renan's *Histoire du peuple
d'Israël* and Hegel's *Lectures on the History of Philosophy*. ``book``
holds the chapter splitter's heading label, not a volume id: title-cased,
with any subtitle lines just above merged in (``Civilisation Antique
Rayonnant De L'asie Centrale Au Sud-ouest. Chapitre V``); ``section`` is
that label + ``¶N``. The livre is recorded only where its heading is
plain ASCII capitals — ``LIVRE SECOND.`` splits, ``LIVRE CINQUIÈME.``
does not, and neither does a first chapter the OCR reads as
``CHAPITRE I er .``.

See ``add-gobineau-renan-plan`` memory for source acquisition log
and the bidirectional refs audit (Nietzsche/Marx → Gobineau rules in
addition to this module's outgoing rules in
``refs/rules/specs/gobineau.yaml``).
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV"}
_YEAR = {1: 1853, 2: 1853, 3: 1855, 4: 1855}


def _tome(n: int) -> CorpusWork:
    return CorpusWork(
        code=f"essai_inegalite_tome{n}_fra",
        title=f"Essai sur l'inégalité des races humaines, tome {_ROMAN[n]}",
        translator="(Original)",
        edition_year=f"{_YEAR[n]} (Paris, Firmin Didot)",
        filenames=(f"essai_inegalite_tome{n}_fra.txt",),
        fmt="txt",
        locator="chapter",
        lang="fra",
        corpus="gobineau",
        author="Gobineau",
        citation_system="paragraph",
        # Verso and recto running heads of all four tomes (#578).
        ocr_reflow=("De l'inégalité", "Des races humaines"),
    )


WORKS: tuple[CorpusWork, ...] = (_tome(1), _tome(2), _tome(3), _tome(4))


find_work = make_find_work(WORKS)
