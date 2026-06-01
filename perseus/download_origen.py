#!/usr/bin/env python3
"""Download Origen's *Contra Celsum* (Greek + English) — PHASE B SKELETON.

Per [[add-origen-celsus-plan]] memory:

* Greek: First1KGreek TLG 2042 (confirmed available — see
  https://github.com/OpenGreekAndLatin/First1KGreek/tree/master/data/tlg2042
  for the canonical work list). Eight-book *Contra Celsum* sits as
  one of the ``perseus-grc*`` editions inside that tree. License:
  CC-BY-SA-4.0 per First1KGreek's standard licence header.
* English: Frederick Crombie 1872 translation in the *Ante-Nicene
  Fathers* (ANF) Vol IV. Fully public-domain via
  https://ccel.org/ccel/origen/origen04 — CCEL serves clean HTML.

Output layout:

    data/origen/contra_celsum_grc.xml    (First1KGreek TEI P5)
    data/origen/contra_celsum_eng.html   (CCEL ANF Vol IV)

The Celsus fragments preserved within Origen's prose — most famously
the women/children/slaves passage at *Contra Celsum* 3.44, antecedent
of Nietzsche's slave-morality thesis in the *Genealogy of Morals* —
are the philosophical payoff of this ingest. Celsus himself stays as
an out-of-corpus reference target (no data dir), wired via the
``origen_celsus`` rule + the bidirectional ``nietzsche_celsus`` /
``hegel_celsus`` / ``augustine_celsus`` rules.

A future Phase 2 Origen pass would add *De Principiis* (Περὶ Ἀρχῶν)
as the second pillar; deferred so this batch stays focused on the
Celsus thread.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "PHASE B TODO: source Origen's *Contra Celsum*.\n"
        "  Greek: First1KGreek TLG 2042 (CC-BY-SA-4.0, confirmed).\n"
        "  English: CCEL ANF Vol IV — Crombie 1872.\n"
        "  Output to: data/origen/contra_celsum_grc.xml\n"
        "             data/origen/contra_celsum_eng.html\n"
        "See add-origen-celsus-plan memory.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
