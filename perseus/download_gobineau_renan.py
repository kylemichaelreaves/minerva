#!/usr/bin/env python3
"""Download Gobineau's *Essai sur l'inégalité des races humaines*
and Renan's *Vie de Jésus*, *L'Antéchrist*, and *Histoire du peuple
d'Israël* from archive.org.

Source manifest (verified 2026-05-29):

  Gobineau Essai vols 1-4 — Google Books scan of the 1853 first
  edition. Re-typeset OCR, clean by 18th-c standards. Identifiers:
    essaisurlingali01gobigoog .. essaisurlingali04gobigoog

  Renan Vie de Jésus (1863) — University of Toronto scan. Clean OCR
  (no long-s preserved). Identifier: viedejsus00renauoft

  Renan L'Antéchrist (1877) — = vol 4 of Histoire des origines du
  christianisme. Identifier: histoiredesorigi04renauoft

  Renan Histoire du peuple d'Israël vols 1-5 — 1887/1889/1893 first
  editions. Identifiers: histoiredupeuple01rena .. histoiredupeuple05rena

The cleanup applies the same minimal pass as the Boulainvilliers
fetcher: drop Google Books boilerplate at the head, strip page
footers, collapse run-of-spaces, normalize blank lines. The chapter
splitter then catches ALL-CAPS heading anchors that come through
the OCR intact.

See ``add-gobineau-renan-plan`` memory for source manifest +
expected xref payoff.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from _download import fetch_with_retry

REPO_ROOT = Path(__file__).resolve().parent.parent

# Per-author data directories. The corpus-label parser walks each
# of these and dispatches by filename via `find_work`.
GOBINEAU_DIR = REPO_ROOT / "data" / "gobineau"
RENAN_DIR = REPO_ROOT / "data" / "renan"

# Conservative header drop — Google Books scans typically prepend
# ~30-80 lines of licence boilerplate + the cover image text. The
# chunker then handles whatever residual front-matter slips through.
HEADER_LINES = 60


def _archive_djvu(item: str) -> str:
    return f"https://archive.org/download/{item}/{item}_djvu.txt"


def _fetch(url: str) -> str:
    return fetch_with_retry(
        url,
        timeout=180,
        user_agent="minerva-ingest/1.0",
        encoding="utf-8",
    )


def _clean(raw: str) -> str:
    """Boilerplate strip + light whitespace normalization.

    Same shape as the Boulainvilliers fetcher's `_clean`. Idempotent —
    rerunning produces identical output for identical input.
    """

    lines = raw.splitlines()[HEADER_LINES:]
    text = "\n".join(lines)
    text = re.sub(r"(?i)\bDigitized by Google\b", "", text)
    text = re.sub(r"(?i)\bdby Google\b", "", text)
    # Collapse intra-line whitespace runs; preserve blank-line paragraphs.
    cleaned: list[str] = []
    for raw_line in text.split("\n"):
        cleaned.append(re.sub(r"[ \t]+", " ", raw_line).strip())
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _fetch_to(item: str, out_path: Path) -> None:
    url = _archive_djvu(item)
    print(f"  Fetching {url}", file=sys.stderr)
    raw = _fetch(url)
    cleaned = _clean(raw)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(cleaned, encoding="utf-8")
    print(
        f"    raw {len(raw):>9,} → cleaned {len(cleaned):>9,} chars  →  {out_path}",
        file=sys.stderr,
    )


# ──────────────────────────────────────────────────────────────────
# Source → output mapping
# ──────────────────────────────────────────────────────────────────

GOBINEAU_SOURCES: list[tuple[str, str]] = [
    (f"essaisurlingali0{v}gobigoog", f"essai_inegalite_vol{v}_fra.txt")
    for v in range(1, 5)
]

RENAN_SOURCES: list[tuple[str, str]] = [
    ("viedejsus00renauoft", "vie_de_jesus_fra.txt"),
    ("histoiredesorigi04renauoft", "antechrist_fra.txt"),
    *[
        (f"histoiredupeuple0{v}rena", f"peuple_israel_vol{v}_fra.txt")
        for v in range(1, 6)
    ],
]


def main() -> int:
    print("=== Gobineau ===", file=sys.stderr)
    for item, out in GOBINEAU_SOURCES:
        _fetch_to(item, GOBINEAU_DIR / out)
    print("=== Renan ===", file=sys.stderr)
    for item, out in RENAN_SOURCES:
        _fetch_to(item, RENAN_DIR / out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
