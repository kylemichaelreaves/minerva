#!/usr/bin/env python3
"""Source the Theognidea — Greek (Welcker 1826) + English (Banks 1856).

After 2026-06-01 sourcing probes, no clean TEI / structured-text
source exists on the standard repos (PerseusDL/canonical-greekLit,
First1KGreek, Diorisis, Scaife CTS). The Edmonds Loeb 1931 the
original plan recommended is gated as borrowable on archive.org
(still in copyright until 2027). The best public-domain options
are:

* **Greek**: Welcker 1826 *Theognidis Reliquiae*
  (archive.org ``theognidisreliq00welcgoog``). Clean Greek OCR
  (proper polytonic characters with accents). HOWEVER Welcker
  reorders the elegies thematically; we recover canonical
  numbering from the marginal line annotations (185, 190, 195,
  ...) and resequence.

* **English**: J. Banks 1856 *The Works of Hesiod, Callimachus,
  and Theognis* (archive.org ``worksofhesiodca00hesi``). Complete
  prose translation. Page headers like ``MAXIMS OF THEOGNIS.
  13—26`` give canonical-line-range anchors.

OCR quality means both files arrive rough; this script does
best-effort extraction. Downstream consumers (and curators) should
expect hand-correction passes.

Output:

    data/theognis/theognidea_grc.txt       # canonical-resequenced Greek
    data/theognis/theognidea_eng.txt       # page-anchored English prose

Both are emitted as plain text (not XML/TEI) because the source
quality doesn't justify pretending we have structured markup.
``theognis_works.py`` will be wired to parse these plain-text
files via the same path used for OCR'd Marx/Boulainvilliers
texts.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from _download import fetch_with_retry

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "theognis"

GREEK_URL = (
    "https://archive.org/download/theognidisreliq00welcgoog/"
    "theognidisreliq00welcgoog_djvu.txt"
)
ENGLISH_URL = (
    "https://archive.org/download/worksofhesiodca00hesi/"
    "worksofhesiodca00hesi_djvu.txt"
)

UA = "minerva-corpus-fetch/1.0 (+personal research; PD-only sources)"


def _fetch(url: str) -> str:
    return fetch_with_retry(url, timeout=60, user_agent=UA, encoding="utf-8")


def _extract_english(raw: str) -> str:
    """Pull the Theognis section out of the Banks 1856 bundle.

    Strategy: start at "THEOGNIS THE MEGAREAN", end at the next
    work boundary (we look for "INDEX" / "FINIS" / END marker
    after that point). Within the section, drop OCR-detected
    page-header lines and footnote blocks.

    Footnote heuristic: lines starting with a digit + space
    followed by lowercase prose, or lines that are mostly Greek/
    Latin commentary (low English-letter ratio). Imperfect — some
    body sentences will leak footnote content. Hand-curation is
    the safety net.
    """

    lines = raw.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if "THEOGNIS THE MEGAREAN" in ln:
            start = i + 1
            break
    if start is None:
        raise RuntimeError("Banks 1856: Theognis section start not found")

    # The Theognis section runs through the end of the volume.
    # Banks orders Hesiod → Callimachus → Theognis. End markers
    # may include INDEX, FINIS, or copyright pages.
    end = len(lines)
    for i in range(start, len(lines)):
        if any(
            tok in lines[i]
            for tok in ("INDEX TO", "FINIS.", "PRINTED BY", "BOHN'S CLASSICAL")
        ):
            end = i
            break

    out_lines: list[str] = []
    for ln in lines[start:end]:
        s = ln.rstrip()
        stripped = s.strip()
        # Page headers (e.g. "218 MAXIMS OF THEOGNIS. 13—26,").
        # Replace with a section anchor only when we recovered the
        # canonical-line range; bare "[Page]" markers without a
        # range are useless noise downstream.
        if "MAXIMS OF THEOGNIS" in s:
            m2 = re.search(r"(\d+)\s*[—\-]\s*(\d+)", s)
            if m2:
                out_lines.append(f"\n[Lines {m2.group(1)}–{m2.group(2)}]\n")
            continue
        # Lines dominated by Greek characters are footnote
        # commentary (Banks's footnotes quote the Greek alongside
        # the English) — drop.
        if re.search(r"[α-ωΑ-Ω]{3,}", s):
            continue
        # Latin citation footnotes — common abbreviations of
        # ancient sources Banks cross-references.
        if re.match(
            r"\s+(Cf\.|Hor\.|Virg\.|Hom\.|Aristot\.|Plat\.|Pl\.|Sch\.) ",
            s,
        ):
            continue
        # OCR noise: lines too short to be substantive prose. Skip
        # everything < 8 chars unless it's a blank line (which the
        # downstream chunker uses for paragraph splits).
        if stripped and len(stripped) < 8:
            continue
        # Footnote-only lines: pure citation fragments like
        # "1076." or ", 1076." (Banks's line-number annotations).
        if re.fullmatch(r"[,\.;:]?\s*\d{1,4}[,\.;:]?\s*", stripped):
            continue
        # OCR-junk pure-punctuation lines.
        if stripped and not re.search(r"[A-Za-zα-ωΑ-Ω]", stripped):
            continue
        out_lines.append(s)

    # Collapse multi-blank runs.
    text = "\n".join(out_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# Welcker structures: after "ΘΕΟΓΝΙΔΟΣ" / "ΓΝΩΜΑΙ ΠΡΟΣ KFPNOYN"
# the body alternates between Greek verses and Latin/German
# commentary. Marginal canonical line numbers appear as bare
# integers at line-end on every ~5th verse (185, 190, 195, ...).
_LINE_NUM_TRAIL = re.compile(r"\b(\d{2,5})\s*\.?\s*$")
# Greek-character predicate — basic + extended (polytonic) blocks.
# Use \u escapes so a hand-typed accent range can't break re.compile.
_GREEK_VERSE_HINT = re.compile(
    r"[Ͱ-Ͽἀ-῿]"  # Greek + Greek Extended
)


def _extract_greek(raw: str) -> str:
    """Pull verses + canonical line numbers from Welcker.

    Output: lines in canonical order, each annotated with its
    canonical line range when known. Lines without recovered
    canonical positions are placed at end as ``[UNPOSITIONED]``.

    Heuristic — Welcker reorders thematically, but every marginal
    number anchors the verse it sits next to. We pair each Greek
    verse with the nearest preceding marginal number; verses
    accumulate between numbers (positions interpolated).
    """

    lines = raw.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if "ΘΕΟΓΝΙΔΟΣ" in ln:
            start = i
            break
    if start is None:
        raise RuntimeError("Welcker 1826: ΘΕΟΓΝΙΔΟΣ heading not found")

    # End: index/glossary section begins much later. Pick a large
    # window; OCR debris will be filtered out by Greek-density.
    end = min(start + 20_000, len(lines))

    verses: list[tuple[int | None, str]] = []  # (canonical_line, verse)
    last_marginal: int | None = None
    for ln in lines[start:end]:
        s = ln.rstrip()
        if not s:
            continue
        # Marginal canonical line number? End-of-line integer 2-4 digits.
        m = _LINE_NUM_TRAIL.search(s)
        trailing_num: int | None = None
        if m:
            n = int(m.group(1))
            if 1 <= n <= 1400:  # canonical range of the Theognidea
                trailing_num = n
                # Strip the marginal number off the verse.
                s = _LINE_NUM_TRAIL.sub("", s).rstrip()
        if not _GREEK_VERSE_HINT.search(s):
            if trailing_num is not None:
                last_marginal = trailing_num
            continue
        # OCR-noise short lines: ``κ᾿`` ``΄`` ``ᾳ 2`` etc. are
        # single-character or near-single fragments. The shortest
        # legitimate elegiac line in the Theognidea is ~25 chars.
        if len(s) < 12:
            if trailing_num is not None:
                last_marginal = trailing_num
            continue
        # Require ≥3 Greek characters — guards against Greek-letter
        # OCR fragments leaking through.
        greek_count = sum(1 for ch in s if _GREEK_VERSE_HINT.match(ch))
        if greek_count < 3:
            if trailing_num is not None:
                last_marginal = trailing_num
            continue
        if trailing_num is not None:
            verses.append((trailing_num, s))
            last_marginal = trailing_num
        else:
            verses.append((last_marginal, s))

    # Resequence by canonical position. Unpositioned (None) go at end.
    positioned = sorted(
        (v for v in verses if v[0] is not None), key=lambda kv: kv[0]
    )
    unpositioned = [v[1] for v in verses if v[0] is None]

    out_lines: list[str] = [
        "# Theognidea — reconstructed canonical sequence from Welcker 1826\n"
    ]
    last_block: int | None = None
    for canon, verse in positioned:
        block = (canon // 10) * 10
        if block != last_block:
            out_lines.append(f"\n[~lines {block}–{block+9}]")
            last_block = block
        out_lines.append(verse)
    if unpositioned:
        out_lines.append(
            "\n[UNPOSITIONED — Welcker context lost; needs hand-curation]"
        )
        out_lines.extend(unpositioned)

    return "\n".join(out_lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching Welcker 1826 Greek ...", file=sys.stderr)
    greek_raw = _fetch(GREEK_URL)
    greek_text = _extract_greek(greek_raw)
    greek_out = OUT_DIR / "theognidea_grc.txt"
    greek_out.write_text(greek_text, encoding="utf-8")
    print(
        f"  → {greek_out} ({len(greek_text):,} chars; "
        f"{greek_text.count(chr(10))} lines)",
        file=sys.stderr,
    )

    print("Fetching Banks 1856 English ...", file=sys.stderr)
    eng_raw = _fetch(ENGLISH_URL)
    eng_text = _extract_english(eng_raw)
    eng_out = OUT_DIR / "theognidea_eng.txt"
    eng_out.write_text(eng_text, encoding="utf-8")
    print(
        f"  → {eng_out} ({len(eng_text):,} chars; "
        f"{eng_text.count(chr(10))} lines)",
        file=sys.stderr,
    )
    print(
        "\nDone. Both files are first-cut OCR extractions — manual\n"
        "curation expected for the Greek (Welcker's thematic reorder)\n"
        "and OCR cleanup expected for both. See add-theognis-plan.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
