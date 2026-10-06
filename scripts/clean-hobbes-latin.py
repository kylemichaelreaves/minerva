#!/usr/bin/env python3
"""Ligature repair for the Molesworth Latin Hobbes OCR.

Runs between ``perseus/download_hobbes_la.py`` and ``minerva ingest``,
in place and idempotently, over::

    data / hobbes / raw_lat / leviathan_lat.txt
    data / hobbes / raw_lat / leviathan_appendix_lat.txt
    data / hobbes / raw_lat / de_cive_lat.txt

(every ``*.txt`` there — the appendix, added by #575, needs no rule of its
own: its scan resolves the ligatures the same ways, 209 words repaired and
127 caret tokens stripped on 2026-09-30)

**This script used to be about something else.** Before #535 the
sources were Internet Archive scans of the 1668 and 1704 printings,
set in long-s type, and this file's docstring said the residual long-s
contamination could not be repaired because "pyspellchecker doesn't
ship a Latin wordlist". Both halves of that are now moot: the sources
are Molesworth's 1839 roman-type reprint, which has no long-s, and the
Latin vocabulary the old note said we lacked has been sitting in
``data/latin_vocab.json`` since the Boulainvilliers round.

What Molesworth's OCR gets wrong instead is the **Æ and Œ ligatures**.
The 1839 printing sets *quae* as ``quæ`` and *coelum* as ``cœlum``, and
the scan resolves those two glyphs inconsistently — differently between
the two volumes, which is why both substitution families are needed:

    vol. III (Leviathan)   æ → se     quse, sestimati, praeda → praesda
    vol. II  (De Cive)     æ → ze     tuze, nzeniis, lzdendi
                           æ → ee     preeterquam, esedem
                           æ → z      equales
    both                   œ → ce     ccelum, ccena

Every substitution is **dictionary-guided**: a word is rewritten only
when it is absent from the Latin vocabulary and the rewrite is present.
That is what makes it safe to apply ``se → ae`` at all — *esse* and
*sensus* are in the vocabulary and so are never touched — and what
makes the script idempotent, since a repaired word is in the vocabulary
on the next pass.

Measured on the parsed chunks, 2026-09-12 (vocabulary-hit rate over
tokens of 4+ letters; clean Latin from outside the vocabulary's own
sources reads 78–88% on this scorer):

    Leviathan   85.8%  →  86.9%   (873 words repaired)
    De Cive     84.3%  →  86.0%   (850 words repaired)

Caret debris (``^ T^``, ``j^ ^*``) is stripped in the same pass: 457
tokens in Leviathan, 75 in De Cive, all of it the marginal gloss column
coming apart under OCR.

Run:

    uv run python scripts/clean-hobbes-latin.py

Role: workflow
"""

from __future__ import annotations

import itertools
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOBBES_DIR = REPO_ROOT / "data" / "hobbes" / "raw_lat"
VOCAB_PATH = REPO_ROOT / "data" / "latin_vocab.json"

# (wrong, right). Order matters only for reporting; the first
# substitution that lands a real word wins.
_LIGATURE_SUBS: tuple[tuple[str, str], ...] = (
    ("se", "ae"),
    ("ze", "ae"),
    ("ee", "ae"),
    ("z", "ae"),
    ("ce", "oe"),
)

# How many occurrences of a substring may be rewritten at once. Two
# covers every real case (``prseterquam`` needs one, ``sestimatse``
# two) and keeps the candidate count bounded — a word with six "se"
# runs would otherwise generate 63 candidates.
_MAX_SUBSTITUTIONS = 2

_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]{4,}")
_CARET_TOKEN_RE = re.compile(r"\S*\^\S*")


def _load_vocab() -> set[str]:
    if not VOCAB_PATH.exists():
        raise SystemExit(
            f"Latin vocabulary not found at {VOCAB_PATH}. It is built from "
            f"the corpus's clean Aquinas / Augustine / Spinoza Latin; see "
            f"the Boulainvilliers cleanup scripts for the build command."
        )
    return set(json.loads(VOCAB_PATH.read_text(encoding="utf-8")))


def _repair_word(word: str, vocab: set[str]) -> str | None:
    """Dictionary-guided ligature repair for one word.

    Returns the corrected word, or None when the word is already known
    or no substitution produces a known one. Case is preserved by
    applying the lowercase decision back to the original.
    """

    lower = word.lower()
    if lower in vocab:
        return None
    for wrong, right in _LIGATURE_SUBS:
        positions = [m.start() for m in re.finditer(re.escape(wrong), lower)]
        if not positions:
            continue
        for count in range(1, min(len(positions), _MAX_SUBSTITUTIONS) + 1):
            for combo in itertools.combinations(positions, count):
                candidate = lower
                offset = 0
                for pos in combo:
                    at = pos + offset
                    candidate = candidate[:at] + right + candidate[at + len(wrong) :]
                    offset += len(right) - len(wrong)
                if candidate in vocab:
                    return candidate.capitalize() if word[0].isupper() else candidate
    return None


def _repair_text(text: str, vocab: set[str]) -> tuple[str, int]:
    """Apply `_repair_word` across a whole file. Returns the new text
    and the number of words rewritten."""

    repaired = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal repaired
        fixed = _repair_word(match.group(0), vocab)
        if fixed is None:
            return match.group(0)
        repaired += 1
        return fixed

    return _WORD_RE.sub(_sub, text), repaired


def main() -> int:
    if not HOBBES_DIR.is_dir():
        print(f"Hobbes Latin dir not found: {HOBBES_DIR}", file=sys.stderr)
        return 1
    vocab = _load_vocab()
    total_repaired = 0
    total_carets = 0
    for path in sorted(HOBBES_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        carets = len(_CARET_TOKEN_RE.findall(text))
        text = _CARET_TOKEN_RE.sub("", text)
        text, repaired = _repair_text(text, vocab)
        path.write_text(text, encoding="utf-8")
        total_repaired += repaired
        total_carets += carets
        print(
            f"  {path.name}: {repaired:,} ligature words repaired, "
            f"{carets:,} caret tokens stripped",
            file=sys.stderr,
        )
    print(
        f"\nTotal: {total_repaired:,} words repaired, {total_carets:,} caret tokens stripped.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
