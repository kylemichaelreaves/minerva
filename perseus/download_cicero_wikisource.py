#!/usr/bin/env python3
"""Download Cicero's 16 philosophical + rhetorical works from
la.wikisource.org.

Each work has a top-level Latin page (e.g.
``https://la.wikisource.org/wiki/De_officiis``) which links to
per-book sub-pages (Liber Primus / Liber Secundus / etc.). We
BFS-walk each work's URL tree under its top-level slug, fetch
every reachable sub-page's HTML, and concatenate the text into
a single .txt file per work — same pattern as
``download_marx_zeno.py`` but targeting la.wikisource.

Output: ``data/cicero/raw_la/<work_code>.txt`` × 16.

Run: uv run python perseus/download_cicero_wikisource.py

FIDELITY CAVEAT — read before re-running over existing files.

``fetch_work`` was reconstructed in 2026-08 (issue #116); the original
never made it into the repo, so the 14 files already in
``data/cicero/raw_la/`` were produced by an implementation we no
longer have. This one reproduces them closely but not byte-for-byte:
spot-checked against ``de_fato_lat.txt`` the Latin body is identical,
and against ``de_natura_deorum_lat.txt`` ~109 of 622 lines differ —
per-Liber page titles, Aratea verse that Wikisource breaks into short
``<poem>`` lines, and Arabic section markers in Liber III.

Byte-identity is not reachable anyway: la.wikisource has changed since
the May 2026 fetch (De fato has gained a ``FRAGMENTA`` heading). So
re-running this over the committed files WILL churn chunk_ids and cost
the affected works their embeddings / lemmas / cross-references. Use
``--only`` to fetch genuinely missing works (``de_officiis_lat.txt``
is the one gap) rather than refreshing the set wholesale.
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.error
from pathlib import Path
from urllib.parse import quote, unquote

from _download import ParagraphExtractor, make_fetcher

# (output filename, la.wikisource top-level page title)
_WORKS: tuple[tuple[str, str], ...] = (
    ("de_inventione_lat.txt", "De inventione"),
    ("de_oratore_lat.txt", "De oratore"),
    ("de_re_publica_lat.txt", "De re publica"),
    ("de_legibus_lat.txt", "De legibus"),
    ("brutus_lat.txt", "Brutus"),
    ("orator_lat.txt", "Orator"),
    # Academica intentionally omitted: la.wikisource has no full
    # transcription (it's fragmentary in the manuscript tradition).
    # English coverage still comes via PG 14970 + PG 29247.
    ("de_finibus_lat.txt", "De finibus bonorum et malorum"),
    ("de_natura_deorum_lat.txt", "De natura deorum"),
    ("tusculans_lat.txt", "Tusculanae disputationes"),
    ("de_officiis_lat.txt", "De officiis"),
    ("de_amicitia_lat.txt", "Laelius de Amicitia"),
    ("de_senectute_lat.txt", "Cato maior de senectute"),
    ("de_divinatione_lat.txt", "De divinatione"),
    ("de_fato_lat.txt", "De fato (Marcus Tullius Cicero)"),
    ("topica_lat.txt", "Topica (Marcus Tullius Cicero)"),
)


def _rest_url(title: str) -> str:
    return (
        "https://la.wikisource.org/api/rest_v1/page/html/"
        + quote(title, safe="")
    )


_fetch = make_fetcher()

# Wikisource apparatus classes / structural tags to drop. Same sets
# the other Wikisource scrapers use (see `download_pascal_fr.py`),
# plus `title` — the REST endpoint returns a full document, and its
# `<head><title>` would otherwise surface as a leading paragraph.
_SKIP_TAGS = frozenset({"script", "style", "table", "sup", "noscript", "title"})
_BREAK_END_TAGS = frozenset({"p", "li", "div"})
_SKIP_CLASS_TOKENS = frozenset(
    {"mw-references", "headertemplate", "ws-noexport", "navbox", "metadata"}
)

# Parsoid renders internal links as `href="./Page_title"`. Sub-pages of
# a work are exactly those whose title starts with `<work>/`.
_HREF_RE = re.compile(r'href="\./([^"#?]+)', re.IGNORECASE)

# la.wikisource opens each work page with a breadcrumb paragraph whose
# lines are prefixed `<` (`< Marcus Tullius Cicero / < Opera
# philosophica`). It carries no work text — drop it wherever it appears.
_BREADCRUMB_RE = re.compile(r"^<\s")

# Bare Roman-numeral chapter markers ("I", "XVIII") that la.wikisource
# renders as standalone paragraphs inside each Liber.
_ROMAN_ONLY_RE = re.compile(r"^[IVXLC]+$")


def _extract_paragraphs(html: bytes) -> list[str]:
    p = ParagraphExtractor(
        skip_tags=_SKIP_TAGS,
        break_end_tags=_BREAK_END_TAGS,
        skip_class_tokens=_SKIP_CLASS_TOKENS,
    )
    p.feed(html.decode("utf-8"))
    p.close()
    return [q for q in p.paragraphs if not _BREADCRUMB_RE.match(q)]


def _subpage_titles(html: bytes, title: str) -> list[str]:
    """Return sub-page titles (`De officiis/Liber primus`, …) linked
    from a work's top-level page, in document order and de-duplicated.

    Titles are compared on the underscore form Parsoid emits and
    returned in that form — `_rest_url` re-quotes them, and
    Wikisource treats spaces and underscores as equivalent.
    """

    prefix = title.replace(" ", "_") + "/"
    out: list[str] = []
    seen: set[str] = set()
    for href in _HREF_RE.findall(html.decode("utf-8")):
        sub = unquote(href)
        if not sub.startswith(prefix) or sub in seen:
            continue
        seen.add(sub)
        out.append(sub)
    return out


def fetch_work(title: str, *, dest: Path, delay: float = 1.5) -> Path | None:
    """Fetch one work from la.wikisource and write it as plain text.

    The on-disk shape — matched against the files this script already
    produced in `data/cicero/raw_la/` — is the top-level page's own
    paragraphs (the `M. TVLLI CICERONIS …` title and its table of
    contents) followed, for each `<work>/<subpage>` link, by that
    sub-page's title on its own line and then its body. Works whose
    whole text sits on the top-level page (e.g. De fato) simply have
    no sub-pages to append.

    Sub-page bodies are stripped of bare Roman-numeral section
    markers. They duplicate the `[N]` numbering the text already
    carries, and the committed files omit them — keeping them would
    churn every downstream chunk_id on the next ingest.

    Returns the written path, or None when nothing could be extracted
    (caller logs the skip; one dead work must not kill the batch).
    """

    root_html = _fetch(_rest_url(title))
    subpages = _subpage_titles(root_html, title)

    paragraphs: list[str] = _extract_paragraphs(root_html)
    for sub in subpages:
        label = unquote(sub).replace("_", " ")
        print(f"  - {label}")
        try:
            body = _extract_paragraphs(_fetch(_rest_url(sub)))
        except Exception as e:  # one bad Liber shouldn't lose the work
            print(f"    [subpage skipped] {type(e).__name__}: {e}")
            continue
        paragraphs.append(label)
        paragraphs.extend(p for p in body if not _ROMAN_ONLY_RE.match(p))
        time.sleep(delay)

    if not paragraphs:
        print("  no text extracted")
        return None

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n\n".join(paragraphs).strip() + "\n", encoding="utf-8")
    print(f"  → {dest} ({len(paragraphs)} paragraphs, {dest.stat().st_size:,} bytes)")
    return dest


def main() -> None:
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
        help="Seconds to sleep between requests (be polite to la.wikisource).",
    )
    ap.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Subset filename allowlist (e.g. --only de_officiis_lat.txt).",
    )
    args = ap.parse_args()
    out_dir = args.data_root / "cicero" / "raw_la"
    only = set(args.only) if args.only else None
    for filename, title in _WORKS:
        if only and filename not in only:
            continue
        print(f"\n=== {filename}: {title} ===")
        try:
            fetch_work(title, dest=out_dir / filename, delay=args.delay)
        except urllib.error.HTTPError as e:
            print(f"  [WORK SKIPPED] {filename} ({title}): HTTP {e.code}")
        except Exception as e:
            print(f"  [WORK SKIPPED] {filename}: {type(e).__name__}: {e}")
        time.sleep(args.delay)


if __name__ == "__main__":
    main()
