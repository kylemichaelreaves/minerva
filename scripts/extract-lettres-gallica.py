#!/usr/bin/env python3
"""Extract Boulainvilliers's *Lettres sur les anciens parlemens de
France* from the Gallica "Text View" HTML exports (3 volumes).

The user downloaded Gallica's per-tome HTML pages — these embed the
OCR text directly in the page body (not just viewer chrome). Each
tome's HTML contains a metadata header followed by the full OCR'd
prose. We:

1. Walk each volume in order (Tome 1 → 2 → 3).
2. Strip Gallica's metadata header (the "Reminder of your request:
   Downloading format..." preamble down to the start of body OCR).
3. Inject a ``CHAPTER N`` heading per tome so the chapter splitter
   can produce a volume-level chunk grouping. (Within each volume,
   the chapter splitter will further sub-split on the existing
   ``PREMIERE LETTRE.`` / ``SECONDE LETTRE.`` etc. markers if
   Gallica's OCR preserves them.)
4. Apply the same long-s + ligature + dictionary-guided f→s cleanup
   the other Boulainvilliers files use, via the existing
   ``clean-boulainvilliers-texts`` helpers (imported).

Output: replaces ``data/boulainvilliers/lettres_parlemens_fra.txt``
with the Gallica-sourced version. The archive.org source we used
earlier is discarded — its OCR was unrecoverable.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

# Make the cleanup helpers importable as a sibling module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module
_mod = import_module("clean-boulainvilliers-texts")
clean_text = _mod.clean_text

DOWNLOADS = Path.home() / "Downloads"
OUT = Path(__file__).resolve().parent.parent / "data" / "boulainvilliers" / "lettres_parlemens_fra.txt"

# Match each tome's HTML filename. Gallica's filename pattern is
# "Lettres sur ... Tome N _ Gallica.html".
TOME_GLOB = "Lettres sur les anciens parlements*Tome*_ Gallica.html"


def _extract_body_text(html_path: Path) -> str:
    """Parse the HTML and return everything inside <body>, stripped
    of Gallica's metadata header (the bibliographic preamble that
    runs from "Reminder of your request" through the rights /
    identifier block).

    Gallica's "Text View" HTML wraps each OCR word in a ``<span>``,
    so a naïve ``get_text("\\n", strip=True)`` produces one token
    per line. We walk block-level elements (``<p>``, ``<div>``,
    ``<br>``, etc.) explicitly: spaces between inline children,
    blank lines between blocks. That preserves paragraph structure
    without splitting prose at every span boundary.
    """

    with html_path.open("r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
    for el in soup.find_all(["script", "style", "nav", "header", "footer"]):
        el.decompose()
    body = soup.find("body")
    if body is None:
        return ""
    # Replace <br> with explicit line breaks so they survive
    # get_text's whitespace collapse below.
    for br in body.find_all("br"):
        br.replace_with("\n")
    # Walk paragraph-like blocks; concatenate with a blank line
    # between each. If the body has no <p> blocks (Gallica's
    # bibliographic header is sometimes raw text), fall back to
    # space-joined get_text.
    paras = body.find_all("p")
    if paras:
        text = "\n\n".join(
            re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
            for p in paras
        )
    else:
        text = re.sub(r"\s+", " ", body.get_text(" ", strip=True)).strip()

    # Drop the metadata preamble. Gallica's "Text View" download
    # prepends a bibliographic header that's not part of the work.
    # The body text proper begins at the first paragraph of the
    # preface ("LETTRES SUR LES ANCIENS PARLEMENS") OR at the
    # "PREMIERE LETTRE." marker, whichever comes first.
    for marker in ("PREMIERE LETTRE", "PREMIÈRE LETTRE", "LETTRE PREMIERE"):
        idx = text.find(marker)
        if idx > 0:
            text = text[idx:]
            break
    else:
        # No letter-marker found — keep everything past the
        # "Online date" / "Provenance" Gallica metadata block.
        for trim_marker in ("Provenance :", "Online date :"):
            idx = text.find(trim_marker)
            if idx > 0:
                # Skip past this entire line.
                nl = text.find("\n", idx)
                if nl > 0:
                    text = text[nl + 1:]
                break
    return text


def main() -> int:
    tomes = sorted(DOWNLOADS.glob(TOME_GLOB))
    if not tomes:
        print(f"No Lettres HTML files in {DOWNLOADS}", file=sys.stderr)
        return 1
    print(f"Found {len(tomes)} tome HTML files:", file=sys.stderr)
    for t in tomes:
        print(f"  {t.name}", file=sys.stderr)

    parts: list[str] = []
    for tome_path in tomes:
        # Tome number from the filename.
        m = re.search(r"Tome (\d+)", tome_path.name)
        n = m.group(1) if m else "?"
        print(f"  extracting Tome {n} ...", file=sys.stderr)
        body = _extract_body_text(tome_path)
        print(f"    body text: {len(body):,} chars", file=sys.stderr)
        # Tome marker for the chapter splitter (ALL-CAPS so the
        # secondary regex branch catches it).
        parts.append(f"\n\nTOME {n}\n\n")
        parts.append(body)

    raw = "\n\n".join(parts)
    print(f"  combined raw: {len(raw):,} chars", file=sys.stderr)

    cleaned = clean_text(raw)
    print(f"  after cleanup: {len(cleaned):,} chars", file=sys.stderr)

    OUT.write_text(cleaned, encoding="utf-8")
    print(f"Wrote {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
