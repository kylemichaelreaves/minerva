#!/usr/bin/env python3
"""Download Hobbes's Latin works from Internet Archive OCR text.

Unlike Spinoza / Augustine / Aquinas — whose Latin works exist as
hand-transcribed clean text on la.wikisource.org — Hobbes's Latin
corpus is only available on Wikisource as PDF facsimiles. We fall
back to Internet Archive, which hosts the same scans with OCR
search-text layers (``_hocr_searchtext.txt.gz``). Quality is uneven
(long-s confusions, broken numerals, page-header pollution) and a
dedicated state-machine parser (``src/minerva/hobbes_la.py``)
handles the Molesworth-edition layout downstream.

Sources:

  * Latin Leviathan — Internet Archive ``leviathansivedem00hobb``,
    the 1668 Blaeu edition (single volume, four Pars: De Homine,
    De Civitate, De Civitate Christiana, De Regno Tenebrarum).
  * De Cive Latin — Internet Archive ``gri_elementaphilos00ho``,
    a 1704 reprint of the 1642 *Elementa philosophica de cive*.
    Three Pars: Libertas, Imperium, Religio.

Output:

    data/hobbes/raw_lat/leviathan_lat.txt
    data/hobbes/raw_lat/de_cive_lat.txt

Run:

    uv run python perseus/download_hobbes_la.py
"""

from __future__ import annotations

import argparse
import gzip
import time
from pathlib import Path

from _download import fetch_bytes_with_retry

# (work_label, ia_item_id, output_filename)
_DOWNLOADS: tuple[tuple[str, str, str], ...] = (
    ("Latin Leviathan (1668)", "leviathansivedem00hobb", "leviathan_lat.txt"),
    ("De Cive (1642 / 1704 reprint)", "gri_elementaphilos00ho", "de_cive_lat.txt"),
)


def _fetch_ia_ocr(ia_id: str) -> bytes:
    """Pull the gzipped OCR search-text from an Internet Archive item.
    Returns the raw decompressed bytes."""

    url = (
        f"https://archive.org/download/{ia_id}/"
        f"{ia_id}_hocr_searchtext.txt.gz"
    )
    gz = fetch_bytes_with_retry(
        url,
        timeout=60,
        user_agent="minerva-corpus-fetch/0.1 (research)",
    )
    return gzip.decompress(gz)


def _download_one(
    data_root: Path,
    label: str,
    ia_id: str,
    filename: str,
) -> Path:
    body = _fetch_ia_ocr(ia_id)
    dest_dir = data_root / "hobbes" / "raw_lat"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_bytes(body)
    print(f"  → {dest} ({len(body):,} bytes)")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/hobbes/raw_lat/.",
    )
    args = parser.parse_args()

    for label, ia_id, filename in _DOWNLOADS:
        print(f"\n{label}: {filename} (IA {ia_id})")
        _download_one(args.data_root, label, ia_id, filename)
        # Be polite to archive.org.
        time.sleep(1.0)

    print(
        "\nDone. Next: .venv/bin/minerva ingest && .venv/bin/minerva index"
    )


if __name__ == "__main__":
    main()
