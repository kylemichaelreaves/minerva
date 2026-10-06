#!/usr/bin/env python3
"""Download German Kant originals from zeno.org.

Like `download_hegel_de.py`, runs the shared `_zeno.py` crawler: BFS-walks each work's URL tree, fetches
every reachable subpage's HTML, and concatenates them into one HTML file
per work in `data/kant/`. The 14 `*_de` entries in `kant_works.py` already
point at the output filenames produced here.

Kant died 1804; all works are public domain.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import _zeno
from _zeno import ZenoWork, add_crawl_args, main_for

KANT_PREFIX = "/Philosophie/M/Kant,+Immanuel"
MAX_PAGES = 600

# (output filename, German work title as it appears on zeno).
# The titles are converted to URL-form below — spaces → `+`, then
# percent-encoded for umlauts and other non-ASCII (`title_to_path`).
_TITLES: list[tuple[str, str]] = [
    ("krv_de.html", "Kritik der reinen Vernunft"),
    ("kpv_de.html", "Kritik der praktischen Vernunft"),
    ("ku_de.html", "Kritik der Urteilskraft"),
    ("ku_einl_de.html", "Einleitung in die Kritik der Urteilskraft [1. Fassung]"),
    ("gms_de.html", "Grundlegung zur Metaphysik der Sitten"),
    ("ms_de.html", "Die Metaphysik der Sitten"),
    ("prol_de.html", "Prolegomena zu einer jeden künftigen Metaphysik"),
    ("rel_de.html", "Die Religion innerhalb der Grenzen der bloßen Vernunft"),
    ("anf_naturwiss_de.html", "Metaphysische Anfangsgründe der Naturwissenschaft"),
    ("aufklaerung_de.html", "Beantwortung der Frage: Was ist Aufklärung"),
    ("orientieren_de.html", "Was heißt: sich im Denken orientieren"),
    ("frieden_de.html", "Zum ewigen Frieden. Ein philosophischer Entwurf"),
    (
        "gemeinspruch_de.html",
        "Über den Gemeinspruch: Das mag in der Theorie richtig sein, taugt aber nicht für die Praxis",
    ),
    ("luegen_de.html", "Über ein vermeintes Recht aus Menschenliebe zu lügen"),
]


def title_to_path(title: str) -> str:
    """German title → zeno URL path under the Kant root.

    See `_zeno.title_to_path` for why ``:``/``[``/``]`` are encoded
    (issue #420).
    """
    return _zeno.title_to_path(KANT_PREFIX, title)


WORKS: list[ZenoWork] = [ZenoWork(fn, title_to_path(t), label=t) for fn, t in _TITLES]


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch Kant German originals from zeno.org.")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "kant",
        help="Output directory for combined HTML files (default: data/kant/).",
    )
    add_crawl_args(ap)
    args = ap.parse_args()
    return main_for(WORKS, args.out, args, max_pages=MAX_PAGES)


if __name__ == "__main__":
    raise SystemExit(main())
