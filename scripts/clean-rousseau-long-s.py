#!/usr/bin/env python3
"""Normalize literal long-s codepoints in Rousseau's *Premier Discours*.

The 2026-05-31 corpus quality audit flagged 11 chunks in Rousseau
containing U+017F (``ſ``) — the medial-s glyph that the 18th-c
printer used and that this particular OCR pass let through
without normalizing. All hits trace to a single file:
``data/rousseau/raw_fra/premier_discours.txt`` (143 ``ſ`` glyphs).

Fix is a one-pass Unicode ligature decomposition:

* ``ſ`` (U+017F) → ``s``
* ``ﬀ ﬁ ﬂ ﬃ ﬄ ﬅ ﬆ`` (U+FB00–FB06) → ``ff fi fl ffi ffl st st``

then NFC normalize so any split combining marks get re-composed.

Other Rousseau files (Émile, Contrat Social, Émigré, ...) had no
``ſ`` hits — their ingest path normalized correctly. We touch only
the affected file to avoid noisy diffs.

Idempotent.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "data" / "rousseau" / "raw_fra" / "premier_discours.txt"

LIGATURES = {
    "ſ": "s",
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}


def main() -> int:
    if not TARGET.is_file():
        print(f"Rousseau target not found: {TARGET}", file=sys.stderr)
        return 1
    raw = TARGET.read_text(encoding="utf-8")
    cleaned = raw
    counts: dict[str, int] = {}
    for src, dst in LIGATURES.items():
        n = cleaned.count(src)
        if n:
            counts[src] = n
            cleaned = cleaned.replace(src, dst)
    cleaned = unicodedata.normalize("NFC", cleaned)
    if cleaned == raw:
        print(f"  {TARGET.name}: clean (no long-s / ligatures)", file=sys.stderr)
        return 0
    TARGET.write_text(cleaned, encoding="utf-8")
    print(
        f"  {TARGET.name}: normalized {sum(counts.values())} glyphs "
        f"({len(raw):,} → {len(cleaned):,} chars); breakdown: {counts}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
