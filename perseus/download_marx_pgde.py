#!/usr/bin/env python3
"""Download six Marx works from Projekt Gutenberg-DE.

URL pattern: ``projekt-gutenberg.org/authors/karl-marx/books/<slug>/
chapter/<n>``. The chapter system behaves inconsistently across
works:

  * Some works split into real chapters 1..N; URLs beyond N return
    a stub page (the book's title/cover page repeated).
  * Some works serve the COMPLETE text at every chapter URL —
    every `chapter/N` returns the same single-page content.

We handle both by SHA-256-deduplicating chapter fetches: walk
chapter/1, chapter/2, ... append the body when its hash hasn't been
seen, stop when consecutive chapters yield identical hashes (signals
the stub page or single-page rendering).

PG-DE HTML uses WordPress-style chrome: `.site-header`, `.menu`,
`.post-navigation`, `.sidebar`. We add these tokens to the
class-aware extractor's skip set.

Output: `data/marx/raw_deu/{manifest,brumaire,lohn_preis_profit,
lohnarbeit_kapital,elend_philosophie,heilige_familie,
zur_kritik_pol_oekonomie}.txt`

Note: Manifest is ALSO fetched by the Wikisource scraper. If both
run, the PG-DE version overwrites the Wikisource version. Decide
by order; current intent is Wikisource primary (cleaner text).
"""

from __future__ import annotations

import argparse
import hashlib
import time
from pathlib import Path

from _download import ParagraphExtractor, make_fetcher


# PG-DE work specs. Manifest is omitted from this list — the
# Wikisource scraper handles it (cleaner text). If you want a
# PG-DE fallback for Manifest, add it explicitly.
_WORKS: tuple[tuple[str, str], ...] = (
    # (filename, pg-de slug)
    ("brumaire.txt", "der-18-brumaire-des-louis-bonaparte"),
    ("lohn_preis_profit.txt", "lohn-preis-und-profit"),
    ("lohnarbeit_kapital.txt", "lohnarbeit-und-kapital"),
    ("elend_philosophie.txt", "das-elend-der-philosophie"),
    ("heilige_familie.txt", "die-heilige-familie-oder-kritik-der-kritischen-kritik"),
    ("zur_kritik_pol_oekonomie.txt", "zur-kritik-der-politischen-oekonomie"),
)

_MAX_CHAPTERS = 30  # safety cap


def _chapter_url(slug: str, n: int) -> str:
    return (
        f"https://www.projekt-gutenberg.org/authors/karl-marx/books/"
        f"{slug}/chapter/{n}"
    )


_fetch = make_fetcher()

def _extract_paragraphs(html: bytes) -> list[str]:
    p = ParagraphExtractor(
        skip_tags=_SKIP_TAGS,
        break_end_tags=_BREAK_END_TAGS,
        skip_class_tokens=_SKIP_CLASS_TOKENS,
    )
    p.feed(html.decode("utf-8"))
    p.close()
    return p.paragraphs


def _fetch_work(slug: str) -> list[str]:
    """Walk chapter URLs, dedup by content hash, return concatenated
    paragraph list across all real chapters.

    Stop conditions:
      - Two consecutive chapters yield identical body-paragraph hashes
        (stub page detected).
      - We hit `_MAX_CHAPTERS`.
    """

    seen_hashes: set[str] = set()
    all_paragraphs: list[str] = []
    prev_hash: str | None = None
    for n in range(1, _MAX_CHAPTERS + 1):
        url = _chapter_url(slug, n)
        print(f"  GET {url}")
        try:
            raw = _fetch(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"    404 at chapter/{n}; stopping")
                break
            raise
        paragraphs = _extract_paragraphs(raw)
        body = [p for p in paragraphs if len(p) >= 30]
        if not body:
            print(f"    chapter/{n}: no body content; stopping")
            break
        # Hash the body-paragraph list (ignoring order/whitespace
        # noise) to deduplicate single-page renderings vs real
        # multi-chapter works.
        body_signature = hashlib.sha256(
            "\n".join(body).encode("utf-8")
        ).hexdigest()
        if body_signature == prev_hash:
            # Two consecutive chapters identical → stub or single-
            # page work. We've already captured the content.
            print(f"    chapter/{n}: same as previous; stopping")
            break
        if body_signature in seen_hashes:
            # Cycled back to an earlier chapter — stop.
            print(f"    chapter/{n}: signature already seen; stopping")
            break
        seen_hashes.add(body_signature)
        prev_hash = body_signature
        print(f"    chapter/{n}: {len(body)} paragraphs")
        all_paragraphs.extend(body)
        # Insert a blank-line separator between chapter pages so the
        # downstream splitter sees breakpoints.
        all_paragraphs.append("")
        time.sleep(1.0)
    return all_paragraphs


def fetch_all(
    *,
    dest_root: Path,
    only: tuple[str, ...] | None = None,
) -> list[Path]:
    """Walk all configured works (or only the named filenames) and
    write each to `data/marx/raw_deu/<filename>`."""

    dest_dir = dest_root / "marx" / "raw_deu"
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, slug in _WORKS:
        if only and filename not in only:
            continue
        print(f"\n{filename} ← PG-DE /{slug}/")
        paragraphs = _fetch_work(slug)
        rendered = "\n\n".join(paragraphs).strip() + "\n"
        dest = dest_dir / filename
        dest.write_text(rendered, encoding="utf-8")
        print(f"  ↳ {dest} ({len(rendered):,} chars)")
        written.append(dest)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/marx/raw_deu/.",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Filenames to fetch (default: all).",
    )
    args = parser.parse_args()
    only = tuple(args.only) if args.only else None
    fetch_all(dest_root=args.data_root, only=only)


if __name__ == "__main__":
    main()
