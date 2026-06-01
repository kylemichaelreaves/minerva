#!/usr/bin/env python3
"""
Download Plato TEI/XML from the Perseus Digital Library using official dltext URLs.

Source: https://www.perseus.tufts.edu/hopper/

Per-segment licensing varies; many contributed texts use Creative Commons. Before
redistributing or publishing a derived corpus, open each XML file and read the
<publicationStmt> / license metadata inside the TEI header, and comply with it.

English Plato volumes on Perseus are grouped like the linked Loeb editions;
each XML bundle contains multiple dialogues.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dl import doc_id, download_one

BASE = "https://www.perseus.tufts.edu/hopper/dltext"

# (suffix after "1999.01.", output stem)
ENGLISH_VOLUMES: list[tuple[str, str]] = [
    ("0170", "01_euthyphro_apology_crito_phaedo_en"),
    ("0172", "02_cratylus_theaetetus_sophist_statesman_en"),
    ("0174", "03_parmenides_philebus_symposium_phaedrus_en"),
    ("0176", "04_alcibiades_hipparchus_charmides_laches_lysis_en"),
    ("0178", "05_euthydemus_protagoras_gorgias_meno_en"),
    ("0180", "06_hippias_ion_menexenus_timaeus_critias_en"),
    ("0164", "07_letters_en"),
    ("0166", "08_laws_en"),
    ("0168", "09_republic_en"),
]

GREEK_VOLUMES: list[tuple[str, str]] = [
    ("0169", "01_euthyphro_apology_crito_phaedo_gr"),
    ("0171", "02_cratylus_theaetetus_sophist_statesman_gr"),
    ("0173", "03_parmenides_philebus_symposium_phaedrus_gr"),
    ("0175", "04_alcibiades_hipparchus_charmides_laches_lysis_gr"),
    ("0177", "05_euthydemus_protagoras_gorgias_meno_gr"),
    ("0179", "06_hippias_ion_menexenus_timaeus_critias_gr"),
    ("0163", "07_epistles_gr"),
    ("0165", "08_laws_gr"),
    ("0167", "09_republic_gr"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch Plato TEI XML from Perseus dltext.")
    ap.add_argument(
        "--lang",
        choices=("en", "gr", "both"),
        default="en",
        help="Which language bundles to download (default: en).",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "raw_xml",
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
            "platonic-corpus-fetch/1.0 (+personal research; respects Perseus terms; "
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
        batches.append(("English", ENGLISH_VOLUMES))
    if args.lang in ("gr", "both"):
        batches.append(("Greek", GREEK_VOLUMES))

    total = sum(len(vols) for _, vols in batches)
    n = 0
    for label, vols in batches:
        print(f"=== {label} ({len(vols)} volumes) ===")
        for suffix, stem in vols:
            n += 1
            doc = doc_id(suffix)
            path = out / f"perseus_{stem}.xml"
            print(f"[{n}/{total}] {doc} -> {path.name}")
            if args.skip_existing and path.is_file() and path.stat().st_size > 0:
                print("  skip (already exists)")
                if n < total:
                    time.sleep(args.delay)
                continue
            try:
                download_one(base_url=BASE, doc=doc, dest=path, user_agent=args.user_agent)
            except urllib.error.HTTPError as e:
                print(f"  HTTP error {e.code}: {e.reason}")
                raise
            except urllib.error.URLError as e:
                print(f"  URL error: {e.reason}")
                raise
            if n < total:
                time.sleep(args.delay)
        print()

    print(f"Done. Wrote {total} file(s) under {out.resolve()}")


if __name__ == "__main__":
    main()
