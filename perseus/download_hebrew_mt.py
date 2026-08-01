#!/usr/bin/env python3
"""Download the Westminster Leningrad Codex (WLC) as OSIS XML.

Source: Open Scriptures Hebrew Bible (OSHB) — github.com/openscriptures/morphhb
License: CC-BY 4.0
Format: OSIS XML, one file per book (39 books + VerseMap.xml metadata).

Files land under ``data/hebrew_mt/raw/`` as ``Gen.xml``, ``Exod.xml``, …
The parser (``src/minerva/hebrew_mt.py``) consumes them in any order;
filename → canonical English book name lives in ``hebrew_mt_works.py``.

Run: uv run python perseus/download_hebrew_mt.py
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from _download import make_fetcher

# Raw file URL pattern. master branch is stable across the OSHB
# release cadence; pin to a specific commit if reproducibility ever
# matters for the index (see the rights frontmatter inside each file
# for the release date the maintainers stamp on this commit).
_BASE = "https://raw.githubusercontent.com/openscriptures/morphhb/master/wlc"

# 39 protestant-canon books. Filenames are SBL-style abbreviations
# (Gen, 1Sam, Ps, …). VerseMap.xml is metadata, not a book — we
# exclude it. Order here is the GitHub repo's alphabetical listing;
# the ingest doesn't care about order, and the sidebar uses
# ``TANAKH_BOOK_ORDINAL`` for display ordering.
_FILES: tuple[str, ...] = (
    "Gen.xml", "Exod.xml", "Lev.xml", "Num.xml", "Deut.xml",
    "Josh.xml", "Judg.xml", "Ruth.xml",
    "1Sam.xml", "2Sam.xml", "1Kgs.xml", "2Kgs.xml",
    "1Chr.xml", "2Chr.xml",
    "Ezra.xml", "Neh.xml", "Esth.xml",
    "Job.xml", "Ps.xml", "Prov.xml", "Eccl.xml", "Song.xml",
    "Isa.xml", "Jer.xml", "Lam.xml", "Ezek.xml", "Dan.xml",
    "Hos.xml", "Joel.xml", "Amos.xml", "Obad.xml", "Jonah.xml",
    "Mic.xml", "Nah.xml", "Hab.xml", "Zeph.xml", "Hag.xml",
    "Zech.xml", "Mal.xml",
)


_fetch = make_fetcher()

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
        default=0.4,
        help="Seconds to sleep between requests (be polite to githubusercontent).",
    )
    ap.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Subset filename allowlist (e.g. --only Gen.xml Exod.xml).",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the file already exists locally.",
    )
    args = ap.parse_args()

    out_dir = args.data_root / "hebrew_mt" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    only = set(args.only) if args.only else None

    total = 0
    for filename in _FILES:
        if only and filename not in only:
            continue
        dest = out_dir / filename
        if dest.exists() and not args.force:
            print(f"=== {filename}: cached ({dest.stat().st_size:,} bytes)")
            total += 1
            continue
        url = f"{_BASE}/{filename}"
        print(f"=== {filename}")
        print(f"  GET {url}")
        try:
            data = _fetch(url)
        except Exception as exc:
            print(f"  [SKIP] {filename}: {type(exc).__name__}: {exc}")
            continue
        dest.write_bytes(data)
        print(f"  → {dest} ({len(data):,} bytes)")
        total += 1
        time.sleep(args.delay)

    print(f"\nDone: {total}/{len(_FILES)} files in {out_dir}")


if __name__ == "__main__":
    main()
