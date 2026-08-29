#!/usr/bin/env python3
"""
Download additional Aristotle Greek originals from OpenGreekAndLatin's
``First1KGreek`` GitHub repo.

Source: https://github.com/OpenGreekAndLatin/First1KGreek
License: CC-BY-SA-4.0 (per the `<licence>` element in each TEI file).

Why a second downloader: Perseus's canonical TEI bundle for Aristotle
contains only 9 works (Constitution of Athenians, Metaphysics,
Nicomachean Ethics, Eudemian Ethics, Politics, Rhetoric, Poetics,
Economics, Virtues and Vices). First1KGreek expands this with the
Organon, Physics, On the Heavens, the biological works, On the Soul,
the Parva Naturalia, etc. — roughly twenty additional works in Greek.

These files are TEI P5 with EpiDoc (vs. Perseus's TEI.2 / non-
namespaced flavor), so a separate parser handles them — see
``src/minerva/tei_p5.py``.

Output layout
-------------
``perseus/raw_xml_aristotle_first1k/<canonical_title>/grc.xml``

One file per work, named consistently with the canonical title from
``aristotle_works.ARISTOTLE_WORKS``. The parser keys on the directory
name to look up the citation system and the work's canonical title in
the corpus.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
from pathlib import Path

from _download import FailureAccumulator, make_fetcher

# Make src/minerva importable when run from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from minerva.authors.aristotle_works import works_with_first1k  # noqa: E402

RAW_BASE = "https://raw.githubusercontent.com/OpenGreekAndLatin/First1KGreek/master"


_fetch = make_fetcher()

def _slug_for(title: str) -> str:
    """Filename-safe slug derived from the canonical title."""
    return "".join(c.lower() if c.isalnum() else "_" for c in title).strip("_")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "raw_xml_aristotle_first1k",
        help="Output directory.",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds to sleep between HTTP requests (default: 0.5).",
    )
    ap.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip download if destination already exists and is non-empty.",
    )
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    works = works_with_first1k()
    print(f"=== First1KGreek Aristotle ({len(works)} works) ===")
    failures = FailureAccumulator()
    for i, w in enumerate(works, 1):
        # First1KGreek file naming: tlg0086.<tlg>.1st1K-grc1.xml
        remote = f"{RAW_BASE}/data/tlg0086/{w.first1k_tlg}/tlg0086.{w.first1k_tlg}.1st1K-grc1.xml"
        slug = _slug_for(w.canonical_title)
        dest_dir = out / slug
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "grc.xml"
        print(f"[{i}/{len(works)}] {w.first1k_tlg} {w.canonical_title!r} -> {dest.relative_to(out)}")
        if args.skip_existing and dest.is_file() and dest.stat().st_size > 0:
            print("  skip (already exists)")
            if i < len(works):
                time.sleep(args.delay)
            continue
        try:
            data = _fetch(remote)
        except urllib.error.HTTPError as e:
            failures.record(
                w.first1k_tlg, f"HTTP {e.code} (likely a TLG slot we got wrong)"
            )
            continue
        dest.write_bytes(data)
        # Also fetch the __cts__.xml sidecar — it carries the canonical
        # title used in the catalog probe and is a useful breadcrumb.
        cts_url = f"{RAW_BASE}/data/tlg0086/{w.first1k_tlg}/__cts__.xml"
        try:
            cts = _fetch(cts_url)
            (dest_dir / "__cts__.xml").write_bytes(cts)
        except urllib.error.HTTPError:
            pass  # sidecar is optional
        if i < len(works):
            time.sleep(args.delay)

    print(f"\nDone. Wrote files under {out.resolve()}")
    return failures.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
