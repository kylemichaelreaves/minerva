#!/usr/bin/env python3
"""Download the Greek New Testament (SBLGNT) from LogosBible's mirror.

Source: ``github.com/LogosBible/SBLGNT`` (path
``data/sblgnt/xml/<Book>.xml``). 27 per-book XML files in a custom
SBL format — not TEI, not OSIS. Tokenised at the word level via
``<w>``/``<suffix>`` pairs and milestone-based verse markers
(``<verse-number id="Matthew 1:1">``); the splitter at
``src/minerva/sblgnt.py`` walks that shape.

License: the SBLGNT text is licensed under the SBLGNT EULA from
``sblgnt.com`` (free for academic / non-commercial display).
LogosBible's repo wraps the upstream files with an MIT-style notice
for the packaging. See ``LICENSE`` in the cloned repo before
redistributing or deriving training data.

Why this, not First1KGreek: First1KGreek's ``tlg0031`` slot has only
ONE NT book (Mark) — coverage is unusable. SBLGNT is the modern
critical text (Mike Holmes ed.) used as the base for the NRSVue,
NIV, etc.

Output: ``data/nt/raw_grc/<Book>.xml``.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from _download import fetch_bytes_with_retry

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

RAW_BASE = (
    "https://raw.githubusercontent.com/LogosBible/SBLGNT/master/data/sblgnt/xml"
)
USER_AGENT = (
    "minerva-corpus-fetch/1.0 (+personal research; respects SBLGNT EULA; "
    "contact: local user)"
)

# Filenames as they appear in the SBLGNT repo. Order = canonical NT
# order (Matthew → Revelation). The .xml suffix is added by the
# downloader.
_NT_BOOK_FILES: tuple[str, ...] = (
    "Matt", "Mark", "Luke", "John", "Acts",
    "Rom", "1Cor", "2Cor", "Gal", "Eph",
    "Phil", "Col", "1Thess", "2Thess", "1Tim",
    "2Tim", "Titus", "Phlm", "Heb", "Jas",
    "1Pet", "2Pet", "1John", "2John", "3John",
    "Jude", "Rev",
)


_HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def _fetch(url: str, *, timeout: float = 60, retries: int = 8) -> bytes:
    return fetch_bytes_with_retry(
        url,
        timeout=timeout,
        retries=retries,
        user_agent=USER_AGENT,
        extra_headers=_HTML_HEADERS,
        backoff_initial=5.0,
        backoff_max=120.0,
    )

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "data" / "nt" / "raw_grc",
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
    print(f"=== SBLGNT NT ({len(_NT_BOOK_FILES)} books) ===")
    for i, stem in enumerate(_NT_BOOK_FILES, 1):
        filename = f"{stem}.xml"
        remote = f"{RAW_BASE}/{filename}"
        dest = out / filename
        print(f"[{i}/{len(_NT_BOOK_FILES)}] {stem} -> {dest.name}")
        if args.skip_existing and dest.is_file() and dest.stat().st_size > 0:
            print("  skip (already exists)")
            if i < len(_NT_BOOK_FILES):
                time.sleep(args.delay)
            continue
        try:
            data = _fetch(remote)
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code}: skipping ({remote})")
            failures.append((stem, str(e)))
            continue
        dest.write_bytes(data)
        if i < len(_NT_BOOK_FILES):
            time.sleep(args.delay)

    print(f"\nDone. Wrote files under {out.resolve()}")
    if failures:
        print(f"\n{len(failures)} failure(s):")
        for stem, err in failures:
            print(f"  - {stem}: {err}")


if __name__ == "__main__":
    main()
