#!/usr/bin/env python3
"""Download German Hegel originals from zeno.org.

Hegel died in 1831; all major works are public domain everywhere. zeno.org
hosts complete texts of all four big works under stable URL paths:

    /Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/<Work>/<Chapter>/<Subchapter>

This script BFS-walks each work's URL tree (via the shared `_zeno.py`
crawler), fetches every reachable subpage's HTML, and concatenates them
into one HTML file per work in `data/hegel/`. The existing `hegel.py` parser handles HTML extraction
and chapter splitting from there.

Run via:
    python3 perseus/download_hegel_de.py

The four `*_de` entries in `hegel_works.py` already point at the output
filenames produced here.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _zeno import ZenoWork, add_crawl_args, main_for

MAX_PAGES = 600

# (output filename, root URL path on zeno.org)
WORKS: list[ZenoWork] = [
    ZenoWork(
        "phg_de.html",
        "/Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/Ph%C3%A4nomenologie+des+Geistes",
    ),
    ZenoWork(
        "pr_de.html",
        "/Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/Grundlinien+der+Philosophie+des+Rechts",
    ),
    ZenoWork(
        "enz_de.html",
        "/Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/Enzyklop%C3%A4die+der+philosophischen+Wissenschaften+im+Grundrisse",
    ),
    ZenoWork(
        "sol_de.html",
        "/Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/Wissenschaft+der+Logik",
    ),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch Hegel German originals from zeno.org.")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "hegel",
        help="Output directory for combined HTML files (default: data/hegel/).",
    )
    add_crawl_args(ap)
    args = ap.parse_args()
    return main_for(WORKS, args.out, args, max_pages=MAX_PAGES)


if __name__ == "__main__":
    raise SystemExit(main())
