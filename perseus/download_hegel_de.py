#!/usr/bin/env python3
"""Download German Hegel originals from zeno.org.

Hegel died in 1831; all major works are public domain everywhere. zeno.org
hosts complete texts of all four big works under stable URL paths:

    /Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/<Work>/<Chapter>/<Subchapter>

This script BFS-walks each work's URL tree, fetches every reachable
subpage's HTML, and concatenates them into one HTML file per work in
`data/hegel/`. The existing `hegel.py` parser handles HTML extraction
and chapter splitting from there.

Run via:
    python3 perseus/download_hegel_de.py

The four `*_de` entries in `hegel_works.py` already point at the output
filenames produced here.
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.parse
from pathlib import Path

from _download import RateLimiter, fetch_parallel, fetch_with_retry

ROOT = "http://www.zeno.org"

# (output filename, root URL path on zeno.org)
WORKS: list[tuple[str, str]] = [
    (
        "phg_de.html",
        "/Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/Ph%C3%A4nomenologie+des+Geistes",
    ),
    (
        "pr_de.html",
        "/Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/Grundlinien+der+Philosophie+des+Rechts",
    ),
    (
        "enz_de.html",
        "/Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/Enzyklop%C3%A4die+der+philosophischen+Wissenschaften+im+Grundrisse",
    ),
    (
        "sol_de.html",
        "/Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/Wissenschaft+der+Logik",
    ),
]

_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)


def fetch(url: str, *, timeout: float = 30, retries: int = 8) -> str:
    """zeno.org-specific fetch wrapper — ISO-8859-1 decoded, retries
    on transient HTTP / URL errors. Delegates to the shared
    ``_download.fetch_with_retry`` helper introduced in Phase 5 of
    the 2026-05-30 remediation II plan."""

    return fetch_with_retry(
        url,
        timeout=timeout,
        retries=retries,
        encoding="iso-8859-1",
    )


def extract_links(html: str, root_path: str) -> list[str]:
    """Return paths under `root_path` linked from the given HTML."""

    out: list[str] = []
    seen: set[str] = set()
    for raw in _HREF_RE.findall(html):
        if raw.startswith(ROOT):
            raw = raw[len(ROOT):]
        if not raw.startswith("/"):
            continue
        path = raw.split("#", 1)[0].split("?", 1)[0]
        # Stay within the work's URL prefix; this enforces the BFS staying
        # inside one work and not wandering off to other Hegel works or
        # zeno's site chrome.
        if not path.startswith(root_path):
            continue
        # Skip the root page itself; we handle it separately.
        if path == root_path:
            continue
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def crawl_work(
    root_path: str,
    *,
    delay: float = 1.5,
    max_pages: int = 600,
    jobs: int = 1,
) -> list[tuple[str, str]]:
    """BFS-walk the work's subtree on zeno. Returns ``[(path, html),
    ...]`` in visit order.

    ``jobs=1`` keeps the prior single-request behavior (one fetch,
    then sleep ``delay``). ``jobs>1`` fetches each BFS level in
    parallel via ``fetch_parallel`` + ``RateLimiter(delay)`` — the
    limiter enforces the per-host minimum interval so 4 workers
    don't actually issue 4× the request rate at zeno.
    """

    queue: list[str] = [root_path]
    seen: set[str] = {root_path}
    pages: list[tuple[str, str]] = []
    limiter = RateLimiter(min_interval=delay) if jobs > 1 else None
    while queue and len(pages) < max_pages:
        # Take a slice of the queue sized to the parallelism so the
        # limiter has work to dole out. With jobs=1 this is the
        # original "one path at a time" behavior.
        batch_size = max(jobs, 1)
        batch = queue[:batch_size]
        queue = queue[len(batch):]

        if jobs > 1:
            urls = [ROOT + p for p in batch]
            results = fetch_parallel(
                urls, jobs=jobs, limiter=limiter, encoding="iso-8859-1"
            )
        else:
            results = []
            for p in batch:
                try:
                    html = fetch(ROOT + p)
                    results.append((ROOT + p, html))
                except Exception as e:
                    results.append((ROOT + p, e))

        for (url, res), path in zip(results, batch, strict=True):
            del url
            if isinstance(res, Exception):
                print(f"  [skip] {path}: {res}")
                continue
            html = res
            pages.append((path, html))
            decoded = urllib.parse.unquote(path)
            print(
                f"  [{len(pages):>3}] {decoded[-80:]:<80}  "
                f"{len(html):>7,} bytes"
            )
            for child in extract_links(html, root_path):
                if child in seen:
                    continue
                seen.add(child)
                queue.append(child)
            if jobs == 1:
                # Single-threaded path uses the inter-request sleep
                # the way the original did; parallel runs use the
                # RateLimiter instead.
                time.sleep(delay)
        if len(pages) >= max_pages:
            break
    if len(pages) >= max_pages:
        print(f"  (hit max_pages={max_pages}; stopping)")
    return pages


def download_work(
    filename: str,
    root_path: str,
    out_dir: Path,
    *,
    delay: float,
    jobs: int = 1,
) -> Path | None:
    print(f"\n=== {filename}: {urllib.parse.unquote(root_path)} ===")
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = crawl_work(root_path, delay=delay, jobs=jobs)
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
    ap = argparse.ArgumentParser(description="Fetch Hegel German originals from zeno.org.")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "hegel",
        help="Output directory for combined HTML files (default: data/hegel/).",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds between requests (default: 1.5; please be polite).",
    )
    ap.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Restrict to these output filenames (e.g. --only phg_de.html).",
    )
    ap.add_argument(
        "--jobs",
        type=int,
        default=1,
        help=(
            "Parallel BFS workers (default: 1 — sequential). When >1, "
            "each level's paths are fetched concurrently via a thread "
            "pool with per-host RateLimiter(delay) so the request rate "
            "stays polite. Cap at 2-3 to stay within zeno.org's good "
            "graces."
        ),
    )
    args = ap.parse_args()

    works = [(f, r) for f, r in WORKS if not args.only or f in args.only]
    written: list[Path] = []
    for fn, root in works:
        out = download_work(
            fn, root, args.out, delay=args.delay, jobs=args.jobs
        )
        if out is not None:
            written.append(out)

    print(f"\nDone. Wrote {len(written)} file(s):")
    for p in written:
        print(f"  {p}")


if __name__ == "__main__":
    main()
