#!/usr/bin/env python3
"""Caret + glyph cleanup for Hobbes' Latin source files.

The 2026-05-31 corpus quality audit flagged 49 caret_artifact +
18 run_on + 5 glyph_soup chunks in Hobbes. All Latin:

* ``data/hobbes/raw_lat/de_cive_lat.txt`` — 546 caret lines.
* ``data/hobbes/raw_lat/leviathan_lat.txt`` — 266 caret lines.

The English Hobbes files (Leviathan eng, De Corpore Politico,
Philosophical Rudiments, Human Nature) are clean.

The Latin files are the same Gallica/Google-Books OCR family as
Boulainvilliers — caret debris, ligatures, running headers — PLUS
the 17th-c long-s OCR misread (``inftituto``, ``Cenforis``,
``fapientix``). We CANNOT run the Boulainvilliers dict-guided
f→s pass here because pyspellchecker doesn't ship a Latin
wordlist. That residual long-s contamination is acknowledged in
the audit's `long_s_misread` count (10 chunks — already low
because the misread heuristic gates lang to {eng/fra/deu}).

This script applies the SAFE cleanup steps from the Boulainvilliers
pipeline:

1. Unicode ligature decomposition (``ﬁ ﬂ ﬀ ...``).
2. Hyphenation join across line breaks.
3. Caret-bearing token strip.
4. Page-number-only line drop.
5. Column-edge garbage line drop.
6. Glyph-soup line drop.
7. ``------------`` divider line drop.
8. Same-file paragraph dedup (≥60 chars).

A future round can add a Latin-aware f→s pass (CLTK or
in-corpus-vocabulary lookup) — that's tracked as a follow-up.

Idempotent.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOBBES_DIR = REPO_ROOT / "data" / "hobbes" / "raw_lat"

_BV_PATH = REPO_ROOT / "scripts" / "clean-boulainvilliers-texts.py"
_spec = importlib.util.spec_from_file_location("_bv_clean", _BV_PATH)
assert _spec and _spec.loader
_bv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bv)

# Hobbes Latin running-header patterns.
#
# DELIBERATE OMISSION: we do NOT strip ``CAPUT N``/``CAPVT N`` or
# ``PARS N``/``PARS PRIMA`` etc. — those lines are structural
# anchors the downstream chunker (``src/minerva/hobbes_la.py``)
# uses to detect chapter boundaries. Stripping them collapses the
# chunker's output from 65 chunks to ~40 mega-chunks because the
# splitter loses its CAPVT signal. Body running-heads (single-word
# Latin titles in caps on their own line) and dedication/preface
# titles are safe to drop.
_HOBBES_RUNNING = re.compile(
    r"^\s*(?:"
    r"DE\s+CIVE\s*\.?"
    r"|LEVIATHAN\s*\.?"
    r"|ELEMENTA\s+PHILOSOPHIAE?\s*\.?"
    r"|EPISTOLA\s+(?:DEDICATORIA)?\s*\.?"
    r"|PRAEFATIO\s*\.?"
    # NB: LIBERTAS / IMPERIUM / RELIGIO are PARS titles in De Cive
    # (3 parts). The chunker uses Pars detection too, so keep these
    # lines as well — they're rare and dropping them loses Pars info.
    # See src/minerva/hobbes_la.py:213 for Pars handling.
    r")\s*$",
    re.IGNORECASE,
)

_DIVIDER_LINE = re.compile(r"^-{10,}\s*$")
_DEDUP_MIN_LEN = 60


def main() -> int:
    """Minimal in-place caret-token strip + ligature decomposition.

    We deliberately avoid line-level filtering (running headers,
    page numbers, glyph-soup, column-edge garbage, dedup). The
    downstream chunker (``src/minerva/hobbes_la.py``) is a careful
    state machine that detects CAPVT / PARS / running-head /
    page-number sequences to identify chapter boundaries — running
    any of the Boulainvilliers line-level filters here disrupts
    those signals and collapses chunk count from 65 → 41 chunks.

    Caret tokens (``S<x^``, ``C^nnw^try``, ``h^``) are isolated
    OCR debris and safe to strip per-token: the chunker doesn't
    use them. Ligature decomposition (``ﬁ`` → ``fi``) is
    similarly local.
    """

    if not HOBBES_DIR.is_dir():
        print(f"Hobbes Latin dir not found: {HOBBES_DIR}", file=sys.stderr)
        return 1
    total_before = 0
    total_after = 0
    total_carets = 0
    for path in sorted(HOBBES_DIR.glob("*.txt")):
        raw = path.read_text(encoding="utf-8")
        before = len(raw)
        text = _bv._normalize_ligatures(raw)
        carets = len(re.findall(r"\S*\^\S*", text))
        text = _bv._strip_caret_artifacts(text)
        # Collapse multi-space runs left behind by caret strip.
        text = re.sub(r" {2,}", " ", text)
        path.write_text(text, encoding="utf-8")
        total_before += before
        total_after += len(text)
        total_carets += carets
        print(
            f"  {path.name}: -{carets} caret tokens "
            f"({before:,} → {len(text):,} chars)",
            file=sys.stderr,
        )
    print(
        f"\nTotal: -{total_carets} caret tokens, "
        f"{total_before:,} → {total_after:,} chars\n"
        f"NOTE: 17th-c long-s OCR misread (``inftituto`` etc.) "
        f"survives — pyspellchecker has no Latin wordlist for the "
        f"dict-guided f→s pass. Line-level filters (page numbers, "
        f"running heads, glyph-soup) also disabled because the "
        f"hobbes_la chunker reads those lines as section signals.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
