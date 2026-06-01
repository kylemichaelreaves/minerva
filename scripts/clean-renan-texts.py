#!/usr/bin/env python3
"""One-shot cleanup for Renan's source texts.

Renan's *Vie de Jésus*, *L'Antéchrist*, and the five-volume
*Histoire du peuple d'Israël* — seven files in all — were OCR'd
from Google Books / archive.org scans of the 1863-1893 editions.
The 2026-05-30 corpus quality audit flagged:

  * 397 caret_artifact chunks  (page-rule intersections)
  * 227 glyph_soup chunks      (column-edge debris)
  * 2 run_on_token chunks      (lost interword spaces)
  * 136 duplicate_text chunks  (front-matter title repeats across vols)

We share the Boulainvilliers OCR pipeline (same Gallica-family
artifacts). The **875 mostly_digits chunks** are intentionally
NOT touched — they're Renan's scholarly biblical-footnote
apparatus (``Ilebr., V, 4 1-14``, ``Apoc, XIX, 13``) which the
audit's digits-ratio gate flagged but is legitimate content.

Renan is 19th-c, so we skip the long-s f→s repair (the audit
shows 0 long_s_misread chunks in Renan — running f→s would only
invite false positives like ``effet`` → ``esset``).

Idempotent.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RENAN_DIR = REPO_ROOT / "data" / "renan"

_BV_PATH = REPO_ROOT / "scripts" / "clean-boulainvilliers-texts.py"
_spec = importlib.util.spec_from_file_location("_bv_clean", _BV_PATH)
assert _spec and _spec.loader, f"failed to load {_BV_PATH}"
_bv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bv)


import re  # noqa: E402

# Renan-specific running-header patterns. The Histoire is divided
# into TOMES + LIVRES + CHAPITRES; *Vie de Jésus* and *L'Antéchrist*
# add their own title-page reprises that recur as tiny chunks.
_RENAN_RUNNING_HEADERS = re.compile(
    r"^\s*(?:"
    # Title-page reprises
    r"VIE\s+DE\s+J[ÉE]SUS\s*\.?"
    r"|L['’]ANT[ÉE]CHRIST\s*\.?"
    r"|HISTOIRE\s+DU\s+PEUPLE\s+D['’]ISRA[ËE]L\s*\.?"
    r"|PAR(?:\s+ERNEST\s+RENAN)?\s*\.?"
    r"|PARIS\s*\.?"
    r"|CALMANN\s+L[ÉE]VY\s*\.?"
    # OCR-mangled version of title
    r"|I?L[\^]?\s*WTECHRIST\s*\.?"
    r"|ILANTECHRIST\)?"
    # Volume / Tome
    r"|TOME\s+(?:[IVX]+|PREMIER|SECOND|TROISI[ÈE]ME|QUATRI[ÈE]ME|"
    r"CINQUI[ÈE]ME|DEUXIEME|DEUXI[ÈE]ME)\s*\.?"
    # Livre + Chapitre
    r"|LIVRE\s+(?:[IVX]+|PREMIER|SECOND|TROISI[ÈE]ME|QUATRI[ÈE]ME|CINQUI[ÈE]ME)\s*\.?"
    r"|CHAPITRE\s+[IVX]+\s*\.?"
    # Section markers
    r"|TABLE(?:\s+DES\s+MATI[ÈE]RES)?\s*\.?"
    r"|PR[ÉE]FACE\s*\.?"
    r"|INTRODUCTION\s*\.?"
    r"|APPENDICE\s*\.?"
    r"|AVERTISSEMENT\s*\.?"
    r"|EPILOGUE\s*\.?"
    # Year stamps that float on title pages
    r"|18[0-9]{2}\s*\.?"
    r")\s*$",
    re.IGNORECASE,
)


# Same-file dedup pass for paragraph-level content duplication
# (some of Renan's volumes have a TOC + Table-des-Matières that
# repeats chapter titles verbatim). We use 60 chars min-len like
# Marx — anything shorter is plausibly legitimate (section
# heading repeated as both TOC and chapter open).
_DEDUP_MIN_LEN = 60


def main() -> int:
    if not RENAN_DIR.is_dir():
        print(f"Renan directory not found: {RENAN_DIR}", file=sys.stderr)
        return 1
    _bv._RUNNING_HEADERS = _RENAN_RUNNING_HEADERS
    total_before = 0
    total_after = 0
    total_dups = 0
    for path in sorted(RENAN_DIR.glob("*.txt")):
        raw = path.read_text(encoding="utf-8")
        before = len(raw)
        # Mirror the Gobineau pipeline (skip f→s for 19th-c text).
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
        # Same-file dedup pass.
        seen: set[str] = set()
        dedup_lines: list[str] = []
        dups = 0
        for line in out_lines:
            stripped = line.strip()
            if len(stripped) >= _DEDUP_MIN_LEN:
                if stripped in seen:
                    dups += 1
                    continue
                seen.add(stripped)
            dedup_lines.append(line)
        cleaned = "\n".join(dedup_lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        path.write_text(cleaned, encoding="utf-8")
        total_before += before
        total_after += len(cleaned)
        total_dups += dups
        print(
            f"  {path.name}: {before:,} → {len(cleaned):,} chars "
            f"(-{(before - len(cleaned)) / before * 100:.1f}%; -{dups} dup paras)",
            file=sys.stderr,
        )
    print(
        f"\nTotal: {total_before:,} → {total_after:,} chars "
        f"(-{(total_before - total_after) / total_before * 100:.1f}%; "
        f"-{total_dups} duplicate paragraphs)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
