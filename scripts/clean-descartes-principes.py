#!/usr/bin/env python3
"""Partial cleanup for Descartes' *Principes* parts II-IV.

The 2026-05-31 corpus quality audit flagged 117 caret_artifact
chunks in Descartes — all from a single file:
``data/descartes/raw_fr/principes_pars2to4.txt``. The other five
Descartes source files (meditationes, principia LA, meditations
FR, principes_pars1 FR, discours FR) are clean.

**This file has a fundamentally broken PDF extraction.** It looks
like the original PDF was multi-column or had marginalia that got
merged into the body text:

* Mangled tokens scattered in body text: ``Coissisbi``, ``Mvoo``,
  ``ftroe``, ``fane`` (for ``âme``), ``Mulconnir``, ``iTmratoT``,
  ``inouuubi.``, ``Wuteuoni^c``. These are OCR'd marginal printer's
  marks / catchwords that bled into the main column.
* Internal text duplication inside chunks — e.g.
  ``Coissisbi Nous devons conclure aussi … Mvoo. Coissisbi Nous
  devons conclure aussi … Mvoo.`` (the SAME sentence appears twice
  back-to-back). PDF extraction likely captured both the body
  column and a duplicated render path.
* ``c^`` artifacts where cedillas belong — ``fac^on`` for ``façon``,
  ``rec^u`` for ``reçu``, ``rec^oit`` for ``reçoit``.

A regex cleanup CANNOT salvage this file — the marginalia tokens
are interleaved word-by-word with body text. The proper fix is
to re-extract from a clean source (Adam-Tannery edition, OEuvres
Complètes Vol IX-2, available on archive.org / Gallica). We log
this as a known-bad file for the next ingest pass.

Partial fixes we CAN apply here:

1. ``c^`` → ``ç`` cedilla restoration (covers ~30-50 hits per file).
2. ``ç^`` / ``e^`` / ``s^`` similar accent restorations.
3. Caret-bearing token strip (``\\S*\\^\\S*`` → drop) for tokens
   that can't be salvaged.
4. Same-file paragraph dedup (≥60 chars) to drop the internal
   duplicate sentences.

Even after this, the file's chunks remain partially unreadable —
this is **harm reduction, not a fix**.

Idempotent.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "data" / "descartes" / "raw_fr" / "principes_pars2to4.txt"


# Caret-as-broken-cedilla / accent substitutions. Apply BEFORE the
# generic caret-strip so we recover what we can.
_CARET_CEDILLA = [
    # c^a/c^o/c^u → ça/ço/çu (most common: "façon", "reçu", "reçoit")
    (re.compile(r"c\^a"), "ça"),
    (re.compile(r"c\^o"), "ço"),
    (re.compile(r"c\^u"), "çu"),
    # rare: capital cedilla
    (re.compile(r"C\^a"), "Ça"),
    (re.compile(r"C\^o"), "Ço"),
    # e^/e' fragments where the accent got separated
    (re.compile(r"e\^"), "ê"),
    (re.compile(r"a\^"), "â"),
    (re.compile(r"o\^"), "ô"),
    (re.compile(r"u\^"), "û"),
    (re.compile(r"i\^"), "î"),
]

_RE_CARET_TOKEN = re.compile(r"\S*\^\S*")


def clean_text(raw: str) -> tuple[str, int, int]:
    """Apply cedilla restoration + caret-token strip + dedup.

    Returns (cleaned, caret_tokens_dropped, dup_paragraphs_dropped).
    """

    text = raw
    for pat, repl in _CARET_CEDILLA:
        text = pat.sub(repl, text)
    # Count caret tokens before strip for the report.
    pre_strip_caret_tokens = len(_RE_CARET_TOKEN.findall(text))
    text = _RE_CARET_TOKEN.sub(" ", text)
    # Collapse intra-line multiple spaces.
    text = re.sub(r"  +", " ", text)
    # Same-file dedup pass.
    seen: set[str] = set()
    out_lines: list[str] = []
    dup_dropped = 0
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) >= 60:
            if stripped in seen:
                dup_dropped += 1
                continue
            seen.add(stripped)
        out_lines.append(line)
    cleaned = "\n".join(out_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, pre_strip_caret_tokens, dup_dropped


def main() -> int:
    if not TARGET.is_file():
        print(f"Descartes target not found: {TARGET}", file=sys.stderr)
        return 1
    raw = TARGET.read_text(encoding="utf-8")
    cleaned, caret_tokens, dups = clean_text(raw)
    TARGET.write_text(cleaned, encoding="utf-8")
    print(
        f"  {TARGET.name}: -{caret_tokens} caret tokens, "
        f"-{dups} duplicate paragraphs "
        f"({len(raw):,} → {len(cleaned):,} chars)",
        file=sys.stderr,
    )
    print(
        "\nNOTE: this file's PDF extraction is fundamentally broken.\n"
        "Marginal sidenotes are interleaved with body text. A regex\n"
        "cleanup cannot fully recover it; re-extraction from a clean\n"
        "source (Adam-Tannery OEuvres IX-2 on archive.org) is the\n"
        "proper fix. The pass above is harm reduction.\n",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
