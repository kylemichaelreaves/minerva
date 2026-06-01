#!/usr/bin/env python3
"""One-shot cleanup for the Gobineau source texts.

Gobineau's four-volume *Essai sur l'inégalité des races humaines*
was OCR'd from Google Books / Gallica scans of the 1853-1855
first edition. The 2026-05-30 corpus quality audit flagged **1,799
caret-artifact chunks**, **1,209 tiny chunks**, **23 duplicate
chunks**, plus glyph-soup and OCR-broken word-boundary debris.

The contamination family is the same as Boulainvilliers
(Gallica/Google French OCR), so we share the same pipeline:

1. **Unicode ligature decomposition** — ``ﬁ ﬂ ﬀ ﬃ ﬄ ﬅ`` → ``fi fl ff ffi ffl st``.
2. **Hyphenation join** across line breaks.
3. **Glyph-soup line drop** (predominantly non-letter character runs).
4. **Caret-artifact token strip** — drops tokens like
   ``Mezt^ ray``, ``Ckctrlema^ne``, ``T^yA`` that OCR mangled at
   page-rule intersections.
5. **Page-number-only line drop** — bare arabic / roman numerals.
6. **Running-header strip** — Gobineau-specific headers like
   "ESSAI SUR L'INÉGALITÉ", "TOME PREMIER", etc.
7. **Column-edge-garbage line drop**.

Gobineau is 19th-c so we SKIP the long-s f→s repair pass — the
audit shows only 2 long_s_misread chunks (essentially zero, vs.
Boulainvilliers' 497). Running the f→s pass on clean 19th-c
French would only invite false positives.

Idempotent.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GOBINEAU_DIR = REPO_ROOT / "data" / "gobineau"

# Import the Boulainvilliers pipeline. The file has a hyphen in
# its name so spec_from_file_location is the cleanest path; this
# avoids duplicating the 400-line OCR-cleanup logic. When a third
# French-OCR author lands we should promote this into
# scripts/lib/ocr_cleanup.py — for now, two callers justifies the
# shim approach.
_BV_PATH = REPO_ROOT / "scripts" / "clean-boulainvilliers-texts.py"
_spec = importlib.util.spec_from_file_location("_bv_clean", _BV_PATH)
assert _spec and _spec.loader, f"failed to load {_BV_PATH}"
_bv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bv)


import re  # noqa: E402  — after the spec_from_file_location dance

# Gobineau-specific running-header patterns. Replace the
# Boulainvilliers patterns since titles/structure differ.
_GOBINEAU_RUNNING_HEADERS = re.compile(
    r"^\s*(?:"
    # The cover/title-page reprise that appears at the top of every
    # volume's text view: "ESSAI", "SUR L'INÉGALITÉ", "DES RACES
    # HUMAINES". These are the audit's "tiny_chunk" entries
    # (``ESSAI``, ``SUR L'INÉGALITÉ``, ``DIS``).
    r"ESSAI\s*\.?"
    r"|SUR\s+L['’]IN[ÉE]GALIT[ÉE]\s*\.?"
    r"|DES\s+RACES\s+HUMAINES\s*\.?"
    r"|DIS\s*\.?"  # "DIS" (truncated "DES")
    # Volume / Tome markers
    r"|TOME\s+(?:[IVX]+|PREMIER|SECOND|TROISI[ÈE]ME|QUATRI[ÈE]ME|"
    r"DEUXIEME|DEUXI[ÈE]ME|QUATRIEME|QUATRIE?A?IE?\.?)"
    r"|TOME\s+QUATRI[ÈE]ME\.?"
    r"|TOME\s+QUATRI[ÈE]?AIE\.?"  # OCR variant "TOME QUATRIÈAIE."
    # Chapter / Book / Livre / Chapitre running heads
    r"|LIVRE\s+(?:[IVX]+|PREMIER|SECOND|TROISI[ÈE]ME|QUATRI[ÈE]ME)\s*\.?"
    r"|CHAPITRE\s+[IVX]+\s*\.?"
    # Standalone section markers
    r"|TABLE(?:\s+DES\s+MATI[ÈE]RES)?\s*\.?"
    r"|PR[ÉE]FACE\s*\.?"
    r"|INTRODUCTION\s*\.?"
    r"|AVERTISSEMENT\s*\.?"
    # Per-page running header that Gallica shows above each scan:
    # the chapter-summary phrase in small caps.
    r")\s*$",
    re.IGNORECASE,
)

# Monkey-patch the Boulainvilliers running-header regex with the
# Gobineau-specific one for the duration of this script's run.
_bv._RUNNING_HEADERS = _GOBINEAU_RUNNING_HEADERS


def main() -> int:
    if not GOBINEAU_DIR.is_dir():
        print(f"Gobineau directory not found: {GOBINEAU_DIR}", file=sys.stderr)
        return 1
    total_before = 0
    total_after = 0
    for path in sorted(GOBINEAU_DIR.glob("*.txt")):
        raw = path.read_text(encoding="utf-8")
        before = len(raw)
        # Skip the f→s pass: Gobineau is 19th-c and the audit
        # found only 2 long_s_misread chunks — running f→s on
        # clean 19th-c French is all downside (false-positive
        # risk, e.g. ``effet`` → ``esset`` would be wrong; the
        # dict-guarded pass should leave them alone, but skipping
        # it entirely is the safer + faster path here).
        text = _bv._normalize_ligatures(raw)
        text = _bv._join_hyphenation(text)
        text = _bv._strip_caret_artifacts(text)
        text = _bv._strip_inline_running_headers(text)
        text = _bv._split_run_on_words(text)
        out_lines: list[str] = []
        for line in text.split("\n"):
            line = _bv.MARGIN_NOISE.sub("", line)
            line = line.rstrip()
            if _bv._is_glyph_soup(line):
                continue
            if _bv._PAGE_NUMBER_LINE.match(line):
                continue
            if _bv._RUNNING_HEADERS.match(line):
                continue
            if _bv._is_column_edge_garbage(line):
                continue
            line = re.sub(r" {2,}", " ", line)
            out_lines.append(line)
        cleaned = "\n".join(out_lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        path.write_text(cleaned, encoding="utf-8")
        total_before += before
        total_after += len(cleaned)
        print(
            f"  {path.name}: {before:,} → {len(cleaned):,} chars "
            f"({(before - len(cleaned)) / before * 100:.1f}% reduction)",
            file=sys.stderr,
        )
    print(
        f"\nTotal: {total_before:,} → {total_after:,} chars "
        f"({(total_before - total_after) / total_before * 100:.1f}% reduction)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
