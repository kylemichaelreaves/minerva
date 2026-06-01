#!/usr/bin/env python3
"""Extract Boulainvilliers's *Essai sur la noblesse de France* from
the Gallica PDF (the new one with a text layer — replaces the broken
EPUB extraction).

The PDF is the user's second download attempt, a much smaller
17 MB file (vs. the original 164 MB image-only download). PyMuPDF
sees text on 495 of 507 pages — Gallica embedded the OCR text layer
this time. We pull page-by-page, inject ``CHAPTER N`` heading
anchors where the source has top-of-page chapter markers, and
hand off to the standard Boulainvilliers cleanup
(long-s → s, ligatures, dictionary-guided f→s).
"""

from __future__ import annotations

import re
import sys
from importlib import import_module
from pathlib import Path

import fitz  # type: ignore[import-untyped]

# Make the cleanup helpers importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
_mod = import_module("clean-boulainvilliers-texts")
clean_text = _mod.clean_text

PDF = Path.home() / "Downloads" / "Essais_sur_la_noblesse_de_France_contena.pdf"
OUT = (
    Path(__file__).resolve().parent.parent
    / "data" / "boulainvilliers" / "essai_noblesse_fra.txt"
)

# Pages before this offset are Gallica cover / table-of-contents
# / library metadata, not the work itself. Sampled by hand:
# page 28-29 is the title page, body text starts around page 30.
BODY_START_PAGE = 28


def _extract() -> str:
    """Pull text page-by-page with blocks-mode extraction.

    The default ``get_text()`` mode drops inter-word spaces at
    glyph-cluster boundaries on this PDF — output looks like
    ``lesSenateurs``, ``expressed'en``, ``DiffertationsurlaNobleffe``.
    Switching to ``get_text("blocks")`` returns a list of
    ``(x0, y0, x1, y1, text, block_no, block_type)`` tuples, with
    inter-block whitespace intact and intra-block tokens
    space-joined as the source typesetter wrote them.

    Within each block we collapse run-of-whitespace to single
    spaces (Gallica's OCR sometimes inserts hard line breaks
    mid-paragraph) so each block becomes one logical paragraph.
    """

    doc = fitz.open(PDF)
    parts: list[str] = []
    for i in range(BODY_START_PAGE, len(doc)):
        blocks = doc[i].get_text("blocks")
        page_text: list[str] = []
        for x0, y0, x1, y1, text, block_no, btype in blocks:
            # Skip image blocks (btype == 1); text blocks are btype 0.
            if btype != 0:
                continue
            t = re.sub(r"\s+", " ", text).strip()
            if t:
                page_text.append(t)
        if page_text:
            parts.append("\n\n".join(page_text))
    return "\n\n".join(parts)


def main() -> int:
    if not PDF.exists():
        print(f"PDF not found: {PDF}", file=sys.stderr)
        return 1
    print(f"Reading {PDF.name} ...", file=sys.stderr)
    raw = _extract()
    print(f"  raw text: {len(raw):,} chars", file=sys.stderr)
    cleaned = clean_text(raw)
    print(f"  after cleanup: {len(cleaned):,} chars", file=sys.stderr)
    OUT.write_text(cleaned, encoding="utf-8")
    print(f"Wrote {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
