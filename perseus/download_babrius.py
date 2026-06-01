#!/usr/bin/env python3
"""Source Babrius (Greek verse Aesop) — Crusius 1897 + Davies 1860.

Per [[add-aesop-plan]] memory, Phaedrus was sourced from
PerseusDL/canonical-latinLit on 2026-05-29 (already in corpus).
Babrius was a known gap — no TLG 1670 file in PerseusDL/canonical-
greekLit, First1KGreek, Diorisis, or Scaife CTS catalogs as of
2026-06-01 probes.

The remaining options were all archive.org OCR:

* **Greek**: Crusius 1897 *Babrii Fabulae Aesopeae* (the standard
  critical edition; archive.org ``babriifabvlaeaes00babruoft``).
  Clean polytonic Greek OCR. Critical apparatus is interleaved
  with verses (numbered notes referencing line numbers in each
  fable); we filter those out by detecting their characteristic
  shape.
* **English**: J. Davies 1860 *The Fables of Babrius* (archive.org
  ``bib_fict_4103078``). Complete English verse translation in
  the standard format (``FABLE I.`` / ``FABLE II.`` headers).
  Clean OCR.

The Crusius Greek text is organized as two collections (Part I
fables 1-122, Part II fables 123-143ish, plus fragments). Davies
also has two parts. Output preserves the fable numbers as anchors.

Output:

    data/aesop/babrius_grc.txt       # Greek verses by Crusius fable num
    data/aesop/babrius_eng.txt       # Davies's verse translations

Both are plain text. ``aesop_works.py`` will be wired to parse
them via the same path used for ``theognidea_*.txt``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from _download import fetch_with_retry

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "aesop"

GREEK_URL = (
    "https://archive.org/download/babriifabvlaeaes00babruoft/"
    "babriifabvlaeaes00babruoft_djvu.txt"
)
ENGLISH_URL = (
    "https://archive.org/download/bib_fict_4103078/"
    "bib_fict_4103078_djvu.txt"
)

UA = "minerva-corpus-fetch/1.0 (+personal research; PD-only sources)"


def _fetch(url: str) -> str:
    return fetch_with_retry(
        url, timeout=60, user_agent=UA, encoding="utf-8"
    )


# Greek character predicate. Use Unicode block ranges.
_GREEK_CHAR = re.compile(r"[Ͱ-Ͽἀ-῿]")
# Leading fable number — small integer at start of line, often as
# the only content or before a Greek verse.
_FABLE_NUM = re.compile(r"^\s*(\d{1,3})\s+([Ͱ-Ͽἀ-῿].*)$")
# Critical apparatus line: small numeric annotation + Latin
# critic's-note format (often starts with a number then a Greek
# variant followed by codex abbreviations or commentary in Latin).
_APPARATUS_HINT = re.compile(
    r"^\s*\d+(?:\s|\.)+.*"  # leading num
    r"(?: [A-Z]{1,2}(?:[a-z]+)?(?:\s|\|)|"  # codex sigla
    r" (?:corr|sup|m\.|s\.)\b|"  # corr., sup., m., s.
    r" Lm |"  # Lm
    r" Bgk\b)"  # Bekker
)


def _extract_greek(raw: str) -> str:
    """Pull Babrius fables from Crusius 1897, skipping critical apparatus."""

    lines = raw.splitlines()
    # Body starts at the first "ΒΑΒΡΙΟΥ" page header — preceded by
    # ~6700 lines of prolegomena.
    start = None
    for i, ln in enumerate(lines):
        if "ΒΑΒΡΙΟΥ" in ln and i > 4000:
            start = i
            break
    if start is None:
        raise RuntimeError("Crusius 1897: ΒΑΒΡΙΟΥ section not found")

    # End: indices begin near the end. Pick a generous window.
    end = min(start + 30_000, len(lines))

    out: list[str] = ["# Babrius — Crusius 1897 (archive.org babriifabvlaeaes00babruoft)\n"]
    current_fable: int | None = None
    fable_verses: list[str] = []

    def _flush():
        if current_fable is not None and fable_verses:
            out.append(f"\n[Fable {current_fable}]")
            out.extend(fable_verses)

    in_apparatus = False
    for ln in lines[start:end]:
        s = ln.rstrip()
        stripped = s.strip()
        if not stripped:
            in_apparatus = False
            continue
        # Page headers like "98 ΒΑΒΡΙΟΥ" or "MYTOIAMBOI 29".
        if re.match(r"^\s*\d{1,3}\s+ΒΑΒΡΙΟΥ\s*$", s) or re.match(
            r"^MYTOIAMBOI\s+\d+\s*$", stripped
        ):
            continue
        # New fable: leading 2-3 digit number followed by Greek capital.
        m = _FABLE_NUM.match(s)
        if m:
            n = int(m.group(1))
            verse = m.group(2).strip()
            # Heuristic: fable numbers run 1–~150; apparatus refs are usually
            # smaller numbers paired with codex sigla.
            greek_count = sum(1 for c in verse if _GREEK_CHAR.match(c))
            if 1 <= n <= 200 and greek_count >= 5:
                _flush()
                current_fable = n
                fable_verses = [verse]
                in_apparatus = False
                continue
        # Apparatus markers — high density of codex sigla / line refs.
        # Heuristic: line starts with "<num>" and contains "|" or codex
        # abbreviations.
        if _APPARATUS_HINT.match(s):
            in_apparatus = True
            continue
        # Drop apparatus continuation lines (Latin commentary; low
        # Greek-character density).
        greek_count = sum(1 for c in stripped if _GREEK_CHAR.match(c))
        total_alpha = sum(1 for c in stripped if c.isalpha())
        if total_alpha == 0:
            continue
        greek_ratio = greek_count / total_alpha
        if in_apparatus and greek_ratio < 0.5:
            continue
        if greek_ratio < 0.5:
            # Mostly-Latin lines (commentary)
            continue
        # Drop very short lines.
        if len(stripped) < 12:
            continue
        # Valid verse line.
        if current_fable is not None:
            fable_verses.append(s)

    _flush()
    text = "\n".join(out) + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# Davies 1860 fable header: "FABLE I." for #1, then all-caps title +
# Perry index ref "(P. F. nnn.)" for #2 onward. We use the Perry ref
# as the canonical fable boundary marker — it appears immediately
# below the title for every fable in the body.
_DAVIES_FABLE = re.compile(
    r"^\s*FABLE\s+([IVXLC]+)\.?\s*$", re.IGNORECASE
)
# Perry / Babrian cross-references appear in parens like "(P. F. 403.)"
# OCR sometimes renders parens as "( ", "(", "(p.", "(v.", etc.
_PERRY_REF = re.compile(
    r"^\s*[\(\{][PpVvy]\.?\s*[Ff][.,]\s*[\dvi\.,—\-]+[.,]?\s*[\)\}]\s*$"
)
# All-caps title line — Davies's fable titles. At least 3 letters,
# mostly uppercase, no terminal period (the title ends with "." but
# we need a flexible match).
_ALLCAPS_TITLE = re.compile(
    r"^\s*[A-Z][A-Z ’',\-]{3,}\.?\s*$"
)


def _extract_english(raw: str) -> str:
    """Pull Davies's verse fables from the 1860 edition.

    Strategy: find each Perry-ref line ``(P. F. nnn.)``; the line
    just before it (skipping blanks + page-headers) is the all-caps
    title. Body verse runs between Perry refs.
    """

    lines = raw.splitlines()
    # Body starts at FABLE I header after preface.
    start = None
    for i, ln in enumerate(lines):
        m = _DAVIES_FABLE.match(ln)
        if m and m.group(1).upper() == "I" and i > 1000:
            start = i
            break
    if start is None:
        raise RuntimeError("Davies 1860: 'FABLE I' header not found")

    end = len(lines)
    for i in range(start, len(lines)):
        s = lines[i].strip()
        if "INDEX TO" in s or "FINIS" in s or "PRINTED BY" in s:
            end = i
            break

    out: list[str] = [
        "# Babrius — Davies 1860 English verse (archive.org bib_fict_4103078)\n"
    ]
    current_fable = 0  # We renumber sequentially since titles vary.
    current_title: str | None = None
    fable_lines: list[str] = []

    def _flush():
        if current_fable > 0 and fable_lines:
            header = f"\n[Fable {current_fable}"
            if current_title:
                header += f": {current_title}"
            header += "]"
            out.append(header)
            out.extend(fable_lines)

    # Look-back window for title detection.
    recent_titles: list[str] = []

    for ln in lines[start:end]:
        s = ln.rstrip()
        stripped = s.strip()
        # Perry ref → new fable boundary.
        if _PERRY_REF.match(s):
            _flush()
            current_fable += 1
            # Title: pick the most recent all-caps line we saw.
            title = None
            for t in reversed(recent_titles):
                if _ALLCAPS_TITLE.match(t):
                    title = t.strip().rstrip(".")
                    break
            current_title = title
            recent_titles.clear()
            fable_lines = []
            continue
        # "FABLE I." line → skip (the immediately-following Perry
        # ref will create the fable). Used only to mark where body
        # begins; once we're past it, fable boundaries are Perry-ref
        # only.
        m = _DAVIES_FABLE.match(s)
        if m:
            recent_titles.clear()
            continue
        # Page headers / running heads.
        if stripped in (
            "The Fables of Babrius.",
            "FABLES OF BABRIUS.",
            "The fables of Babrius.",
            "Preface.",
        ):
            continue
        # Bare page numbers.
        if re.match(r"^\d+\s*$", stripped):
            continue
        # Section dividers: pure non-letter strings (lines of stars,
        # dots, dashes; OCR artifacts; lone Roman numerals).
        if stripped and not re.search(r"[A-Za-z]", stripped):
            continue
        # Track potential title lines in look-back window.
        if stripped:
            recent_titles.append(stripped)
            if len(recent_titles) > 6:
                recent_titles.pop(0)
        # OCR debris: short stripped fragment.
        if stripped and len(stripped) < 6:
            continue
        if current_fable > 0:
            fable_lines.append(s)

    _flush()
    text = "\n".join(out) + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching Crusius 1897 Greek ...", file=sys.stderr)
    greek_raw = _fetch(GREEK_URL)
    greek_text = _extract_greek(greek_raw)
    greek_out = OUT_DIR / "babrius_grc.txt"
    greek_out.write_text(greek_text, encoding="utf-8")
    n_fables_grc = greek_text.count("[Fable ")
    print(
        f"  → {greek_out} ({len(greek_text):,} chars; ~{n_fables_grc} fables)",
        file=sys.stderr,
    )

    print("Fetching Davies 1860 English ...", file=sys.stderr)
    eng_raw = _fetch(ENGLISH_URL)
    eng_text = _extract_english(eng_raw)
    eng_out = OUT_DIR / "babrius_eng.txt"
    eng_out.write_text(eng_text, encoding="utf-8")
    n_fables_eng = eng_text.count("[Fable ")
    print(
        f"  → {eng_out} ({len(eng_text):,} chars; ~{n_fables_eng} fables)",
        file=sys.stderr,
    )
    print(
        "\nDone. Crusius critical-apparatus filtering is heuristic;\n"
        "expect some bleed-through. Davies's English is the cleaner side.\n"
        "See add-aesop-plan memory.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
