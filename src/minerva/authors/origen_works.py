"""Per-work configuration for Origen ingest.

One work bilingually — *Contra Celsum* (Κατὰ Κέλσου, c. 248 CE), an
eight-book refutation of Celsus's lost 2nd-c. CE *Alēthēs Logos*. The
Celsus polemic survives **only** as verbatim quotations Origen embeds
within his refutation — most famously the women/children/slaves
passage at *Contra Celsum* 3.44, the antecedent of Nietzsche's
slave-morality thesis in the *Genealogy of Morals*.

Sources (planned — Phase B will verify URLs and fetch):

  * Greek: Koetschau 1899 *Die griechischen christlichen
    Schriftsteller* (GCS), fully public-domain. Available via
    First1KGreek under TLG 2042 (confirmed). Borret's 1967-69
    *Sources Chrétiennes* critical edition with French facing-page is
    in copyright; older PD wins.
  * English: Frederick Crombie 1872 translation in the *Ante-Nicene
    Fathers* (ANF) Vol IV, fully PD. Available cleanly on
    [CCEL](https://ccel.org/ccel/origen/origen04). Chadwick (1953,
    Cambridge) is the gold-standard modern translation but in
    copyright.

Citation system: ``paragraph``. The standard scholarly citation is
``C.Cels. III.44`` (book.chapter); ``book`` field carries Roman-
numeral book label and ``section`` carries ``book.chapter`` or
``Book III, ch. 44`` per the corpus convention.

Celsus himself is added as an **out-of-corpus reference target** in
the same pass — see ``refs/rules/origen.py``'s ``origen_celsus`` rule
and the bidirectional ``nietzsche_celsus`` / ``hegel_celsus`` /
``augustine_celsus`` rules. *De Principiis*, Origen's other major
work, is deferred to a Phase 2 Origen addition.

See ``add-origen-celsus-plan`` memory for the full ingest plan and
the optional Celsus-quotation chunk-marker (``speaker="Celsus"``)
refinement that would let the UI distinguish Celsus's actual surviving
words from Origen's surrounding prose.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="contra_celsum_grc",
        title="Contra Celsum",
        translator="(Original)",
        edition_year="c. 248 CE (Koetschau ed., 1899)",
        filenames=("contra_celsum_grc.xml",),
        fmt="xml",
        locator="chapter",
        lang="grc",
        corpus="origen",
        author="Origen",
        citation_system="paragraph",
    ),
    CorpusWork(
        code="contra_celsum_eng",
        title="Contra Celsum",
        translator="Frederick Crombie",
        edition_year="1872",  # Ante-Nicene Fathers Vol IV
        filenames=("contra_celsum_eng.html",),
        fmt="html",
        locator="chapter",
        lang="eng",
        corpus="origen",
        author="Origen",
        citation_system="paragraph",
    ),
)


find_work = make_find_work(WORKS)
