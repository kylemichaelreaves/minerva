#!/usr/bin/env python3
"""Download Lucretius's De Rerum Natura from Perseus.

Two Perseus dltext IDs cover the work bilingually:
  * `Perseus:text:1999.02.0130` — Munro 1860 critical Latin edition
  * `Perseus:text:1999.02.0131` — H. A. J. Munro 1864 English translation

Output:
    data/lucretius/raw/dr_natura_lat.xml
    data/lucretius/raw/dr_natura_en.xml

Run: uv run python perseus/download_perseus_lucretius.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dl import download_one

BASE = "https://www.perseus.tufts.edu/hopper/dltext"

WORKS: list[tuple[str, str]] = [
    ("Perseus:text:1999.02.0130", "dr_natura_lat.xml"),
    ("Perseus:text:1999.02.0131", "dr_natura_en.xml"),
]

USER_AGENT = (
    "minerva-corpus-fetch/1.0 (+local research; respects Perseus terms)"
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "lucretius" / "raw",
        help="Output directory for XML files.",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to sleep between requests (Perseus rate-limits aggressively).",
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for doc, filename in WORKS:
        dest = args.out / filename
        print(f"GET {BASE}?doc={doc} → {dest}")
        download_one(
            base_url=BASE,
            doc=doc,
            dest=dest,
            user_agent=USER_AGENT,
        )
        print(f"  → {dest.stat().st_size:,} bytes")
        time.sleep(args.delay)


if __name__ == "__main__":
    main()
