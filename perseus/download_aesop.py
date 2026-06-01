#!/usr/bin/env python3
"""Download Aesop's Fables (Babrius grc + Phaedrus lat) — PHASE B SKELETON.

Per [[add-aesop-plan]] memory, the planned sources are:

* Babrius (Greek choliambic verse, 1st-2nd c. CE) — Crusius 1897 or
  Halm 1852 editions, fully public-domain. Possible hosts:
  Perseus / First1KGreek (TLG 1670 — needs verification),
  archive.org for the Crusius facing-page volume.
* Phaedrus (Latin iambic verse, 1st c. CE) — Perseus PHI 0975
  (Bährens 1884 edition).
* English translations: Davies 1860 (Babrius) and Smart 1828
  (Phaedrus), both PD on archive.org / Project Gutenberg.

Cross-walk: per-collection fable numbers cross-reference the Perry
Index (Perry 1952, 584-entry standardisation). Notable for our
philosophical citations: the *Boastful Athlete* fable (Babrius 47 /
Perry 33) is the source of Hegel's "Hic Rhodus, hic salta" /
"Hier ist die Rose, hier tanze" in the Preface to *Philosophy of
Right*, which Marx reuses in *18th Brumaire of Louis Bonaparte* ch. 1.

Output layout:

    data/aesop/babrius_grc.xml
    data/aesop/babrius_eng.txt
    data/aesop/phaedrus_lat.xml
    data/aesop/phaedrus_eng.txt

Until Phase B runs this script and writes those files, the ``aesop``
corpus produces zero chunks at re-ingest time.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "PHASE B TODO: source Babrius + Phaedrus.\n"
        "  Babrius grc: Crusius 1897 or Perseus / First1KGreek TLG 1670.\n"
        "  Phaedrus lat: Perseus PHI 0975 (Bährens 1884).\n"
        "  English: Davies 1860 + Smart 1828 (archive.org / Gutenberg).\n"
        "  Output to: data/aesop/{babrius,phaedrus}_{grc,lat,eng}.{xml,txt}\n"
        "See add-aesop-plan memory.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
