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
from html.parser import HTMLParser
from pathlib import Path

from _download import fetch_bytes_with_retry

USER_AGENT = "minerva-research/1.0 (local research; bulk fetch with delays)"

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


_HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def _fetch(url: str, *, timeout: float = 60, retries: int = 8) -> bytes:
    return fetch_bytes_with_retry(
        url,
        timeout=timeout,
        retries=retries,
        user_agent=USER_AGENT,
        extra_headers=_HTML_HEADERS,
        backoff_initial=5.0,
        backoff_max=120.0,
    )

class _ParagraphExtractor(HTMLParser):
    """Extract `<p>`-bounded text from Wikisource REST HTML, dropping
    `<script>` / `<style>` / `<sup>` / `<table>` (TOC, nav widgets)
    AND any element whose `class` contains a Wikisource apparatus
    marker (see `_SKIP_CLASS_TOKENS`). The class-aware skip is what
    catches Brunschvicg's editorial footnotes — the simple tag-only
    extractor used by `download_descartes_wikisource.py` would pull
    them in alongside Pascal's text and cause spurious cross-
    references."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._buf: list[str] = []
        self.paragraphs: list[str] = []

    def _should_skip(self, attrs: list[tuple[str, str | None]]) -> bool:
        for name, value in attrs:
            if name != "class" or value is None:
                continue
            tokens = value.split()
            if any(tok in _SKIP_CLASS_TOKENS for tok in tokens):
                return True
        return False

    def _flush(self) -> None:
        text = " ".join("".join(self._buf).split()).strip()
        if text:
            self.paragraphs.append(text)
        self._buf.clear()

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if self._skip_depth:
            # Track nested elements inside an already-skipped subtree
            # so end-tag balancing works.
            self._skip_depth += 1
            return
        if tag in _SKIP_TAGS or self._should_skip(attrs):
            self._skip_depth = 1
            return
        if tag == "p":
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            self._skip_depth -= 1
            return
        if tag in _BREAK_END_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._buf.append(data)

    def close(self) -> None:  # type: ignore[override]
        super().close()
        self._flush()


def _extract_paragraphs(html: bytes) -> list[str]:
    p = _ParagraphExtractor()
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
