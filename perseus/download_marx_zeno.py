#!/usr/bin/env python3
"""Download two Grundrisse-derived Marx works from zeno.org.

The Grundrisse (1857-58 notebooks) was first published in 1939; the
standard Dietz Verlag edition (MEW Bd 42, 1983) is still in copyright,
so PG-DE / Wikisource / archive.org all decline to host the full
text and the mlwerke.de pages are dead. But zeno.org carries the
two most-cited stand-alone selections from Grundrisse:

  * Einleitung [zur Kritik der politischen Ökonomie] (Aug 1857) —
    Marx's General Introduction, often regarded as the most
    important methodological text in his corpus. Multi-section
    on zeno (I.1, I.2, I.3, I.4 + Lesarten).

  * Formen, die der kapitalistischen Produktion vorhergehen
    (1857-58) — "Forms which precede capitalist production." Single-
    page on zeno. Published by Hobsbawm as a standalone in English
    as *Pre-Capitalist Economic Formations*.

zeno serves both as HTML with sub-page navigation. We BFS-walk each
work's URL tree and concatenate the HTML pages with `<!-- ZENO_PAGE: -->`
markers — the same convention `download_hegel_de.py` uses and that
the downstream `split_zeno_pages` recognizes for chapter boundaries.

Output:
    data/marx/raw_deu/einleitung_grundrisse.html
    data/marx/raw_deu/formen_vorkapitalistisch.html

Run:
    uv run python perseus/download_marx_zeno.py
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.parse
from pathlib import Path

from _download import fetch_with_retry

ROOT = "http://www.zeno.org"

# (output filename, zeno root URL path)
WORKS: list[tuple[str, str]] = [
    (
        "einleitung_grundrisse.html",
        "/Philosophie/M/Marx,+Karl/Einleitung+%5Bzur+Kritik+der+politischen+%C3%96konomie%5D",
    ),
    (
        "formen_vorkapitalistisch.html",
        "/Philosophie/M/Marx,+Karl/Formen,+die+der+kapitalistischen+Produktion+vorhergehen",
    ),
]

_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)


def fetch(url: str, *, timeout: float = 30, retries: int = 8) -> str:
    """zeno.org-specific fetch wrapper — ISO-8859-1 decoded, retries
    on transient HTTP / URL errors. Delegates to the shared
    ``_download.fetch_with_retry`` helper (Phase 5)."""

    return fetch_with_retry(
        url,
        timeout=timeout,
        retries=retries,
        encoding="iso-8859-1",
    )


def extract_links(html: str, root_path: str) -> list[str]:
    """Return paths under `root_path` linked from the given HTML.
    Footnote-anchor links (`#fnA1`, `#fnA1ref`) are stripped by the
    fragment-removal step; only true sub-pages survive."""

    out: list[str] = []
    seen: set[str] = set()
    for raw in _HREF_RE.findall(html):
        if raw.startswith(ROOT):
            raw = raw[len(ROOT):]
        if not raw.startswith("/"):
            continue
        path = raw.split("#", 1)[0].split("?", 1)[0]
        if not path.startswith(root_path):
            continue
        if path == root_path:
            continue
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def crawl_work(
    root_path: str, *, delay: float = 1.5, max_pages: int = 100
) -> list[tuple[str, str]]:
    """BFS-walk one work's subtree on zeno. Cap at max_pages."""

    queue: list[str] = [root_path]
    seen: set[str] = {root_path}
    pages: list[tuple[str, str]] = []
    while queue and len(pages) < max_pages:
        path = queue.pop(0)
        url = ROOT + path
        try:
            html = fetch(url)
        except Exception as e:
            print(f"  [skip] {path}: {e}")
            continue
        pages.append((path, html))
        decoded = urllib.parse.unquote(path)
        print(f"  [{len(pages):>3}] {decoded[-80:]:<80}  {len(html):>7,} bytes")
        for child in extract_links(html, root_path):
            if child in seen:
                continue
            seen.add(child)
            queue.append(child)
        time.sleep(delay)
    if len(pages) >= max_pages:
        print(f"  (hit max_pages={max_pages}; stopping)")
    return pages


def download_work(
    filename: str, root_path: str, out_dir: Path, *, delay: float
) -> Path | None:
    print(f"\n=== {filename}: {urllib.parse.unquote(root_path)} ===")
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = crawl_work(root_path, delay=delay)
    if not pages:
        print("  no content fetched")
        return None
    parts = [
        f"<!-- ZENO_PAGE: {urllib.parse.unquote(p)} -->\n{html}"
        for p, html in pages
    ]
    out_path = out_dir / filename
    out_path.write_text("\n\n".join(parts), encoding="utf-8")
    print(f"  → {out_path} ({len(pages)} pages, {out_path.stat().st_size:,} bytes)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/marx/raw_deu/.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds to wait between requests (be polite to zeno.org).",
    )
    args = parser.parse_args()
    out_dir = args.data_root / "marx" / "raw_deu"
    for filename, root_path in WORKS:
        download_work(filename, root_path, out_dir, delay=args.delay)


if __name__ == "__main__":
    main()
