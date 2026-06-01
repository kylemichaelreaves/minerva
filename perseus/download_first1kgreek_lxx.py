#!/usr/bin/env python3
"""Download the Septuagint from OpenGreekAndLatin's First1KGreek repo.

Source: ``github.com/OpenGreekAndLatin/First1KGreek``, group
``tlg0527`` (Swete's LXX, Cambridge 1887–1901, public domain).
License: CC-BY-SA-4.0 per the ``<licence>`` element in each TEI file.

Scope: 40+ books in the Catholic canon (see
``minerva.authors.septuagint_works._BOOKS``). LXX-only books outside that
scope (1 Esdras, 3–4 Macc, Odes, Pss. Sol.) are intentionally not
fetched here.

Output layout (flat directory; one XML file per book):

    perseus/raw_xml_lxx/tlg0527.tlgNNN.1st1K-grc1.xml

The on-disk filename is preserved verbatim from First1KGreek so the
``septuagint_works.find_work`` / ``tei_lxx.parse_dir`` dispatch chain
can recognise each file unambiguously.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from _download import fetch_bytes_with_retry

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from minerva.authors.septuagint_works import all_books  # noqa: E402

RAW_BASE = "https://raw.githubusercontent.com/OpenGreekAndLatin/First1KGreek/master"
USER_AGENT = (
    "minerva-corpus-fetch/1.0 (+personal research; respects First1KGreek terms; "
    "contact: local user)"
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
        default=Path(__file__).resolve().parent / "raw_xml_lxx",
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

    books = all_books()
    print(f"=== First1KGreek LXX ({len(books)} books) ===")
    failures: list[tuple[str, str]] = []
    for i, b in enumerate(books, 1):
        filename = f"tlg0527.{b.tlg}.1st1K-grc1.xml"
        remote = f"{RAW_BASE}/data/tlg0527/{b.tlg}/{filename}"
        dest = out / filename
        print(f"[{i}/{len(books)}] {b.tlg} {b.title!r} -> {dest.name}")
        if args.skip_existing and dest.is_file() and dest.stat().st_size > 0:
            print("  skip (already exists)")
            if i < len(books):
                time.sleep(args.delay)
            continue
        try:
            data = _fetch(remote)
        except urllib.error.HTTPError as e:
            # 404 means we got the TLG slot wrong (Swete numbering drift)
            # or the file isn't hosted; record and continue rather than
            # halt the whole batch.
            print(f"  HTTP {e.code}: skipping ({remote})")
            failures.append((b.title, str(e)))
            continue
        dest.write_bytes(data)
        if i < len(books):
            time.sleep(args.delay)

    print(f"\nDone. Wrote files under {out.resolve()}")
    if failures:
        print(f"\n{len(failures)} failure(s):")
        for title, err in failures:
            print(f"  - {title}: {err}")


if __name__ == "__main__":
    main()
