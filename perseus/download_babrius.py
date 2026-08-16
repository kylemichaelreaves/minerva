#!/usr/bin/env python3
"""Source Babrius (Greek verse Aesop) — First1KGreek + Davies 1860.

**Corrected 2026-08-15.** This script used to say Babrius was "a known
gap — no TLG 1670 file in PerseusDL/canonical-greekLit, First1KGreek,
Diorisis, or Scaife CTS catalogs as of 2026-06-01 probes", and fell back
to archive.org OCR of Crusius's critical edition for the Greek. The
probes were real; the conclusion was not. **Babrius is tlg0614, not
tlg1670** — under the number probed, both repos genuinely 404, and under
the right one First1KGreek has carried a hand-encoded EpiDoc TEI text
all along.

What the error cost: Crusius prints his apparatus criticus beneath each
fable, the OCR could not tell it from verse, and the heuristic filter
below let most of it through. 498 chunks and 501,783 characters were
indexed as Babrius; the Greek text itself is about 72,000 (#398).

* **Greek**: First1KGreek ``tlg0614.tlg001.1st1K-grc1`` — Schneidewin's
  *Fabulae Aesopeae*, EpiDoc TEI P5, Harvard/Leipzig encoded, no
  apparatus in the text stream. 147 ``<div subtype="section">`` fables.
  Licence: CC-BY-SA-4.0 per First1KGreek's standard header.
* **English**: J. Davies 1860 *The Fables of Babrius* (archive.org
  ``bib_fict_4103078``); First1KGreek carries no translation. **Not**
  in a ``FABLE I.`` / ``FABLE II.`` header format, as this docstring
  used to claim — the string ``FABLE <roman>`` occurs exactly twice in
  the whole scan. Fable boundaries are the Perry-index lines under each
  title, which is why ``_PERRY_REF`` matters so much (#399).

Output:

    data/aesop/babrius_grc.xml       # First1KGreek TEI P5, parsed by tei_p5
    data/aesop/babrius_eng.txt       # Davies's verse translations

The Greek is parsed by ``sources.tei_p5.parse_dir`` (the same path as
the Phaedrus half of this corpus); the English still goes through the
``corpus``-label ``.txt`` pipeline. ``--keep-crusius`` re-fetches the old
OCR to ``babrius_grc_crusius.txt`` for comparison; nothing ingests it.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _download import fetch_with_retry

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "aesop"

# First1KGreek tlg0614 = Babrius. NOT tlg1670, which is what the
# 2026-06-01 probes searched and is why this fetched OCR for two months.
GREEK_TEI_URL = (
    "https://raw.githubusercontent.com/OpenGreekAndLatin/First1KGreek/master/"
    "data/tlg0614/tlg001/tlg0614.tlg001.1st1K-grc1.xml"
)
# Retained for `--keep-crusius` only; not ingested.
CRUSIUS_OCR_URL = (
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
# Perry / Babrian cross-reference, printed under every fable's title:
# "(P. F. 403.)". These lines ARE the fable boundaries, so a variant this
# pattern misses is a fable the corpus loses silently.
#
# The scan damages roughly half of them, and the previous pattern —
# `[\(\{][PpVvy]\.?\s*[Ff][.,]` — required the P-token to be one letter
# followed by at most one dot, and the F to be followed by a dot or
# comma. Measured against the raw text, that matched 81 of 142; the 61 it
# dropped are all real, just mangled: `(Pp. F. 28.)` (P read twice),
# `(P..F. 26.)` (doubled dot), `(Pp. ‘F. 10.)` (stray quote), `(p. F.
# 237+)` (terminal `.` read as `+`), `(P.. F174.)` (space eaten). So the
# separators are now "a short run of non-alphanumerics" rather than an
# enumerated set (#399).
#
# What still bounds it, and what keeps `(P. 63.)` and `(See Plat. Phaedr.
# p. 203.)` out: the line must be bracketed, start with a P/V-ish token,
# carry an F before the digits, and contain nothing else.
_PERRY_REF = re.compile(
    r"^\s*[\(\{\[]\s*"  # opening bracket
    r"[PpVvy]{1,2}"  # P, Pp, vp — the OCR's readings of "P"
    r"[^A-Za-z0-9\n]{0,4}\s*"  # ". ", "..", ". ‘"
    r"[Ff]"  # the "F" of "P. F."
    r"[^0-9\n]{0,4}"  # ". ", ", ", "" (F174)
    r"(?P<perry>\d{1,3})"  # Davies's Perry-index number
    r"[^0-9\n]{0,4}"  # ".", "+", ".,"
    r"[\)\}\]]\s*$"  # closing bracket
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

    # End of the fables. "NOTES TO" is the one that actually fires on
    # this scan — `INDEX TO`, `FINIS` and `PRINTED BY` occur nowhere in
    # it, so `end` stayed at `len(lines)` and Davies's 14,891-character
    # commentary was swallowed into the last fable (#399). The others are
    # kept: they cost nothing and other printings use them.
    end = len(lines)
    for i in range(start, len(lines)):
        s = lines[i].strip()
        if "NOTES TO" in s or "INDEX TO" in s or "FINIS" in s or "PRINTED BY" in s:
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
    ap = argparse.ArgumentParser(description="Source Babrius (Greek + English).")
    ap.add_argument(
        "--keep-crusius",
        action="store_true",
        help=(
            "Also fetch the superseded Crusius archive.org OCR to "
            "babrius_grc_crusius.txt for comparison. Not ingested."
        ),
    )
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching First1KGreek tlg0614 (Schneidewin, TEI P5) ...", file=sys.stderr)
    greek_tei = _fetch(GREEK_TEI_URL)
    greek_out = OUT_DIR / "babrius_grc.xml"
    greek_out.write_text(greek_tei, encoding="utf-8")
    n_sections = greek_tei.count('subtype="section"')
    print(
        f"  → {greek_out} ({len(greek_tei):,} chars; {n_sections} sections)",
        file=sys.stderr,
    )
    stale = OUT_DIR / "babrius_grc.txt"
    if stale.exists():
        stale.unlink()
        print(f"  removed superseded {stale.name}", file=sys.stderr)

    if args.keep_crusius:
        print("Fetching superseded Crusius OCR (comparison only) ...", file=sys.stderr)
        crusius = _extract_greek(_fetch(CRUSIUS_OCR_URL))
        (OUT_DIR / "babrius_grc_crusius.txt").write_text(crusius, encoding="utf-8")
        print(f"  → babrius_grc_crusius.txt ({len(crusius):,} chars)", file=sys.stderr)

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
        "\nDone. The Greek needs no apparatus filtering — First1KGreek's\n"
        "text stream carries none. The English recovers 131 fables from the\n"
        "Perry-reference lines; ~12 of Babrius's ~143 carry no usable ref in\n"
        "this scan and are still missing (#399).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
