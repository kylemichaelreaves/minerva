#!/usr/bin/env python3
"""Download Cicero's 16 philosophical + rhetorical works from
la.wikisource.org.

Each work has a top-level Latin page (e.g.
``https://la.wikisource.org/wiki/De_officiis``) which links to
per-book sub-pages (Liber Primus / Liber Secundus / etc.). We
BFS-walk each work's URL tree under its top-level slug, fetch
every reachable sub-page's HTML, and concatenate the text into
a single .txt file per work — same pattern as
``download_marx_zeno.py`` but targeting la.wikisource.

Output: ``data/cicero/raw_la/<work_code>.txt`` × 16.

Run: uv run python perseus/download_cicero_wikisource.py
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from urllib.parse import quote

from _download import fetch_bytes_with_retry

USER_AGENT = "minerva-corpus-fetch/1.0 (+local research; respects la.wikisource.org)"

# (output filename, la.wikisource top-level page title)
_WORKS: tuple[tuple[str, str], ...] = (
    ("de_inventione_lat.txt", "De inventione"),
    ("de_oratore_lat.txt", "De oratore"),
    ("de_re_publica_lat.txt", "De re publica"),
    ("de_legibus_lat.txt", "De legibus"),
    ("brutus_lat.txt", "Brutus"),
    ("orator_lat.txt", "Orator"),
    # Academica intentionally omitted: la.wikisource has no full
    # transcription (it's fragmentary in the manuscript tradition).
    # English coverage still comes via PG 14970 + PG 29247.
    ("de_finibus_lat.txt", "De finibus bonorum et malorum"),
    ("de_natura_deorum_lat.txt", "De natura deorum"),
    ("tusculans_lat.txt", "Tusculanae disputationes"),
    ("de_officiis_lat.txt", "De officiis"),
    ("de_amicitia_lat.txt", "Laelius de Amicitia"),
    ("de_senectute_lat.txt", "Cato maior de senectute"),
    ("de_divinatione_lat.txt", "De divinatione"),
    ("de_fato_lat.txt", "De fato (Marcus Tullius Cicero)"),
    ("topica_lat.txt", "Topica (Marcus Tullius Cicero)"),
)


def _rest_url(title: str) -> str:
    return (
        "https://la.wikisource.org/api/rest_v1/page/html/"
        + quote(title, safe="")
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
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds to sleep between requests (be polite to la.wikisource).",
    )
    ap.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Subset filename allowlist (e.g. --only de_officiis_lat.txt).",
    )
    args = ap.parse_args()
    out_dir = args.data_root / "cicero" / "raw_la"
    only = set(args.only) if args.only else None
    for filename, title in _WORKS:
        if only and filename not in only:
            continue
        print(f"\n=== {filename}: {title} ===")
        try:
            fetch_work(title, dest=out_dir / filename, delay=args.delay)
        except urllib.error.HTTPError as e:
            print(f"  [WORK SKIPPED] {filename} ({title}): HTTP {e.code}")
        except Exception as e:
            print(f"  [WORK SKIPPED] {filename}: {type(e).__name__}: {e}")
        time.sleep(args.delay)


if __name__ == "__main__":
    main()
