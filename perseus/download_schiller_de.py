#!/usr/bin/env python3
"""Download Friedrich Schiller's theoretical/aesthetic writings from zeno.org.

Mirrors `download_kant_de.py`: BFS-walks each work's URL subtree under
`/Literatur/M/Schiller,+Friedrich/Theoretische+Schriften`, fetches every
reachable subpage, and concatenates them into one `<!-- ZENO_PAGE: ... -->`
marked HTML file per work in `data/schiller/raw_deu/` — the format the
`split_zeno` parser consumes.

Scope is Schiller's aesthetic philosophy: the Aesthetic Education letters
plus the major companion essays. Occasional book reviews (Bürger, Matthisson,
Egmont) and the Universalgeschichte lecture are deliberately omitted.

Schiller died 1805; all works are public domain.
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.parse
from pathlib import Path

from _download import RateLimiter, fetch_parallel, fetch_with_retry

ROOT = "http://www.zeno.org"
SCHILLER_PREFIX = "/Literatur/M/Schiller,+Friedrich/Theoretische+Schriften"

# (output filename, work title exactly as it appears on the zeno path).
WORKS: list[tuple[str, str]] = [
    (
        "aesthetische_erziehung_de.html",
        "Über die ästhetische Erziehung des Menschen in einer Reihe von Briefen",
    ),
    ("naive_sentimentalische_de.html", "Über naive und sentimentalische Dichtung"),
    ("anmut_wuerde_de.html", "Über Anmut und Würde"),
    ("kallias_de.html", "[Kallias oder über die Schönheit]"),
    ("ueber_erhabene_de.html", "Über das Erhabene"),
    ("vom_erhabenen_de.html", "Vom Erhabenen"),
    ("pathetische_de.html", "Über das Pathetische"),
    ("tragische_kunst_de.html", "Über die tragische Kunst"),
    ("tragische_gegenstaende_de.html", "Über den Grund des Vergnügens an tragischen Gegenständen"),
    ("philosophische_briefe_de.html", "Philosophische Briefe"),
]

_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)


def title_to_path(title: str) -> str:
    """Work title → zeno URL path (under the Schiller theoretical-works root)."""
    return SCHILLER_PREFIX + "/" + urllib.parse.quote(title.replace(" ", "+"), safe="+,:./[]")


def fetch(url: str, *, timeout: float = 30, retries: int = 8) -> str:
    return fetch_with_retry(url, timeout=timeout, retries=retries, encoding="iso-8859-1")


def extract_links(html: str, root_path: str) -> list[str]:
    """Return zeno paths under `root_path` linked from the given HTML."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in _HREF_RE.findall(html):
        if raw.startswith(ROOT):
            raw = raw[len(ROOT) :]
        if not raw.startswith("/"):
            continue
        path = raw.split("#", 1)[0].split("?", 1)[0]
        if not path.startswith(root_path) or path == root_path or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def crawl_work(
    root_path: str, *, delay: float = 1.5, max_pages: int = 400, jobs: int = 1
) -> list[tuple[str, str]]:
    """BFS-walk the work's subtree; returns ``[(path, html), ...]`` in visit order."""
    queue: list[str] = [root_path]
    seen: set[str] = {root_path}
    pages: list[tuple[str, str]] = []
    limiter = RateLimiter(min_interval=delay) if jobs > 1 else None
    while queue and len(pages) < max_pages:
        batch = queue[: max(jobs, 1)]
        queue = queue[len(batch) :]
        if jobs > 1:
            results = fetch_parallel(
                [ROOT + p for p in batch], jobs=jobs, limiter=limiter, encoding="iso-8859-1"
            )
        else:
            results = []
            for p in batch:
                try:
                    results.append((ROOT + p, fetch(ROOT + p)))
                except Exception as e:  # one bad page shouldn't abort the work
                    results.append((ROOT + p, e))
        for (url, res), path in zip(results, batch, strict=True):
            del url
            if isinstance(res, Exception):
                print(f"  [skip] {path}: {res}")
                continue
            pages.append((path, res))
            print(
                f"  [{len(pages):>3}] {urllib.parse.unquote(path)[-80:]:<80} {len(res):>7,} bytes"
            )
            for child in extract_links(res, root_path):
                if child not in seen:
                    seen.add(child)
                    queue.append(child)
            if jobs == 1:
                time.sleep(delay)
    if len(pages) >= max_pages:
        print(f"  (hit max_pages={max_pages}; stopping)")
    return pages


def download_work(
    filename: str, title: str, out_dir: Path, *, delay: float, jobs: int = 1
) -> Path | None:
    root_path = title_to_path(title)
    print(f"\n=== {filename}: {title} ===")
    print(f"  URL: {ROOT}{root_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = crawl_work(root_path, delay=delay, jobs=jobs)
    if not pages:
        print("  no content fetched")
        return None
    parts = [f"<!-- ZENO_PAGE: {urllib.parse.unquote(p)} -->\n{html}" for p, html in pages]
    out_path = out_dir / filename
    out_path.write_text("\n\n".join(parts), encoding="utf-8")
    print(f"  → {out_path} ({len(pages)} pages, {out_path.stat().st_size:,} bytes)")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch Schiller's theoretical writings from zeno.org.")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "schiller" / "raw_deu",
        help="Output directory (default: data/schiller/raw_deu/).",
    )
    ap.add_argument("--delay", type=float, default=1.5, help="Seconds between requests.")
    ap.add_argument("--only", nargs="*", default=None, help="Restrict to these output filenames.")
    ap.add_argument("--jobs", type=int, default=1, help="Parallel BFS workers (cap 2-3 for zeno).")
    args = ap.parse_args()

    works = [(f, t) for f, t in WORKS if not args.only or f in args.only]
    written: list[Path] = []
    for fn, title in works:
        out = download_work(fn, title, args.out, delay=args.delay, jobs=args.jobs)
        if out is not None:
            written.append(out)
    print(f"\nDone. Wrote {len(written)} file(s):")
    for p in written:
        print(f"  {p}")


if __name__ == "__main__":
    main()
