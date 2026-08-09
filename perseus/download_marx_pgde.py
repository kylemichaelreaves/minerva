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

PG-DE serves a GeneratePress WordPress theme. Rather than enumerate its
chrome we take the chapter body's own container,
`div.book-reader__chapter-content-wrapper` — see `_content_region` for
why the skip-set approach cannot finish the job here (issue #152).

That container also de-duplicates: PG-DE renders the chapter body
**twice** per page (two wrapper regions, differing in markup but
text-identical at 243,630 characters each on `brumaire` chapter/2), so
parsing the whole document emitted every Marx paragraph twice.

*** projekt-gutenberg.org SOMETIMES 403s the canonical `USER_AGENT` in
`_download.py`, and the pattern is per-URL and intermittent rather than
the flat block this docstring used to describe. Measured 2026-08-09 over
all six works, canonical UA vs `foo/1.0`, every other header held equal:
`brumaire` served 200 to both on every attempt, while four of the six
403'd to the canonical UA and 200'd to `foo/1.0` in the same pass — and
`lohnarbeit-und-kapital` returned 403 six times running and 200 a few
minutes later. So it behaves like a bot-mitigation layer with a
short-lived per-(UA, URL) verdict, not like a deliberate substring
blacklist. Either way the response to it is the same: do NOT change the
UA or give this script a private fetcher to get past it. What is worth
knowing is that 403 is not in `_RETRY_CODES`, so the script dies on its
first refused work with no partial output — see issue #299, still open
for the decision. The class/container findings above were measured with
a one-off diagnostic User-Agent. ***

Chapter layout, measured on `der-18-brumaire-des-louis-bonaparte`:
chapter/1 is front matter (title + publication note), chapter/2 carries
the entire work, chapter/3 repeats chapter/1. The hash dedup below stops
correctly on the `seen_hashes` branch, not the `prev_hash` one.

Output: `data/marx/raw_deu/{brumaire,lohn_preis_profit,
lohnarbeit_kapital,elend_philosophie,heilige_familie,
zur_kritik_pol_oekonomie}.txt` — six files, matching `_WORKS`.

Note: Manifest is deliberately NOT in `_WORKS` — the Wikisource scraper
handles it (cleaner text). If you add a PG-DE fallback for it, note that
it would overwrite the Wikisource version.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import time
import urllib.error
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

# Tag/class skip sets for the class-aware extractor. The tag sets are
# the canonical pair shared with the other HTML scrapers (see
# `download_spinoza.py` / `download_augustine.py`).
#
# The class tokens are measured against a live chapter page, not read off
# this module's docstring — issue #152. Of the four previously assumed
# (`site-header`, `menu`, `post-navigation`, `sidebar`) only
# `site-header` matched anything: PG-DE is a GeneratePress WordPress
# theme whose nav is `main-navigation` / `sub-menu` / `menu-item`, has no
# `post-navigation` at all, and whose only `sidebar` token is
# `<body class="no-sidebar">` — which is a *different* token, and just as
# well, since matching the `<body>` element would have skipped the entire
# document.
#
# Measured leak with the old set, on
# `der-18-brumaire-des-louis-bonaparte/chapter/1`: 24 of 24 paragraphs
# clearing the caller's `len >= 30` filter were chrome — Amazon/Thalia
# affiliate buttons, the EPUB download modal, donation prompts, the
# cookie/footer block — and not one line of Marx.
#
# NOTE `sidebar` is deliberately *not* re-added in any widened form. Token
# matching is exact per whitespace-split token, which is the only reason
# `no-sidebar` on `<body>` is harmless; a substring match would empty
# every page.
_SKIP_TAGS = frozenset({"script", "style", "table", "sup", "noscript"})
_BREAK_END_TAGS = frozenset({"p", "li", "div"})
_SKIP_CLASS_TOKENS = frozenset(
    {
        # site chrome
        "site-header",
        "main-navigation",
        "mobile-menu-control-wrapper",
        "menu-bar-items",
        "screen-reader-text",
        # commerce / download / donation furniture
        "book-app__button",
        "book-reader__affiliate-icon",
        "gl-epub-modal",
        "gl-epub-modal__step",
        "gl-epub-modal__actions",
        # chapter pager and footer
        "book-reader__chapter-navigation",
        "gbp-footer__link",
        "gbp-section__inner",
        "site-footer",
    }
)


# The reliable seam. PG-DE wraps the chapter body — and nothing else — in
# `<div class="book-reader__chapter-content-wrapper">`. Skip sets alone
# cannot finish the job here: after widening the set above to every chrome
# class actually present, four paragraphs still came through (the
# Amazon/Thalia row, the e-book pitch, the `← Vorheriges Kapitel` pager
# and the donation prompt), and a WordPress theme will grow more. Taking
# the content container is stable against that churn in a way that
# enumerating its opposite is not.
_CONTENT_OPEN_RE = re.compile(
    r"<div[^>]*\bclass=\"[^\"]*\bbook-reader__chapter-content-wrapper\b[^\"]*\"[^>]*>",
    re.IGNORECASE,
)
_DIV_BOUNDARY_RE = re.compile(r"<div\b|</div\s*>", re.IGNORECASE)


def _content_region(html: str) -> str | None:
    """Return the chapter-body subtree, or None when the marker is absent.

    Walks `<div>` / `</div>` from the wrapper's open tag to its match so
    nested divs inside the body are not mistaken for the end.
    """

    m = _CONTENT_OPEN_RE.search(html)
    if m is None:
        return None
    depth = 1
    pos = m.end()
    for tok in _DIV_BOUNDARY_RE.finditer(html, pos):
        depth += 1 if tok.group(0).lower().startswith("<div") else -1
        if depth == 0:
            return html[m.end() : tok.start()]
    return html[m.end() :]  # unclosed; take the remainder


def _extract_paragraphs(html: bytes) -> list[str]:
    decoded = html.decode("utf-8")
    region = _content_region(decoded)
    if region is None:
        # Loud, not silent: if PG-DE renames the wrapper we fall back to
        # the whole document and the chrome returns, so say so.
        print(
            "    WARNING: book-reader__chapter-content-wrapper not found; "
            "parsing whole page (chrome will leak)"
        )
        region = decoded
    p = ParagraphExtractor(
        skip_tags=_SKIP_TAGS,
        break_end_tags=_BREAK_END_TAGS,
        skip_class_tokens=_SKIP_CLASS_TOKENS,
    )
    p.feed(region)
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
