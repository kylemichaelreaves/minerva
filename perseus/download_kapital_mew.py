#!/usr/bin/env python3
"""Download Das Kapital I–III (MEW 23–25) from the Wayback Machine's
snapshot of mlwerke.de.

The corpus's previous Kapital source was a Google-Books OCR of the
1867 first edition — 55 mega-chunks of 85–582 KB with heavy scan
noise, and the 1867 six-chapter structure nobody cites. mlwerke.de
carried the canonical MEW text (Dietz, Berlin/DDR) with structure
worth everything: ``<A NAME="S49">`` anchors are the MEW page
numbers scholarship cites ("MEW 23, S. 49"), ``Kap_N_M`` anchors mark
sections, and Marx's own footnotes are marked up as ``Z``/``M``
anchor pairs. mlwerke.de itself went dark in 2025 (t-online parking
page), so we fetch the December 2024 Wayback snapshot using ``id_``
URLs — the raw original bytes, no Wayback chrome injected.

Output: ``data/marx/raw_mew/me{23,24,25}_NNN.htm`` (one file per
chapter page, ISO-8859-1 upstream, saved as UTF-8) — parsed by
``corpus/split_kapital_mew.py``.

Run: uv run python perseus/download_kapital_mew.py
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.error
from pathlib import Path

from _download import make_fetcher

VOLUMES = (23, 24, 25)

_fetch = make_fetcher(timeout=90)

# The site died in 2025 and its final captures are a t-online parking
# page ("Hier entsteht eine neue Homepage"), which Wayback happily
# serves for "closest to 2024" requests on sparsely-captured pages.
# So every page is pinned to its OWN last real capture before 2025,
# resolved through the CDX API, and the parking page is rejected by
# content just in case.
_PARKING_MARKER = "Hier entsteht eine neue Homepage"


def _last_good_timestamp(vol: int, page: str) -> str | None:
    """Latest statuscode-200 capture of the page before 2025, via CDX."""

    import json

    cdx = (
        "https://web.archive.org/cdx/search/cdx"
        f"?url=mlwerke.de/me/me{vol}/{page}"
        "&output=json&filter=statuscode:200&to=20241231"
    )
    rows = json.loads(_fetch(cdx).decode("utf-8", errors="replace"))
    if len(rows) < 2:  # header row only → never captured pre-2025
        return None
    return rows[-1][1]


def _fetch_page(vol: int, page: str) -> str:
    ts = _last_good_timestamp(vol, page)
    if ts is None:
        raise RuntimeError(f"{page}: no pre-2025 Wayback capture")
    url = f"https://web.archive.org/web/{ts}id_/http://www.mlwerke.de/me/me{vol}/{page}"
    html = _fetch(url).decode("iso-8859-1", errors="replace")
    if _PARKING_MARKER in html or len(html) < 3_000:
        raise RuntimeError(
            f"{page}@{ts}: got the parking page / a dwarf response "
            f"({len(html)} bytes) — capture unusable"
        )
    return html


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds between requests (Wayback rate-limits aggressively).",
    )
    args = ap.parse_args()
    out_dir = args.data_root / "marx" / "raw_mew"
    out_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    for vol in VOLUMES:
        print(f"=== MEW {vol}: TOC")
        toc = _fetch_page(vol, f"me{vol}_000.htm")
        # Save the TOC too — it documents the chapter set.
        (out_dir / f"me{vol}_000.htm").write_text(toc, encoding="utf-8")
        pages = sorted(set(re.findall(rf'href="(me{vol}_\d+\.htm)"', toc, re.I)))
        print(f"    {len(pages)} chapter pages")
        for page in pages:
            dest = out_dir / page
            if dest.exists() and dest.stat().st_size > 5_000:
                print(f"    {page}: cached, skipping")
                continue
            try:
                html = _fetch_page(vol, page)
            except (urllib.error.HTTPError, RuntimeError) as e:
                print(f"    [FAILED] {page}: {e}")
                failures.append(page)
                continue
            dest.write_text(html, encoding="utf-8")
            print(f"    {page}: {len(html):,} chars")
            time.sleep(args.delay)
        time.sleep(args.delay)
    if failures:
        raise SystemExit(f"{len(failures)} pages failed: {failures}")


if __name__ == "__main__":
    main()
