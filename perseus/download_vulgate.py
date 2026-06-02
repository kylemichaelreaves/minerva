#!/usr/bin/env python3
"""Download the Clementine Vulgate (Latin Bible) from BibleGet-I-O.

Source: ``github.com/BibleGet-I-O/Clementine-Vulgate`` — the canonical
GitHub mirror of the Clementine Vulgate Project (vulsearch). 73
per-book plain-text files under ``src/utf8/<Abbr>.lat``.

License: public domain (the Clementine Vulgate text itself; the
BibleGet-I-O repo wraps it).

Why this edition: the Clementine Vulgate (1592, with Jerome's
~400 AD original text as its base) is the text Aquinas and the
medieval scholastic tradition cite. Vulgate Psalm numbering
(Septuagint-derived), Susanna and Bel as Daniel 13–14, and the
Letter of Jeremiah as Baruch 6 are all preserved — matching the
conventions that scripture cross-references from the existing
Aquinas / Augustine corpora expect.

Output: ``data/vulgate/raw_lat/<Abbr>.lat``.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from _download import make_fetcher

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

RAW_BASE = (
    "https://raw.githubusercontent.com/BibleGet-I-O/Clementine-Vulgate/"
    "master/src/utf8"
)

# Filenames as they appear in BibleGet-I-O/Clementine-Vulgate's
# src/utf8/. 73 entries total — the Catholic canon plus the LXX
# deuterocanonicals Aquinas cites (Tobit, Judith, Wisdom, Sirach,
# Baruch, 1-2 Maccabees). Order = canonical Vulgate sequence.
_VULGATE_FILES: tuple[str, ...] = (
    # ----- Pentateuch -----
    "Gn.lat", "Ex.lat", "Lv.lat", "Nm.lat", "Dt.lat",
    # ----- Historical -----
    "Jos.lat", "Jdc.lat", "Rt.lat",
    "1Rg.lat", "2Rg.lat", "3Rg.lat", "4Rg.lat",
    "1Par.lat", "2Par.lat",
    "Esr.lat", "Neh.lat",
    "Tob.lat", "Jdt.lat", "Est.lat",
    "1Mcc.lat", "2Mcc.lat",
    # ----- Wisdom -----
    "Job.lat", "Ps.lat", "Pr.lat", "Ecl.lat", "Ct.lat",
    "Sap.lat", "Sir.lat",
    # ----- Major prophets -----
    "Is.lat", "Jr.lat", "Lam.lat", "Bar.lat", "Ez.lat", "Dn.lat",
    # ----- Minor prophets -----
    "Os.lat", "Joel.lat", "Am.lat", "Abd.lat", "Jon.lat", "Mch.lat",
    "Nah.lat", "Hab.lat", "Soph.lat", "Agg.lat", "Zach.lat", "Mal.lat",
    # ----- Gospels + Acts -----
    "Mt.lat", "Mc.lat", "Lc.lat", "Jo.lat", "Act.lat",
    # ----- Pauline epistles -----
    "Rom.lat", "1Cor.lat", "2Cor.lat", "Gal.lat", "Eph.lat",
    "Phlp.lat", "Col.lat", "1Thes.lat", "2Thes.lat",
    "1Tim.lat", "2Tim.lat", "Tit.lat", "Phlm.lat",
    # ----- Hebrews -----
    "Hbr.lat",
    # ----- Catholic epistles -----
    "Jac.lat", "1Ptr.lat", "2Ptr.lat", "1Jo.lat", "2Jo.lat", "3Jo.lat",
    "Jud.lat",
    # ----- Revelation -----
    "Apc.lat",
)


_fetch = make_fetcher()

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "data" / "vulgate" / "raw_lat",
        help="Output directory.",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=0.4,
        help="Seconds to sleep between HTTP requests (default: 0.4).",
    )
    ap.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip download if destination already exists and is non-empty.",
    )
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    failures: list[tuple[str, str]] = []
    print(f"=== Clementine Vulgate ({len(_VULGATE_FILES)} books) ===")
    for i, filename in enumerate(_VULGATE_FILES, 1):
        remote = f"{RAW_BASE}/{filename}"
        dest = out / filename
        print(f"[{i}/{len(_VULGATE_FILES)}] {filename}")
        if args.skip_existing and dest.is_file() and dest.stat().st_size > 0:
            print("  skip (already exists)")
            if i < len(_VULGATE_FILES):
                time.sleep(args.delay)
            continue
        try:
            data = _fetch(remote)
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code}: skipping ({remote})")
            failures.append((filename, str(e)))
            continue
        dest.write_bytes(data)
        if i < len(_VULGATE_FILES):
            time.sleep(args.delay)

    print(f"\nDone. Wrote files under {out.resolve()}")
    if failures:
        print(f"\n{len(failures)} failure(s):")
        for fn, err in failures:
            print(f"  - {fn}: {err}")


if __name__ == "__main__":
    main()
