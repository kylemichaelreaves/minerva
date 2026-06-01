#!/usr/bin/env python3
"""Download three Marx works from de.wikisource.org.

de.wikisource hosts clean transcriptions of three Marx works as
single-page `Texte_entier`-style endpoints:

  • Manifest der Kommunistischen Partei (1848)
  • Thesen über Feuerbach (1845)
  • Zur Kritik der Hegel'schen Rechtsphilosophie. Einleitung (1844)

Same Wikisource HTML chrome conventions as fr.wikisource — the
class-aware `_ParagraphExtractor` from `download_rousseau_fr.py`
applies verbatim. We import it directly rather than copy/pasting.

Output: `data/marx/raw_deu/{manifest,thesen_feuerbach,kritik_hegel_rechtsphil_einl}.txt`

Run:

    uv run python perseus/download_marx_wikisource.py
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from urllib.parse import quote

# Reuse the Rousseau scraper's `_fetch`, `_extract_paragraphs`,
# and `_ParagraphExtractor` — same Wikisource HTML chrome applies
# to de.wikisource as fr.wikisource (mw-references, headertemplate,
# ws-noexport are MediaWiki-wide classes).
from download_rousseau_fr import _extract_paragraphs, _fetch  # type: ignore[import-not-found]

_WORKS: tuple[dict, ...] = (
    {
        "filename": "manifest.txt",
        "display": "Manifest der Kommunistischen Partei (1848)",
        "title": "Manifest der Kommunistischen Partei (1848)",
    },
    {
        "filename": "thesen_feuerbach.txt",
        "display": "Thesen über Feuerbach (1845)",
        "title": "Thesen über Feuerbach",
    },
    {
        "filename": "kritik_hegel_rechtsphil_einl.txt",
        "display": "Zur Kritik der Hegel'schen Rechtsphilosophie. Einleitung (1844)",
        # The Wikisource canonical title uses the curly right
        # single-quote (U+2019), not a straight apostrophe.
        "title": "Zur Kritik der Hegel’schen Rechtsphilosophie",
    },
)


def _url(title: str) -> str:
    return (
        "https://de.wikisource.org/api/rest_v1/page/html/"
        + quote(title, safe="")
    )


def fetch_all(*, dest_root: Path) -> list[Path]:
    """Walk the work specs and fetch each single-page Wikisource
    transcription. Drops paragraphs under 30 chars to filter nav-
    chrome bleed."""

    dest_dir = dest_root / "marx" / "raw_deu"
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for spec in _WORKS:
        url = _url(spec["title"])
        print(f"\n{spec['display']} → {spec['filename']}")
        print(f"  GET {url}")
        raw = _fetch(url)
        paragraphs = _extract_paragraphs(raw)
        body = [p for p in paragraphs if len(p) >= 30]
        print(f"  {len(body)} paragraphs (from {len(paragraphs)} extracted)")
        rendered = "\n\n".join(body).strip() + "\n"
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
        help="Top of the data tree; files land in <root>/marx/raw_deu/.",
    )
    args = parser.parse_args()
    fetch_all(dest_root=args.data_root)
    print("\nNext: run download_marx_pgde.py + download_marx_archive.py, then ingest.")


if __name__ == "__main__":
    main()
