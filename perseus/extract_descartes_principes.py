#!/usr/bin/env python3
"""Re-extract Descartes *Principes* II-IV from Adam-Tannery Vol IX.

The existing ``data/descartes/raw_fr/principes_pars2to4.txt`` has
a fundamentally broken PDF extraction — marginal sidenotes are
interleaved with body text, the same passage repeats inside chunks,
and many tokens are unrecoverably mangled (``Coissisbi``, ``Mvoo``,
``ftroe`` for ``âme``). See [[corpus-quality-audit-lessons]] (the
Descartes ``principes_pars2to4`` row).

This script replaces the file with a clean re-extraction from the
authoritative Adam-Tannery OEuvres Vol IX (1904), which carries
the d'Albert / duc de Luynes 1647 French translation — the
canonical edition Descartes himself supervised.

* archive.org item: ``uvresdedescartes09desc``
* Section boundaries, found by heading rather than by line number (#499):
  - SECONDE PARTIE — the first one in the file starts our extract
    (PREMIERE PARTIE is already in `principes_pars1.txt`)
  - TABLE DES PRINCIPES — the first one after it ends the extract
  In the 2026-06-01 and 2026-10-06 OCR these sit at lines 15777 and 28781.

The OCR retains the 17th-c long-s rendered as ``f``:
``fubftance``, ``confifte``, ``fcauoir``. We apply the
Boulainvilliers dict-guided f→s pass to repair these in place.

Idempotent.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "data" / "descartes" / "raw_fr" / "principes_pars2to4.txt"

SOURCE_URL = "https://archive.org/download/uvresdedescartes09desc/uvresdedescartes09desc_djvu.txt"
UA = "minerva-corpus-fetch/1.0 (+personal research; PD source)"

# Boundary headings. archive.org regenerates OCR, so the extract is anchored
# on these rather than on line numbers, and a missing one raises (#499).
_PART_II_RE = re.compile(r"^\s*SECONDE\s+PARTIE\b")
_TABLE_RE = re.compile(r"^\s*TABLE\s+DES\s+PRINCIPES\b")

# Reuse the Boulainvilliers OCR-cleanup pipeline for the long-s
# repair + ligature decomposition + line normalization.
_BV_PATH = REPO_ROOT / "scripts" / "clean-boulainvilliers-texts.py"
_spec = importlib.util.spec_from_file_location("_bv_clean", _BV_PATH)
assert _spec and _spec.loader
_bv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bv)


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


# Adam-Tannery running heads and page artifacts.
_RUNNING_HEADS = re.compile(
    r"^\s*(?:"
    # Section names alone on a line
    r"LA\s+PHILOSOPHIE"
    r"|LES\s+PRINCIPES"
    r"|PRINCIPES"
    # Volume page-footer "Œuvres. IV. 41" → page-number citation
    r"|Œuvres\.\s+IV\.\s+\d+"
    r"|OEUVRES\s+DE\s+DESCARTES"
    r"|Œ?UVRES?\s+DE\s+Descartes\.?"
    # Bare page number
    r"|\d{1,4}"
    r")\s*\.?\s*$",
    re.IGNORECASE,
)

_PARTIE_HEADER = re.compile(
    r"^\s*(SECONDE|TROISIESME|TROISI[ÈE]ME|QUATRIESME|QUATRI[ÈE]ME)\s+PARTIE\.?\s*$",
    re.IGNORECASE,
)


def _first_match(lines: list[str], pattern: re.Pattern[str], start: int, name: str) -> int:
    for i in range(start, len(lines)):
        if pattern.match(lines[i]):
            return i
    raise RuntimeError(
        f"{name} heading not found in the Adam-Tannery OCR; archive.org may "
        f"have regenerated it. Re-probe {SOURCE_URL}"
    )


def _slice_parts(raw: str) -> str:
    """Parts II-IV: from the first SECONDE PARTIE up to the TABLE DES
    PRINCIPES that follows it (the table repeats the part headings)."""

    lines = raw.splitlines()
    start = _first_match(lines, _PART_II_RE, 0, "SECONDE PARTIE")
    end = _first_match(lines, _TABLE_RE, start + 1, "TABLE DES PRINCIPES")
    return "\n".join(lines[start:end])


def _extract(raw: str) -> str:
    """Pull Parts II-IV from the Adam-Tannery Vol IX OCR.

    The d'Albert translation is text-clean (proper French with 17th-c
    long-s OCR'd as ``f``); we run the dict-guided ``_fix_medial_f_to_s``
    pass + ligature normalize + running-head strip.
    """

    body = _slice_parts(raw)

    # Normalize ligatures + hyphenation join FIRST so the f→s pass
    # sees clean tokens.
    body = _bv._normalize_ligatures(body)
    body = _bv._join_hyphenation(body)
    # Strip caret-bearing tokens (scattered OCR debris like ``i^i``,
    # ``del^us``) — same ``\\S*\\^\\S*`` filter as Boulainvilliers.
    body = _bv._strip_caret_artifacts(body)
    # Long-s f→s repair (dictionary-guided; safe for legitimate
    # French f-words).
    body = _bv._fix_medial_f_to_s(body)

    out_lines: list[str] = []
    for line in body.split("\n"):
        s = line.strip()
        if not s:
            out_lines.append("")
            continue
        # Strip running heads + bare page numbers.
        if _RUNNING_HEADS.match(s):
            continue
        # Preserve PARTIE section headers as anchors.
        m = _PARTIE_HEADER.match(s)
        if m:
            out_lines.append(f"\n{m.group(1).upper()} PARTIE.\n")
            continue
        # OCR junk lines
        if _bv._is_glyph_soup(s):
            continue
        # Drop column-edge garbage
        if _bv._is_column_edge_garbage(s):
            continue
        out_lines.append(line.rstrip())

    text = "\n".join(out_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print("Fetching Adam-Tannery Vol IX ...", file=sys.stderr)
    raw = _fetch(SOURCE_URL)
    print(f"  raw OCR: {len(raw):,} chars", file=sys.stderr)
    clean = _extract(raw)
    OUT_PATH.write_text(clean, encoding="utf-8")
    print(
        f"  → {OUT_PATH} ({len(clean):,} chars, {clean.count(chr(10))} lines)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
