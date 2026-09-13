#!/usr/bin/env python3
"""Repair the capital-I misread in the French Sacy OSIS source (#557).

Runs between ``perseus/download_sacy_fr.py`` and ``minerva ingest``, in
place and idempotently, over ``data/sacy/raw_fra/sacy.xml``.

**Why a script and not a one-line edit.** The issue originally proposed
correcting the two bad fields in the XML directly. That file is
gitignored (``.gitignore:13  data/*``), so an edit there reaches no PR,
no CI and no other checkout, and evaporates the moment the source is
re-downloaded — with the issue already closed against it.

The damage is one OCR confusion — capital ``I`` read as lowercase ``l``
or as ``1`` — landing in two places, which need two different
detectors. Ten verses in all, swept over every one of the file's 31,437
verses.

**Shape A — the verse number ate the text (1 verse).** In
``Lam.3.711``, the verse's own first word ``Il`` was read as ``11`` and
glued onto the verse number. Both halves of that event have to be
undone: the osisID becomes ``Lam.3.7`` and the leading ``Il`` goes back
on the text. Until then Lamentations 3:7 is simply missing from the
edition — every other edition in the corpus has it where the French
sits, and ``Lam 3:8`` through ``3:11`` all exist here.

**Shape B — the text kept the damage, the number is fine (9 verses).**
``Il``/``Ils`` read as ``ll``/``lls``. The range check that finds shape
A cannot see these at all. A literal match is safe because French has
no word ``ll`` or ``lls``.

Two detectors that look right and are not, recorded so nobody re-walks
them:

  * "osisID ends in three or more digits" — 79 hits, almost all Psalm
    118, which genuinely has 176 verses in this versification. Hence
    the *range* check below rather than a length check.
  * "verse number ends in ``11`` and the text starts lowercase" — 48
    hits, of which 47 are ordinary Sacy continuations (``Matt.2.11``,
    ``Luke.3.11``) that begin lowercase by style.

Run:

    uv run python scripts/clean-sacy-fra.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SACY_XML = REPO_ROOT / "data" / "sacy" / "raw_fra" / "sacy.xml"

# Highest plausible verse number in any chapter of any book. Psalm 118
# reaches 176 here, so the bar sits above that and well below the 711
# that a swallowed "Il" produces. A verse number *length* check would
# flag Psalm 118 instead of the damage.
_MAX_PLAUSIBLE_VERSE = 200

# Shape A: <verse osisID='Book.Chap.Verse'>text
_VERSE_OPEN_RE = re.compile(
    r"(<verse\s+osisID=(['\"])([A-Za-z0-9]+)\.(\d+)\.(\d+)\2[^>]*>)",
)

# Shape B: the verse text opening with a bare `ll` or `lls`. `\s` after
# the word is what keeps it from matching a real word that merely
# begins "ll" — and anchoring to `>` keeps it from touching `ll`
# occurring mid-verse inside an ordinary French word.
_LEADING_LL_RE = re.compile(r"(<verse\b[^>]*>)(lls?)(\s)")


def _repair_shape_a(text: str) -> tuple[str, int]:
    """Undo a verse number that swallowed a leading ``Il``.

    ``Lam.3.711`` → ``Lam.3.7``, and ``Il`` goes back on the front of
    the verse text. Only fires when the trailing digits are literally
    ``11`` *and* removing them leaves a plausible verse number, so a
    genuine verse 111 or 211 is untouched.
    """

    repaired = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal repaired
        whole, quote, book, chapter, verse = match.groups()
        if int(verse) <= _MAX_PLAUSIBLE_VERSE:
            return whole
        if not verse.endswith("11"):
            return whole
        real = verse[:-2]
        if not real or int(real) > _MAX_PLAUSIBLE_VERSE:
            return whole
        repaired += 1
        return (
            f"<verse osisID={quote}{book}.{chapter}.{real}{quote}>Il "
        )

    out = _VERSE_OPEN_RE.sub(_sub, text)
    # The replacement above emits "Il " immediately after the tag; the
    # damaged text began with a lowercase word ("a élevé"), so the
    # result reads "Il a élevé".
    return out, repaired


def _repair_shape_b(text: str) -> tuple[str, int]:
    """``ll``/``lls`` opening a verse → ``Il``/``Ils``."""

    repaired = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal repaired
        tag, word, space = match.groups()
        repaired += 1
        return f"{tag}I{word[1:]}{space}"

    return _LEADING_LL_RE.sub(_sub, text), repaired


def repair_text(text: str) -> tuple[str, int]:
    """Apply both repairs. Returns the new text and the number of verses
    changed. Idempotent: a repaired verse matches neither detector."""

    text, a = _repair_shape_a(text)
    text, b = _repair_shape_b(text)
    return text, a + b


def main() -> int:
    if not SACY_XML.is_file():
        print(f"Sacy OSIS source not found: {SACY_XML}", file=sys.stderr)
        print(
            "Fetch it first: uv run python perseus/download_sacy_fr.py",
            file=sys.stderr,
        )
        return 1
    text = SACY_XML.read_text(encoding="utf-8")
    out, repaired = repair_text(text)
    if repaired:
        SACY_XML.write_text(out, encoding="utf-8")
    print(
        f"  {SACY_XML.name}: {repaired} verse(s) repaired "
        f"(expected 10 on first run, 0 thereafter)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
