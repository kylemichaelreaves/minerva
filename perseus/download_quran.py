#!/usr/bin/env python3
"""Download the Quran in Uthmani script from tanzil.net.

Source: tanzil.net — the canonical Arabic-script Quran distribution.
Format: single XML file with <sura index name>/<aya index text> nesting.
License: free for any use with attribution (Tanzil terms; the
``<aya>`` block preserves the copyright header).

Pulls 114 surahs / 6,236 ayahs as one XML file into
``data/quran/raw/quran-uthmani.xml``. The parser
(``src/minerva/quran.py``) consumes it in canonical Mushaf order.

Run: uv run python perseus/download_quran.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _download import make_fetcher

# Tanzil's parameterised download endpoint. ``quranType=uthmani`` →
# canonical script with full tashkeel; ``outType=xml`` → the
# <sura>/<aya> structure we parse; ``marks=true`` keeps the small
# pause / sajda / rub markers that some editions use as recitation
# guides (parser ignores them, but they're preserved in the file
# verbatim so a future pass can use them). ``agree=true`` is
# required to accept Tanzil's redistribution terms (encoded in the
# URL — we are accepting the standard CC-attribution licensing).
_URL = (
    "https://tanzil.net/pub/download/index.php?"
    "marks=true&sajdah=true&rub=true&img=true&"
    "quranType=uthmani&outType=xml&agree=true"
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
        "--force",
        action="store_true",
        help="Re-download even if the file already exists locally.",
    )
    args = ap.parse_args()

    out_dir = args.data_root / "quran" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "quran-uthmani.xml"

    if dest.exists() and not args.force:
        print(f"=== cached ({dest.stat().st_size:,} bytes) → {dest}")
        return

    print(f"=== GET {_URL}")
    data = _fetch(_URL)
    dest.write_bytes(data)
    print(f"  → {dest} ({len(data):,} bytes)")
    # Sanity-check counts so the next ingest sees what it expects.
    n_sura = data.count(b"<sura ")
    n_aya = data.count(b"<aya ")
    print(f"  surahs found:  {n_sura}  (canonical: 114)")
    print(f"  ayahs found:   {n_aya:,}  (canonical: 6,236)")
    if n_sura != 114 or n_aya != 6236:
        print("  WARNING: counts deviate from the canonical Mushaf — inspect before ingesting.")


if __name__ == "__main__":
    main()
