#!/usr/bin/env python3
"""Download the Luther Bibel 1545 Letzte-Hand as OSIS XML.

The 1545 Letzte-Hand edition is Luther's final revision of his 1534
Vollbibel — Frühneuhochdeutsch orthography preserved (Tewfel /
langes-ſ / -nis spellings).

Source: gratis-bible (``github.com/gratis-bible/bible``). OSIS 2.1.1
XML, single file per edition. Public domain.

Output: ``data/luther_1545/raw_deu/luther_1545.xml``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _download import fetch_bytes_with_retry

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

DEFAULT_URL = (
    "https://raw.githubusercontent.com/gratis-bible/bible/master/de/luth1545.xml"
)
USER_AGENT = (
    "minerva-corpus-fetch/1.0 (+personal research; Luther 1545 public "
    "domain; contact: local user)"
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
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "data" / "luther_1545" / "raw_deu",
    )
    ap.add_argument("--skip-existing", action="store_true")
    args = ap.parse_args()

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "luther_1545.xml"

    if args.skip_existing and dest.is_file() and dest.stat().st_size > 0:
        print(f"skip (already exists): {dest}")
        return

    print("=== Luther 1545 Letzte-Hand (OSIS XML) ===")
    print(f"GET {args.url}")
    try:
        xml_bytes = _fetch(args.url)
    except urllib.error.HTTPError as e:
        print(f"FAILED: HTTP {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)

    dest.write_bytes(xml_bytes)
    print(f"  wrote {dest.resolve()} ({len(xml_bytes):,} bytes)")


if __name__ == "__main__":
    main()
