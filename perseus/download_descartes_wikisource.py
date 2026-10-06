#!/usr/bin/env python3
"""Download the Wikisource-only half of the Descartes corpus.

Two works land here, both via Wikisource's REST HTML API:

  • Principia philosophiae (Latin, complete — all four Pars, ~487 articles)
  • Principes de la philosophie (French Desrez 1838 — Pars I only,
    ~76 articles; Wikisource does not carry Parts II–IV).

Both Wikisource pages are reader-mode-friendly and serve full text
inline on a single REST endpoint per work — no subpage walk needed.
The Latin source carries Descartes' bracketed article markers
`[N.NNN]` verbatim (e.g. `[1.007]` = Pars I, art. 7); the French
source uses `<p>N. Title</p>` / `<p>Body</p>` pairs, and this script
inserts synthetic `[1.NNN]` markers so a single article-splitter
regex matches both. Article 1 of the French edition is sourced with
no numbered title (it opens the work directly) — the script
synthesizes `[1.001]` for it.

Output:

    data/descartes/raw_la/principia.txt
    data/descartes/raw_fr/principes_pars1.txt

Run via:

    uv run python perseus/download_descartes_wikisource.py
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from _download import ParagraphExtractor, make_fetcher

_LATIN_URL = "https://la.wikisource.org/api/rest_v1/page/html/Principia_philosophiae"
_FRENCH_URL = (
    "https://fr.wikisource.org/api/rest_v1/page/html/Principes_de_la_philosophie_(%C3%A9d._Desrez)"
)


_fetch = make_fetcher()

# Tag-only skip sets — this scraper deliberately uses the simple
# variant (no class-aware filtering); see the note in
# `download_pascal_fr._extract_paragraphs`.
_SKIP_TAGS = frozenset({"script", "style", "table", "sup", "noscript"})
_BREAK_END_TAGS = frozenset({"p", "li", "div"})


def _extract_paragraphs(html: bytes) -> list[str]:
    p = ParagraphExtractor(skip_tags=_SKIP_TAGS, break_end_tags=_BREAK_END_TAGS)
    p.feed(html.decode("utf-8"))
    p.close()
    return p.paragraphs


# Latin article-marker line shape produced by Wikisource: `[N.NNN]`
# at the very start of a paragraph, followed by the article's title
# (or sometimes only the marker on a line). Match-anchored so we
# don't trip on the marker appearing inside body prose.
_LATIN_ARTICLE_RE = re.compile(r"^\[(\d+)\.(\d{3})\]\s*(.*)$")

# French Desrez article-marker shape: ordinal at the start of the
# paragraph, optionally followed by a period, then space, then a
# capitalized short title. The Wikisource transcription is loose
# about both the article-number period (missing on art. 45 in
# Pars I) and the title-ending period (missing on art. 69), so we
# allow both. Articles run 1..76 (Pars I only).
#
# The length cap on the title is what protects against false
# matches against body paragraphs starting with a number (date
# strings, footnote ordinals): real article titles in Desrez run
# 30-250 chars; body paragraphs are uniformly 400+ chars in this
# Pars-I excerpt, so 300 is well clear of either side.
_FRENCH_ARTICLE_RE = re.compile(r"^(\d+)\.?\s+([A-ZÀ-ÿ].{4,300})\s*$")


def _render_latin_principia(paragraphs: list[str]) -> str:
    """Join paragraphs into the canonical `[N.NNN]` + body shape on
    disk. Each article's marker and title go on one line; body
    paragraphs follow, separated by blank lines; articles are
    separated by an extra blank line. Front-matter paragraphs
    (anything before the first `[1.001]` marker) are dropped.
    """

    out: list[str] = []
    started = False
    for para in paragraphs:
        m = _LATIN_ARTICLE_RE.match(para)
        if m:
            if not started:
                started = True
            else:
                out.append("")  # blank line between articles
            pars, art, rest = m.group(1), m.group(2), m.group(3).strip()
            header = f"[{pars}.{art}]"
            if rest:
                header = f"{header} {rest}"
            out.append(header)
            continue
        if started:
            out.append(para)
    return "\n\n".join(out).strip() + "\n"


def _render_french_principes(paragraphs: list[str]) -> str:
    """French Desrez has no `[N.NNN]` markers in the source — but
    each article does carry a `N. Title` paragraph (including art. 1).
    We synthesize bracket markers by walking the paragraph stream:
    each `^N. Title$` paragraph starts a new article (we emit
    `[1.NNN] Title`); paragraphs that follow up to the next title
    are the article body. Everything before the first numbered
    title (bibliographic metadata, source attribution) is dropped.
    """

    out: list[str] = []
    current_article: int | None = None
    for para in paragraphs:
        m = _FRENCH_ARTICLE_RE.match(para)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 1000:
                current_article = n
                if out:
                    out.append("")
                out.append(f"[1.{n:03d}] {m.group(2).strip()}")
                continue
        if current_article is not None:
            out.append(para)
    return "\n\n".join(out).strip() + "\n"


def fetch_latin_principia(*, dest_root: Path) -> Path:
    print(f"GET {_LATIN_URL}")
    raw = _fetch(_LATIN_URL)
    paragraphs = _extract_paragraphs(raw)
    rendered = _render_latin_principia(paragraphs)
    dest_dir = dest_root / "descartes" / "raw_la"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "principia.txt"
    dest.write_text(rendered, encoding="utf-8")
    n_articles = sum(1 for line in rendered.splitlines() if _LATIN_ARTICLE_RE.match(line))
    print(f"  → {dest} ({len(rendered):,} chars · {n_articles} articles)")
    return dest


def fetch_french_principes_pars1(*, dest_root: Path) -> Path:
    print(f"GET {_FRENCH_URL}")
    raw = _fetch(_FRENCH_URL)
    paragraphs = _extract_paragraphs(raw)
    rendered = _render_french_principes(paragraphs)
    dest_dir = dest_root / "descartes" / "raw_fr"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "principes_pars1.txt"
    dest.write_text(rendered, encoding="utf-8")
    n_articles = sum(1 for line in rendered.splitlines() if _LATIN_ARTICLE_RE.match(line))
    print(f"  → {dest} ({len(rendered):,} chars · {n_articles} articles)")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/descartes/raw_*/.",
    )
    args = parser.parse_args()

    fetch_latin_principia(dest_root=args.data_root)
    fetch_french_principes_pars1(dest_root=args.data_root)

    print()
    print("French Principes Parts II–IV are not on Wikisource — when")
    print("those land (likely from Gallica), drop them in raw_fr/ and")
    print("extend descartes_works.py with a third entry.")


if __name__ == "__main__":
    main()
