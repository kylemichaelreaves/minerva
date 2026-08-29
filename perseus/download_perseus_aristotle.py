#!/usr/bin/env python3
"""
Download Aristotle TEI/XML from the Perseus Digital Library using official dltext URLs.

Source: https://www.perseus.tufts.edu/hopper/

Coverage note — Perseus currently exposes these nine works as separate Greek/English
pairs (not the entire Bekker corpus: e.g. Categories / Analytics are not listed here).
See hopper search "Aristotle" for what Perseus adds over time.

Per-work licensing may differ; read the TEI <publicationStmt> before redistributing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dl import download_one, run_dltext_batches

BASE = "https://www.perseus.tufts.edu/hopper/dltext"

# One XML file per work. Greek suffix is always odd starting at 0045; English next id.
ENGLISH_WORKS: list[tuple[str, str]] = [
    ("0046", "01_athenian_constitution_en"),
    ("0048", "02_economics_en"),
    ("0050", "03_eudemian_ethics_en"),
    ("0052", "04_metaphysics_en"),
    ("0054", "05_nicomachean_ethics_en"),
    ("0056", "06_poetics_en"),
    ("0058", "07_politics_en"),
    ("0060", "08_rhetoric_en"),
    ("0062", "09_virtues_and_vices_en"),
]

GREEK_WORKS: list[tuple[str, str]] = [
    ("0045", "01_athenian_constitution_gr"),
    ("0047", "02_economics_gr"),
    ("0049", "03_eudemian_ethics_gr"),
    ("0051", "04_metaphysics_gr"),
    ("0053", "05_nicomachean_ethics_gr"),
    ("0055", "06_poetics_gr"),
    ("0057", "07_politics_gr"),
    ("0059", "08_rhetoric_gr"),
    ("0061", "09_virtues_and_vices_gr"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch Aristotle TEI XML from Perseus dltext.")
    ap.add_argument(
        "--lang",
        choices=("en", "gr", "both"),
        default="en",
        help="Which texts to download (default: en).",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "raw_xml_aristotle",
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

    return run_dltext_batches(
        base_url=BASE,
        batches=batches,
        out=out,
        filename=lambda stem: f"perseus_aristotle_{stem}.xml",
        delay=args.delay,
        user_agent=args.user_agent,
        skip_existing=args.skip_existing,
        download_one_fn=download_one,
    )


if __name__ == "__main__":
    raise SystemExit(main())
