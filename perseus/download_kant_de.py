#!/usr/bin/env python3
"""Download German Kant originals from zeno.org.

Mirrors `download_hegel_de.py`: BFS-walks each work's URL tree, fetches
every reachable subpage's HTML, and concatenates them into one HTML file
per work in `data/kant/`. The 14 `*_de` entries in `kant_works.py` already
point at the output filenames produced here.

Kant died 1804; all works are public domain.
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.parse
from pathlib import Path

from _download import RateLimiter, fetch_parallel, fetch_with_retry

ROOT = "http://www.zeno.org"
KANT_PREFIX = "/Philosophie/M/Kant,+Immanuel"

# (output filename, German work title as it appears on zeno).
# The titles are converted to URL-form below — spaces → `+`, then
# percent-encoded for umlauts and other non-ASCII.
WORKS: list[tuple[str, str]] = [
    ("krv_de.html",          "Kritik der reinen Vernunft"),
    ("kpv_de.html",          "Kritik der praktischen Vernunft"),
    ("ku_de.html",           "Kritik der Urteilskraft"),
    ("ku_einl_de.html",      "Einleitung in die Kritik der Urteilskraft [1. Fassung]"),
    ("gms_de.html",          "Grundlegung zur Metaphysik der Sitten"),
    ("ms_de.html",           "Die Metaphysik der Sitten"),
    ("prol_de.html",         "Prolegomena zu einer jeden künftigen Metaphysik"),
    ("rel_de.html",          "Die Religion innerhalb der Grenzen der bloßen Vernunft"),
    ("anf_naturwiss_de.html", "Metaphysische Anfangsgründe der Naturwissenschaft"),
    ("aufklaerung_de.html",  "Beantwortung der Frage: Was ist Aufklärung"),
    ("orientieren_de.html",  "Was heißt: sich im Denken orientieren"),
    ("frieden_de.html",      "Zum ewigen Frieden. Ein philosophischer Entwurf"),
    ("gemeinspruch_de.html", "Über den Gemeinspruch: Das mag in der Theorie richtig sein, taugt aber nicht für die Praxis"),
    ("luegen_de.html",       "Über ein vermeintes Recht aus Menschenliebe zu lügen"),
]

_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)


def title_to_path(title: str) -> str:
    """German title → zeno URL path (under the Kant root).

    ``:``, ``[`` and ``]`` are deliberately excluded from `safe` —
    zeno.org percent-encodes those three in its own outbound hrefs
    (``%3A``, ``%5B``, ``%5D``), and `extract_links` matches children
    by `path.startswith(root_path)`, so leaving them literal here
    silently stops the BFS crawl at the first page for any title that
    contains one (issue #420).
    """
    # zeno uses `+` for spaces; non-ASCII is percent-encoded.
    return KANT_PREFIX + "/" + urllib.parse.quote(
        title.replace(" ", "+"), safe="+,./"
    )


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
    """Return zeno paths under `root_path` linked from the given HTML."""

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
    root_path: str,
    *,
    delay: float = 1.5,
    max_pages: int = 600,
    jobs: int = 1,
) -> list[tuple[str, str]]:
    """BFS-walk the work's subtree. Returns ``[(path, html), ...]``
    in visit order. ``jobs>1`` fetches each BFS level in parallel
    via ``fetch_parallel`` + per-host ``RateLimiter(delay)``."""

    queue: list[str] = [root_path]
    seen: set[str] = {root_path}
    pages: list[tuple[str, str]] = []
    limiter = RateLimiter(min_interval=delay) if jobs > 1 else None
    while queue and len(pages) < max_pages:
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
                    results.append((ROOT + p, fetch(ROOT + p)))
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
                time.sleep(delay)
        if len(pages) >= max_pages:
            break
    if len(pages) >= max_pages:
        print(f"  (hit max_pages={max_pages}; stopping)")
    return pages


def download_work(
    filename: str,
    title: str,
    out_dir: Path,
    *,
    delay: float,
    jobs: int = 1,
) -> Path | None:
    root_path = title_to_path(title)
    print(f"\n=== {filename}: {title} ===")
    print(f"  URL: {ROOT}{root_path}")
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
    ap = argparse.ArgumentParser(description="Fetch Kant German originals from zeno.org.")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "kant",
        help="Output directory for combined HTML files (default: data/kant/).",
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
        help="Restrict to these output filenames (e.g. --only krv_de.html).",
    )
    ap.add_argument(
        "--jobs",
        type=int,
        default=1,
        help=(
            "Parallel BFS workers (default: 1). When >1, each level's "
            "paths are fetched concurrently via fetch_parallel + per-host "
            "RateLimiter(delay). Cap at 2-3 for zeno.org."
        ),
    )
    args = ap.parse_args()

    works = [(f, t) for f, t in WORKS if not args.only or f in args.only]
    written: list[Path] = []
    for fn, title in works:
        out = download_work(
            fn, title, args.out, delay=args.delay, jobs=args.jobs
        )
        if out is not None:
            written.append(out)

    print(f"\nDone. Wrote {len(written)} file(s):")
    for p in written:
        print(f"  {p}")


if __name__ == "__main__":
    main()
