#!/usr/bin/env python3
"""
Download Homer's Iliad + Odyssey TEI/XML from the Perseus Digital Library.

Source: https://www.perseus.tufts.edu/hopper/ (Perseus:text:1999.01.NNNN)

Coverage:
  * Iliad   — Greek (Allen ed., Oxford 1920) + English (Murray, Loeb 1924)
  * Odyssey — Greek (Allen ed., Oxford 1919) + English (Murray, Loeb 1919)

Structure on the wire: each work is a single TEI.2 file with 24 books
(`<div1 type="Book" n="N">`) split into Perseus "cards"
(`<milestone unit="card" n="<starting-line>" />`). The minerva TEI
parser (src/minerva/tei.py) treats each card as a chunk boundary and
emits `section="<book>.<starting-line>"` locators, so a Homer
citation reads like Il. 1.33 or Od. 12.108 — the standard scholarly
form.

Per-work licensing may differ; read the TEI <publicationStmt> before
redistributing.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dl import doc_id, download_one
from _download import FailureAccumulator

BASE = "https://www.perseus.tufts.edu/hopper/dltext"

# Perseus's id scheme pairs the same work in two adjacent numeric
# slots — odd = Greek source, even = English translation. Confirmed
# by probing the TEI <titleStmt> on each: 0133/0135 = Greek, 0134/0136
# = English.
GREEK_WORKS: list[tuple[str, str]] = [
    ("0133", "01_iliad_gr"),
    ("0135", "02_odyssey_gr"),
]

ENGLISH_WORKS: list[tuple[str, str]] = [
    ("0134", "01_iliad_en"),
    ("0136", "02_odyssey_en"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch Homer TEI XML from Perseus dltext.")
    ap.add_argument(
        "--lang",
        choices=("en", "gr", "both"),
        default="both",
        help="Which texts to download (default: both).",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "raw_xml_homer",
        help="Output directory for XML files.",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds to sleep between HTTP requests (default: 1.5).",
    )
    ap.add_argument(
        "--user-agent",
        default=(
            "perseus-corpus-fetch/1.0 (+personal research; respects Perseus terms; "
            "contact: local user)"
        ),
        help="User-Agent header sent with each request.",
    )
    ap.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip download if destination file already exists and is non-empty.",
    )
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    batches: list[tuple[str, list[tuple[str, str]]]] = []
    if args.lang in ("en", "both"):
        batches.append(("English", ENGLISH_WORKS))
    if args.lang in ("gr", "both"):
        batches.append(("Greek", GREEK_WORKS))

    total = sum(len(vols) for _, vols in batches)
    n = 0
    failures = FailureAccumulator()
    for label, vols in batches:
        print(f"=== {label} ({len(vols)} works) ===")
        for suffix, stem in vols:
            n += 1
            doc = doc_id(suffix)
            path = out / f"perseus_homer_{stem}.xml"
            print(f"[{n}/{total}] {doc} -> {path.name}")
            if args.skip_existing and path.is_file() and path.stat().st_size > 0:
                print("  skip (already exists)")
                if n < total:
                    time.sleep(args.delay)
                continue
            try:
                download_one(base_url=BASE, doc=doc, dest=path, user_agent=args.user_agent)
            except urllib.error.HTTPError as e:
                failures.record(path.name, f"HTTP {e.code}: {e.reason}")
                continue
            except urllib.error.URLError as e:
                failures.record(path.name, f"URL error: {e.reason}")
                continue
            if n < total:
                time.sleep(args.delay)
        print()

    print(f"Done. Wrote {total} file(s) under {out.resolve()}")
    return failures.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
