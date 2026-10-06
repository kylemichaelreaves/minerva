#!/usr/bin/env python3
"""Download Friedrich Schiller's theoretical/aesthetic writings from zeno.org.

Like `download_kant_de.py`, runs the shared `_zeno.py` crawler: BFS-walks each work's URL subtree under
`/Literatur/M/Schiller,+Friedrich/Theoretische+Schriften`, fetches every
reachable subpage, and concatenates them into one `<!-- ZENO_PAGE: ... -->`
marked HTML file per work in `data/schiller/raw_deu/` — the format the
`split_zeno` parser consumes.

Scope is Schiller's aesthetic philosophy: the Aesthetic Education letters
plus the major companion essays. Occasional book reviews (Bürger, Matthisson,
Egmont) and the Universalgeschichte lecture are deliberately omitted.

Schiller died 1805; all works are public domain.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import _zeno
from _zeno import ZenoWork, add_crawl_args, main_for

SCHILLER_PREFIX = "/Literatur/M/Schiller,+Friedrich/Theoretische+Schriften"
MAX_PAGES = 400

# (output filename, work title exactly as it appears on the zeno path).
_TITLES: list[tuple[str, str]] = [
    (
        "aesthetische_erziehung_de.html",
        "Über die ästhetische Erziehung des Menschen in einer Reihe von Briefen",
    ),
    ("naive_sentimentalische_de.html", "Über naive und sentimentalische Dichtung"),
    ("anmut_wuerde_de.html", "Über Anmut und Würde"),
    ("kallias_de.html", "[Kallias oder über die Schönheit]"),
    ("ueber_erhabene_de.html", "Über das Erhabene"),
    ("vom_erhabenen_de.html", "Vom Erhabenen"),
    ("pathetische_de.html", "Über das Pathetische"),
    ("tragische_kunst_de.html", "Über die tragische Kunst"),
    ("tragische_gegenstaende_de.html", "Über den Grund des Vergnügens an tragischen Gegenständen"),
    ("philosophische_briefe_de.html", "Philosophische Briefe"),
]


def title_to_path(title: str) -> str:
    """Work title → zeno URL path under the theoretical-works root.

    Same encoding rule as `download_kant_de.title_to_path` (issue #420).
    Latent here: `kallias_de.html`'s bracketed title is the only affected
    entry, and that work fits on zeno's single root page.
    """
    return _zeno.title_to_path(SCHILLER_PREFIX, title)


WORKS: list[ZenoWork] = [ZenoWork(fn, title_to_path(t), label=t) for fn, t in _TITLES]


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch Schiller's theoretical writings from zeno.org.")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "schiller" / "raw_deu",
        help="Output directory (default: data/schiller/raw_deu/).",
    )
    add_crawl_args(ap)
    args = ap.parse_args()
    return main_for(WORKS, args.out, args, max_pages=MAX_PAGES)


if __name__ == "__main__":
    raise SystemExit(main())
