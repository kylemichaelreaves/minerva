#!/usr/bin/env python3
"""Download two Grundrisse-derived Marx works from zeno.org.

The Grundrisse (1857-58 notebooks) was first published in 1939; the
standard Dietz Verlag edition (MEW Bd 42, 1983) is still in copyright,
so PG-DE / Wikisource / archive.org all decline to host the full
text and the mlwerke.de pages are dead. But zeno.org carries the
two most-cited stand-alone selections from Grundrisse:

  * Einleitung [zur Kritik der politischen Ökonomie] (Aug 1857) —
    Marx's General Introduction, often regarded as the most
    important methodological text in his corpus. Multi-section
    on zeno (I.1, I.2, I.3, I.4 + Lesarten).

  * Formen, die der kapitalistischen Produktion vorhergehen
    (1857-58) — "Forms which precede capitalist production." Single-
    page on zeno. Published by Hobsbawm as a standalone in English
    as *Pre-Capitalist Economic Formations*.

zeno serves both as HTML with sub-page navigation. We BFS-walk each
work's URL tree and concatenate the HTML pages with `<!-- ZENO_PAGE: -->`
markers — the same convention `download_hegel_de.py` uses and that
the downstream `split_zeno_pages` recognizes for chapter boundaries.

Output:
    data/marx/raw_deu/einleitung_grundrisse.html
    data/marx/raw_deu/formen_vorkapitalistisch.html

Run:
    uv run python perseus/download_marx_zeno.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _zeno import ZenoWork, add_crawl_args, main_for

MAX_PAGES = 100

# (output filename, zeno root URL path)
WORKS: list[ZenoWork] = [
    ZenoWork(
        "einleitung_grundrisse.html",
        "/Philosophie/M/Marx,+Karl/Einleitung+%5Bzur+Kritik+der+politischen+%C3%96konomie%5D",
    ),
    ZenoWork(
        "formen_vorkapitalistisch.html",
        "/Philosophie/M/Marx,+Karl/Formen,+die+der+kapitalistischen+Produktion+vorhergehen",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/marx/raw_deu/.",
    )
    add_crawl_args(parser)
    args = parser.parse_args()
    return main_for(WORKS, args.data_root / "marx" / "raw_deu", args, max_pages=MAX_PAGES)


if __name__ == "__main__":
    raise SystemExit(main())
