#!/usr/bin/env python3
"""Strip Wikisource + Project Gutenberg chrome from Cicero files.

The 2026-05-30 corpus quality audit flagged 160 duplicate chunks
in Cicero — all of them site chrome:

* **Latin files (raw_la/\\*.txt)** — Wikisource source. Headers:

      <Title> (Marcus Tullius Cicero)

      < Marcus Tullius Cicero < Opera philosophica (Marcus Tullius Cicero)

  These three lines (title, blank, breadcrumb) repeat per file
  and chunk as the audit's top dup ("7 copies" of the breadcrumb).

* **English files (raw_eng/\\*.txt)** — Project Gutenberg source.
  Standard preamble (header lines 1-22ish ending with "*** START
  OF THE PROJECT GUTENBERG EBOOK ..." marker) and a long postamble
  (starting at "*** END OF THE PROJECT GUTENBERG EBOOK ..."
  through end-of-file with the full PG license + foundation text).

We deliberately leave alone:

* The 186 long_s_misread chunks (false positives — Yonge's clean
  19th-c English Bohn translation doesn't have actual long-s issues
  but trips the audit's f/s-density heuristic).
* The 38 caret_artifact chunks (legitimate scholarly sigla:
  ``A^2`` = "Codex A, second reading", ``Vahlen^2`` = Vahlen ed. 2).
* The 52 glyph_soup chunks (legitimate Loeb-style critical-apparatus
  footnotes with ``§§``, ``_Ad Fam._`` etc.).
* The 48 mostly_digits chunks (legitimate footnote citations).

Idempotent.

Role: oneoff
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CICERO_DIR = REPO_ROOT / "data" / "cicero"

_PG_START = re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK")
_PG_END = re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK")

# Wikisource Latin-file header lines.
_WS_BREADCRUMB = re.compile(r"^<\s*Marcus Tullius Cicero\s*<\s*Opera")
_WS_TITLE = re.compile(r"^[A-Za-zÆŒæœ\s]+\(Marcus Tullius Cicero\)\s*$")


def _strip_gutenberg(text: str) -> tuple[str, int]:
    """Drop PG preamble and postamble. Returns (cleaned, lines_dropped)."""

    lines = text.splitlines()
    n = len(lines)
    # Find START marker
    start = 0
    for i, line in enumerate(lines):
        if _PG_START.search(line):
            start = i + 1  # skip the marker itself
            # Skip any blank lines right after the marker
            while start < n and not lines[start].strip():
                start += 1
            break
    # Find END marker
    end = n
    for i, line in enumerate(lines):
        if _PG_END.search(line):
            end = i
            break
    if start == 0 and end == n:
        return text, 0  # not a PG file
    dropped = start + (n - end)
    return "\n".join(lines[start:end]), dropped


def _strip_wikisource(text: str) -> tuple[str, int]:
    """Drop Wikisource Latin-file breadcrumb header. Returns (cleaned, dropped)."""

    lines = text.splitlines()
    out: list[str] = []
    dropped = 0
    # Strip only the first few lines if they match the chrome shape.
    # Body content (starting "M. TVLLI ..." or "[1] ...") survives.
    in_header = True
    for line in lines:
        stripped = line.strip()
        if in_header:
            if not stripped:
                # Blank line; keep skipping if we're still in chrome territory.
                continue
            if _WS_BREADCRUMB.match(stripped) or _WS_TITLE.match(stripped):
                dropped += 1
                continue
            # Hit first non-chrome non-blank line — end of header window.
            in_header = False
        out.append(line)
    return "\n".join(out), dropped


def main() -> int:
    eng_dir = CICERO_DIR / "raw_eng"
    lat_dir = CICERO_DIR / "raw_la"
    if not (eng_dir.is_dir() and lat_dir.is_dir()):
        print(f"Cicero raw_eng / raw_la dirs not found under {CICERO_DIR}", file=sys.stderr)
        return 1
    total_pg = 0
    total_ws = 0
    for path in sorted(eng_dir.glob("*.txt")):
        raw = path.read_text(encoding="utf-8")
        cleaned, dropped = _strip_gutenberg(raw)
        if dropped:
            path.write_text(cleaned, encoding="utf-8")
            total_pg += dropped
            print(
                f"  {path.name}: -{dropped} PG chrome lines "
                f"({len(raw):,} → {len(cleaned):,} chars)",
                file=sys.stderr,
            )
        else:
            print(f"  {path.name}: clean (no PG markers)", file=sys.stderr)
    for path in sorted(lat_dir.glob("*.txt")):
        raw = path.read_text(encoding="utf-8")
        cleaned, dropped = _strip_wikisource(raw)
        if dropped:
            path.write_text(cleaned, encoding="utf-8")
            total_ws += dropped
            print(
                f"  {path.name}: -{dropped} Wikisource chrome lines "
                f"({len(raw):,} → {len(cleaned):,} chars)",
                file=sys.stderr,
            )
        else:
            print(f"  {path.name}: clean (no Wikisource breadcrumb)", file=sys.stderr)
    print(
        f"\nStripped {total_pg} PG chrome lines + {total_ws} Wikisource chrome lines.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
