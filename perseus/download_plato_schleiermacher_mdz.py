#!/usr/bin/env python3
"""Download Schleiermacher's German Plato *Der Staat* (Republic) from MDZ.

The Republic needs **Stephanus-aligned** text so it lines up with the Greek
+ English Republic (work id 81, ``stephanus`` citation). zeno's reading
edition has no Stephanus margins; archive.org's scans are the wrong dialogue,
poor Google OCR, or Fraktur. MDZ (Bayerische Staatsbibliothek) item
``bsb10237333`` — *Platons Werke. Th. 3, Bd. 1, Der Staat* (Schleiermacher) —
has clean OCR AND prints Stephanus page numbers in the margin, which survive
as monotonic left-margin tokens in the per-page hOCR.

This fetcher pulls every page's hOCR (word boxes preserved, so the splitter
can separate the marginal Stephanus tokens + running-header edition page from
body text) and concatenates them with ``<!-- MDZ_PAGE: N -->`` markers into
``data/plato/raw_deu/republic_schleiermacher_mdz.hocr``.

Public domain (Schleiermacher d. 1834; this edition 1850s).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _download import RateLimiter, fetch_parallel, fetch_with_retry

ID = "bsb10237333"
MANIFEST = f"https://api.digitale-sammlungen.de/iiif/presentation/v2/{ID}/manifest"
OCR = f"https://api.digitale-sammlungen.de/ocr/{ID}/{{page}}"


def page_count() -> int:
    man = json.loads(fetch_with_retry(MANIFEST, timeout=30, retries=4, encoding="utf-8"))
    return len(man["sequences"][0]["canvases"])


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch Schleiermacher Der Staat hOCR from MDZ.")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "data"
        / "plato"
        / "raw_deu"
        / "republic_schleiermacher_mdz.hocr",
        help="Output concatenated-hOCR path.",
    )
    ap.add_argument("--jobs", type=int, default=4, help="Parallel fetch workers.")
    ap.add_argument("--delay", type=float, default=0.3, help="Per-host min interval (s).")
    args = ap.parse_args()

    n = page_count()
    print(f"{ID}: {n} pages")
    urls = [OCR.format(page=p) for p in range(1, n + 1)]
    limiter = RateLimiter(min_interval=args.delay)
    results = fetch_parallel(urls, jobs=args.jobs, limiter=limiter, encoding="utf-8")

    parts: list[str] = []
    ok = 0
    for (url, res), page in zip(results, range(1, n + 1), strict=True):
        del url
        if isinstance(res, Exception):
            print(f"  [skip] page {page}: {res}")
            continue
        parts.append(f"<!-- MDZ_PAGE: {page} -->\n{res}")
        ok += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(parts), encoding="utf-8")
    print(f"  → {args.out} ({ok}/{n} pages, {args.out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
