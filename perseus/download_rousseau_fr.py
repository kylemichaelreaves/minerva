#!/usr/bin/env python3
"""Download Rousseau's *Du contrat social* (1762 edition) from
fr.wikisource.org.

Project Gutenberg has no clean French Contrat Social — its only
hit for "Rousseau Contrat Social" was the Finnish translation
(PG 53593). PG 4636 (the previously-configured ID) was a complete
mismatch — "A Tramp Through the Bret Harte Country" by T. D.
Beasley. The 1762 Wikisource transcription serves the full text
as one page (`Texte_entier`), so we don't need the per-chapter
walk that the Pascal scraper performs.

Output:

    data/rousseau/raw_fra/contrat_social.txt

Run:

    uv run python perseus/download_rousseau_fr.py

The script reuses the class-aware `_ParagraphExtractor` from the
Pascal scraper — same Wikisource chrome ('mw-references' /
'headertemplate' / 'ws-noexport' classes) needs the same stripping
to avoid editorial-apparatus bleed into the corpus.
"""

from __future__ import annotations

import argparse
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

from _download import fetch_bytes_with_retry

USER_AGENT = "minerva-research/1.0 (local research; bulk fetch with delays)"

# Per-work scrape spec. A work either has a single Wikisource title
# (the `Texte_entier` view) OR a list of sub-page (heading, title)
# tuples that get concatenated with uppercase headings between them.
# The heading text MUST match `_HEADING_RE` shape 2 in
# `corpus/split_paragraphic.py` — uppercase letter + 6+ uppercase/
# whitespace chars — so the chapter splitter chunks at each
# Livre / Partie boundary.
_WORKS: tuple[dict, ...] = (
    {
        "filename": "contrat_social.txt",
        "display": "Du contrat social (1762)",
        "single": "Du contrat social/Édition 1762/Texte entier",
    },
    {
        "filename": "premier_discours.txt",
        "display": "Discours sur les sciences et les arts (1750)",
        "single": "Discours sur les sciences et les arts/Édition Genève 1782",
    },
    {
        "filename": "second_discours.txt",
        "display": "Discours sur l'origine de l'inégalité (1755)",
        "subpages": (
            (
                "PRÉFACE",
                "Discours sur l’origine et les fondements de l’inégalité parmi les hommes/Préface",
            ),
            (
                "PREMIÈRE PARTIE",
                "Discours sur l’origine et les fondements de l’inégalité parmi les hommes/Première partie",
            ),
            (
                "SECONDE PARTIE",
                "Discours sur l’origine et les fondements de l’inégalité parmi les hommes/Seconde partie",
            ),
            (
                "PART NOTES",  # "NOTES" alone (5 chars) wouldn't match the
                # ≥7-char ALL-CAPS heading shape, so we prefix with "PART"
                # which the splitter recognizes under shape 1.
                "Discours sur l’origine et les fondements de l’inégalité parmi les hommes/Notes",
            ),
        ),
    },
    {
        "filename": "economie_politique.txt",
        "display": "Discours sur l'économie politique (1755)",
        "single": "L’Encyclopédie/1re édition/ECONOMIE ou OECONOMIE",
    },
    {
        "filename": "emile.txt",
        "display": "Émile, ou De l'éducation (1762)",
        "subpages": (
            ("LIVRE I", "Émile, ou De l’éducation/Édition 1782/Livre I"),
            ("LIVRE II", "Émile, ou De l’éducation/Édition 1782/Livre II"),
            ("LIVRE III", "Émile, ou De l’éducation/Édition 1782/Livre III"),
            ("LIVRE IV", "Émile, ou De l’éducation/Édition 1782/Livre IV"),
            ("LIVRE V", "Émile, ou De l’éducation/Édition 1782/Livre V"),
        ),
    },
    {
        "filename": "essai_origine_langues.txt",
        "display": "Essai sur l'origine des langues (1781)",
        "single": "Essai sur l’origine des langues",
    },
)


def _url(title: str) -> str:
    return (
        "https://fr.wikisource.org/api/rest_v1/page/html/"
        + quote(title, safe="")
    )


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
    """Class-aware HTML stripper. Mirror of the Pascal scraper's
    extractor. See `perseus/download_pascal_fr.py` for the rationale —
    editorial-apparatus classes mustn't leak into corpus text."""

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


def _fetch_one_page(title: str) -> list[str]:
    """Fetch one Wikisource page and return its filtered paragraphs.
    Drops paragraphs under 30 chars to filter nav-chrome bleed."""

    url = _url(title)
    print(f"  GET {url}")
    raw = _fetch(url)
    paragraphs = _extract_paragraphs(raw)
    body = [p for p in paragraphs if len(p) >= 30]
    print(f"    {len(body)} paragraphs (from {len(paragraphs)} extracted)")
    return body


def _render_work(spec: dict) -> str:
    """Build the on-disk text for one work spec. Single-page works
    return the paragraph stream; multi-part works prepend an uppercase
    LIVRE/PARTIE heading before each sub-page's body so the chapter
    splitter chunks at sub-page boundaries."""

    if "single" in spec:
        body = _fetch_one_page(spec["single"])
        return "\n\n".join(body).strip() + "\n"

    out: list[str] = []
    for heading, sub_title in spec["subpages"]:
        body = _fetch_one_page(sub_title)
        if not body:
            print(
                f"  WARNING: sub-page {sub_title!r} returned 0 paragraphs; "
                "skipping (may be a 404 or page rename)"
            )
            continue
        # Blank line, heading, blank line, body — the splitter
        # expects the heading on its own line bracketed by whitespace.
        out.append("")
        out.append(heading)
        out.append("")
        out.extend(body)
        time.sleep(1.0)  # Polite to fr.wikisource.org
    return "\n\n".join(out).strip() + "\n"


def fetch_all(*, dest_root: Path, only: tuple[str, ...] | None = None) -> list[Path]:
    """Walk the work specs and fetch every one (or only the named
    filenames if `only` is non-empty). Returns the list of paths
    written."""

    dest_dir = dest_root / "rousseau" / "raw_fra"
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for spec in _WORKS:
        if only and spec["filename"] not in only:
            continue
        print(f"\n{spec['display']} → {spec['filename']}")
        rendered = _render_work(spec)
        dest = dest_dir / spec["filename"]
        dest.write_text(rendered, encoding="utf-8")
        print(f"  ↳ {dest} ({len(rendered):,} chars)")
        written.append(dest)
        time.sleep(1.0)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/rousseau/raw_fra/.",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        default=None,
        help=(
            "Optional list of filenames to fetch "
            "(e.g. `--only second_discours.txt emile.txt`). "
            "Default: fetch all."
        ),
    )
    args = parser.parse_args()

    only = tuple(args.only) if args.only else None
    fetch_all(dest_root=args.data_root, only=only)
    print("\nNext: uv run minerva ingest && uv run minerva index")


if __name__ == "__main__":
    main()
