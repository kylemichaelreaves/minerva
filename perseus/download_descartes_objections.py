#!/usr/bin/env python3
"""Download the Objections & Réponses to Descartes' Meditations from
fr.wikisource.org (Clerselier's 1647 French translation as printed in
Victor Cousin's 1824 Œuvres de Descartes, tome I/II).

The Latin corpus file (``data/descartes/raw_la/meditationes.txt``)
contains only the six Meditations — the seven sets of Objections by
Caterus, Mersenne, Hobbes, Arnauld, Gassendi et al. and Descartes'
Replies were never ingested. fr.wikisource has clean transcriptions of
ten pieces; the remaining ones (Réponses aux cinquièmes, the whole
Septièmes/Bourdin set, the letter to Clerselier) are NOT transcribed
there and would need an AT VII re-source — tracked in the remediation
plan, not fetched here.

Output: ``data/descartes/raw_fr/objections/<code>.html`` × 10 — the
Parsoid HTML of each page, saved raw so the splitter
(``corpus/split_descartes_objections.py``) owns all parsing and the
committed bytes pin its behavior.

Run: uv run python perseus/download_descartes_objections.py
"""

from __future__ import annotations

import argparse
import time
import urllib.error
from pathlib import Path
from urllib.parse import quote

from _download import FailureAccumulator, make_fetcher

# (output code, fr.wikisource page title). NB the curly apostrophe
# (U+2019) in the "Réponses de l’auteur" titles — the straight-quote
# variants 404.
PIECES: tuple[tuple[str, str], ...] = (
    ("obj1", "Méditations Métaphysiques/Premières objections, faites par M. Caterus"),
    ("rep1", "Méditations Métaphysiques/Réponses de l’auteur aux premières objections"),
    ("obj2", "Méditations Métaphysiques/Secondes objections, recueillies par le R. P. Mersenne"),
    ("rep2", "Méditations Métaphysiques/Réponses de l’auteur aux secondes objections"),
    # Hobbes's set is printed as interleaved objection/réponse pairs on
    # one page — the splitter separates the voices.
    ("obj3", "Méditations Métaphysiques/Troisièmes objections, faites par M. Hobbes, et réponses"),
    ("obj4", "Méditations Métaphysiques/Quatrièmes objections, faites par Arnauld"),
    ("rep4", "Méditations Métaphysiques/Réponses de l’auteur aux quatrièmes objections"),
    ("obj5", "Méditations Métaphysiques/Cinquièmes objections, faites par Gassendy"),
    ("obj6", "Méditations Métaphysiques/Sixièmes objections"),
    ("rep6", "Méditations Métaphysiques/Réponses aux Sixièmes objections"),
)

_fetch = make_fetcher()


def _rest_url(title: str) -> str:
    return "https://fr.wikisource.org/api/rest_v1/page/html/" + quote(title, safe="")


def main() -> int:
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
        help="Seconds between requests (be polite to fr.wikisource).",
    )
    args = ap.parse_args()
    out_dir = args.data_root / "descartes" / "raw_fr" / "objections"
    out_dir.mkdir(parents=True, exist_ok=True)

    # One dead piece must not lose the other nine; accumulating and
    # reporting them at the end is what a scripted run can actually
    # notice (#316 — a per-item `except: continue` that never says
    # what it dropped still exits 0).
    failures = FailureAccumulator()
    for code, title in PIECES:
        dest = out_dir / f"{code}.html"
        print(f"=== {code}: {title}")
        try:
            html = _fetch(_rest_url(title))
        except urllib.error.HTTPError as e:
            failures.record(code, f"HTTP {e.code}")
            continue
        # fr.wikisource serves rate-limit pages as HTTP 200 — a real
        # transcription is tens of KB; refuse suspicious dwarfs. See
        # the wikimedia-rest gotchas note.
        if len(html) < 10_000:
            raise RuntimeError(
                f"{code}: response is only {len(html)} bytes — likely a "
                f"rate-limit/error page served as 200. Re-run with a "
                f"longer --delay."
            )
        dest.write_bytes(html)
        print(f"  saved {len(html):,} bytes -> {dest}")
        time.sleep(args.delay)

    return failures.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
