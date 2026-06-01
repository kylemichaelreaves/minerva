#!/usr/bin/env python3
"""Download Boulainvilliers's *Memoires Historiques sur l'ancien
Gouvernement de la France* + *Lettres sur les anciens parlemens de
France* — the Frankish-conquest / two-race thesis that Nietzsche later
reformulates as master/slave morality, plus the political-historical
follow-on in epistolary form.

Sources:

* **Histoire**: archive.org ``etatdelafranceda01boul`` (1727 first
  edition of *Etat de la France* — bundles the historical essays as
  its preface). Re-typeset OCR (no long-s, clean ligatures).
* **Lettres**: archive.org ``lettressurlesan00boulgoog`` (1753
  standalone first edition). Equally clean OCR with intact
  ``PREMIERE LETTRE.`` / ``SECONDE LETTRE.`` / ... section headings.

What this script ships:

* ``data/boulainvilliers/histoire_anc_gouv_fra.txt`` — the historical
  essays portion. The full 3.1 MB archive.org file is the entire
  Etat de la France; we drop the Google Books boilerplate header
  and the trailing administrative bulk (intendant reports per
  province) to keep the corpus focused on the philosophically-
  relevant material.
* ``data/boulainvilliers/lettres_parlemens_fra.txt`` — the fourteen
  letters from the 1753 standalone edition. The all-caps
  ``PREMIERE LETTRE.`` / ``SECONDE LETTRE.`` headings hit the
  chapter-splitter's secondary branch
  (``[A-Z][A-Z \\-—:,'.]{6,80}``) and produce per-letter chunks.

What this script does NOT ship:

* *Essai sur la noblesse de France* — the 1732 first edition was
  printed anonymously in a small run and isn't digitized on
  archive.org or (so far) on Gallica's open-API endpoints. Defer
  until a clean source surfaces.
* *Lettres sur les anciens parlemens* — English Dryden 1739
  translation. The only PD English of any Boulainvilliers work, but
  the archive.org OCR is rough (raw long-s, mangled letter headings).
  Defer until cleanup investment is warranted or a re-keyed source
  appears.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _download import fetch_with_retry

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "boulainvilliers"

def _archive_djvu(item: str) -> str:
    return f"https://archive.org/download/{item}/{item}_djvu.txt"


# Histoire — archive.org item + line range. The first ~150 lines are
# Google Books boilerplate + the cover/title page; the administrative
# bulk (intendant reports per province) starts after line ~14000.
# The Frankish-conquest material dominates lines ~150-14000.
HISTOIRE_ITEM = "etatdelafranceda01boul"
HISTOIRE_HEADER_LINES = 150
HISTOIRE_END = 14000

# Lettres — archive.org item; we use the whole file minus the Google
# Books boilerplate header. The 14 letters span both volumes (TOME
# PREMIER + TOME SECOND, joined in this djvu.txt at line ~9360).
LETTRES_ITEM = "lettressurlesan00boulgoog"
LETTRES_HEADER_LINES = 60


def _fetch(url: str) -> str:
    """Pull the raw djvu.txt from archive.org with a User-Agent set
    (default urllib UA gets occasionally rate-limited)."""

    return fetch_with_retry(
        url,
        timeout=120,
        user_agent="minerva-ingest/1.0",
        encoding="utf-8",
    )


def _clean(raw: str, *, start: int, end: int | None = None) -> str:
    """Drop Google Books boilerplate + trim to the configured line
    range. Light text-level cleanup (collapse run-of-spaces and
    repeated blank lines) so the chapter splitter sees a usable
    paragraph structure."""

    import re

    lines = raw.splitlines()
    body = lines[start:end] if end is not None else lines[start:]
    text = "\n".join(body)
    # Drop recurring page footers that punctuate the OCR.
    text = re.sub(r"(?i)\bDigitized by Google\b", "", text)
    text = re.sub(r"(?i)\bdby Google\b", "", text)
    # Collapse runs of whitespace within lines (the OCR liberally
    # double-spaces for column alignment). Preserve paragraph blank
    # lines.
    cleaned: list[str] = []
    for raw_line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        cleaned.append(line)
    text = "\n".join(cleaned)
    # Collapse 3+ consecutive blank lines to 2 (paragraph separator).
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _fetch_and_clean(
    item: str,
    out_path: Path,
    *,
    start: int,
    end: int | None,
) -> None:
    url = _archive_djvu(item)
    print(f"Fetching {url} ...", file=sys.stderr)
    raw = _fetch(url)
    print(f"  raw size: {len(raw):,} chars", file=sys.stderr)
    cleaned = _clean(raw, start=start, end=end)
    print(f"  after cleanup: {len(cleaned):,} chars", file=sys.stderr)
    out_path.write_text(cleaned, encoding="utf-8")
    print(f"Wrote {out_path}", file=sys.stderr)


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    _fetch_and_clean(
        HISTOIRE_ITEM,
        DATA_DIR / "histoire_anc_gouv_fra.txt",
        start=HISTOIRE_HEADER_LINES,
        end=HISTOIRE_END,
    )
    _fetch_and_clean(
        LETTRES_ITEM,
        DATA_DIR / "lettres_parlemens_fra.txt",
        start=LETTRES_HEADER_LINES,
        end=None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
