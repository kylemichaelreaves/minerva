#!/usr/bin/env python3
"""Download Pascal's *Pensées* (Brunschvicg 1925 edition) from
fr.wikisource.org.

Project Gutenberg doesn't carry a clean French Pensées — its only
French-titled Pascal item (PG 29772) is the Voltaire/Condorcet
annotated edition, which interleaves commentary with Pascal's
text. The Brunschvicg edition on Wikisource is the standard
scholarly French original (Léon Brunschvicg, "Pensées et opuscules",
Hachette 1925), serves clean HTML via the REST API, and is
organized into 14 sections (some subdivided) plus the Mémorial.

Output: a single concatenated file with `SECTION <roman>` headers
so the generic `split_by_chapter` splitter at
`src/minerva/corpus/split_paragraphic.py` can chunk it without
custom parsing:

    data/pascal/raw_fra/pensees.txt

Run:

    uv run python perseus/download_pascal_fr.py

The script reuses the `_ParagraphExtractor` HTML strip pattern from
`download_descartes_wikisource.py` — Wikisource's REST HTML drops
into the same shape on the Pascal pages.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from _download import ParagraphExtractor, make_fetcher

# Brunschvicg sections + Mémorial, in the order they should appear
# in the concatenated output. The path component after the host is
# `Pensées_(Pascal,_éd._Brunschvicg)/Pensées/<SUBPATH>` — slashes
# in REST URLs become `%2F`.
_SECTIONS: tuple[tuple[str, str], ...] = (
    # (display heading, Wikisource subpage name)
    ("Mémorial", "Mémorial"),
    ("Section I", "Section_I"),
    ("Section II-1", "Section_II-1"),
    ("Section II-2", "Section_II-2"),
    ("Section III", "Section_III"),
    ("Section IV", "Section_IV"),
    ("Section V", "Section_V"),
    ("Section VI", "Section_VI"),
    ("Section VII", "Section_VII"),
    ("Section VIII", "Section_VIII"),
    ("Section IX", "Section_IX"),
    ("Section X", "Section_X"),
    ("Section XI", "Section_XI"),
    ("Section XII", "Section_XII"),
    ("Section XIII", "Section_XIII"),
    ("Section XIV", "Section_XIV"),
)

_BASE_PATH = "Pensées_(Pascal,_éd._Brunschvicg)/Pensées"


def _section_url(subpath: str) -> str:
    # Wikisource REST API expects the full title with `/` encoded as
    # `%2F`; non-ASCII chars (e.g. é, ç) are URL-encoded via quote().
    from urllib.parse import quote

    title = f"{_BASE_PATH}/{subpath}"
    return f"https://fr.wikisource.org/api/rest_v1/page/html/{quote(title, safe='')}"


_fetch = make_fetcher()

# Tag sets are the canonical pair shared with the other HTML scrapers
# (see `download_spinoza.py` / `download_augustine.py`). The class
# tokens are Wikisource's editorial-apparatus markers, matching the
# set the Wikisource scraper in `download_marcus_aurelius.py` uses.
_SKIP_TAGS = frozenset({"script", "style", "table", "sup", "noscript"})
_BREAK_END_TAGS = frozenset({"p", "li", "div"})
_SKIP_CLASS_TOKENS = frozenset(
    {"mw-references", "headertemplate", "ws-noexport", "navbox", "metadata"}
)


def _extract_paragraphs(html: bytes) -> list[str]:
    """Extract `<p>`-bounded text from Wikisource REST HTML, dropping
    `<script>` / `<style>` / `<sup>` / `<table>` (TOC, nav widgets)
    AND any element whose `class` contains a Wikisource apparatus
    marker (see `_SKIP_CLASS_TOKENS`). The class-aware skip is what
    catches Brunschvicg's editorial footnotes — the simple tag-only
    extractor used by `download_descartes_wikisource.py` would pull
    them in alongside Pascal's text and cause spurious cross-
    references."""

    p = ParagraphExtractor(
        skip_tags=_SKIP_TAGS,
        break_end_tags=_BREAK_END_TAGS,
        skip_class_tokens=_SKIP_CLASS_TOKENS,
    )
    p.feed(html.decode("utf-8"))
    p.close()
    return p.paragraphs


def fetch_pensees(*, dest_root: Path) -> Path:
    """Walk every section URL, extract paragraphs, concatenate with
    SECTION headers. Front-matter / navigation paragraphs from any
    given section page (under ~30 chars after whitespace-collapse)
    are dropped — they're typically Wikisource page-nav links."""

    sections_out: list[str] = []
    total_paragraphs = 0
    for heading, subpath in _SECTIONS:
        url = _section_url(subpath)
        print(f"GET {url}")
        raw = _fetch(url)
        paragraphs = _extract_paragraphs(raw)
        # First few paragraphs on each Wikisource subpage are
        # typically TOC / "page suivante" navigation chrome. Filter
        # to substantive content only.
        body = [p for p in paragraphs if len(p) >= 30]
        total_paragraphs += len(body)
        print(f"  {len(body)} paragraphs (from {len(paragraphs)} extracted)")
        # SECTION header on its own line so the chapter splitter's
        # `^SECTION <numeral>` regex matches. Blank lines bracket
        # the header for clean chunk-boundary detection.
        sections_out.append("")
        sections_out.append(heading.upper())
        sections_out.append("")
        sections_out.extend(body)
        time.sleep(1.0)  # Be polite to fr.wikisource.org

    rendered = "\n\n".join(sections_out).strip() + "\n"
    dest_dir = dest_root / "pascal" / "raw_fra"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "pensees.txt"
    dest.write_text(rendered, encoding="utf-8")
    print(
        f"\n→ {dest} "
        f"({len(rendered):,} chars · "
        f"{total_paragraphs} paragraphs · "
        f"{len(_SECTIONS)} sections)"
    )
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; file lands in <root>/pascal/raw_fra/.",
    )
    args = parser.parse_args()

    fetch_pensees(dest_root=args.data_root)

    print(
        "\nDone. Remove the stale 'pascal' entry from "
        "download_early_modern.py if you haven't already — the "
        "PG 24499 ID it referenced was an English translation."
    )
    print("Next: uv run minerva ingest && uv run minerva index")


if __name__ == "__main__":
    main()
