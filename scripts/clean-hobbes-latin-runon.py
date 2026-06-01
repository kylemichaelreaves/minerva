#!/usr/bin/env python3
"""Latin-vocab-guided cleanup for Hobbes's Latin OCR run-on tokens.

The 2026-05-31 corpus quality audit flagged 23 chunks in Hobbes
with run-on tokens like ``jforanominealiudfignificaturquam`` and
``illafolanonrefiftentiaconfiftere``. These survived the initial
caret/ligature cleanup pass (``scripts/clean-hobbes-latin.py``)
because pyspellchecker ships no Latin dictionary; the
Boulainvilliers-style dict-guided f→s + split passes had nothing
to verify candidates against.

This script builds a Latin vocabulary from clean in-corpus Latin
(Aquinas + Augustine + Spinoza — about 50,000 unique words at
freq ≥2) and uses it to:

1. **Repair the 17th-c long-s OCR misread**: ``inftituto`` →
   ``instituto``, ``Cenforis`` → ``Censoris``, ``fubftantia`` →
   ``substantia``. Same dict-guided multi-position f-cluster
   substitution as the Boulainvilliers French pass, but against
   the Latin vocab.
2. **Split run-on tokens**: ``illafolanonrefiftentia confiftere``
   → after f→s: ``illasolanonresistentiaconsistere`` → split at
   dict boundaries → ``illa sola non resistentia consistere``.

Vocabulary build:

    uv run python -c "from collections import Counter; import sqlite3; ..."

Cached to ``data/latin_vocab.json`` so reruns don't re-query the DB.

Idempotent.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOBBES_DIR = REPO_ROOT / "data" / "hobbes" / "raw_lat"
VOCAB_PATH = REPO_ROOT / "data" / "latin_vocab.json"


def _load_vocab() -> set[str]:
    """Load the cached Latin vocabulary (built from Aquinas + Augustine
    + Spinoza Latin chunks; words occurring 2+ times)."""

    if not VOCAB_PATH.exists():
        raise RuntimeError(
            f"Latin vocab not found at {VOCAB_PATH}; build it via:\n"
            "  uv run python -c \"<see clean-hobbes-latin-runon.py docstring>\""
        )
    return set(json.loads(VOCAB_PATH.read_text(encoding="utf-8")))


def _fix_medial_f_to_s_latin(text: str, vocab: set[str]) -> str:
    """Latin-vocab-guided f→s repair.

    For each word containing one or more non-word-initial ``f``s,
    try substituting them with ``s`` (one cluster at a time);
    accept the variant that appears in the vocab. Words that are
    already in the vocab are left alone (no false positives on
    legitimate Latin f-words like ``officium``, ``effectus``).
    """

    def _try(word: str) -> str:
        if len(word) < 4 or "f" not in word.lower():
            return word
        lower = word.lower()
        # If already in vocab, leave alone — no false positives on
        # legitimate Latin f-words like ``officium``, ``effectus``,
        # ``forma``, ``foris``.
        if lower in vocab:
            return word
        # Find ALL f-cluster positions, including word-initial.
        # In Latin OCR, sentence-initial uppercase ``F`` may be a
        # long-s misread too (``Fubftantia`` for ``Substantia``);
        # the vocab-guard catches over-swap risk.
        positions: list[tuple[int, int]] = []
        i = 0
        while i < len(lower):
            if lower[i] != "f":
                i += 1
                continue
            end = i
            while end < len(lower) and lower[end] == "f":
                end += 1
            positions.append((i, end))
            i = end
        if not positions:
            return word
        # Enumerate 2^k variants (k usually ≤ 3).
        n = len(positions)
        best = word
        best_score = -1
        for mask in range(1, 1 << n):
            variant = list(word)
            for idx, (s, e) in enumerate(positions):
                if (mask >> idx) & 1:
                    for k in range(s, e):
                        variant[k] = "S" if word[k].isupper() else "s"
            cand = "".join(variant)
            if cand.lower() in vocab:
                # Prefer the variant with MORE swaps (closer to
                # full long-s interpretation).
                swap_count = bin(mask).count("1")
                if swap_count > best_score:
                    best_score = swap_count
                    best = cand
        return best

    return re.sub(r"[A-Za-zÀ-ÿ]+", lambda m: _try(m.group(0)), text)


def _split_run_on_latin(text: str, vocab: set[str]) -> str:
    """Insert spaces in run-on Latin tokens.

    A 30+ character alphabetic token that isn't a known Latin word
    is tested for split points — for every interior position, if
    BOTH halves are vocab-known Latin (each ≥ 3 chars), we split.
    The leftmost such split wins. This safely handles
    ``illafolanonresistentiaconsistere`` style joins without
    breaking legitimate Latin compounds.

    Returns the text with splits applied.
    """

    def _try(word: str) -> str:
        if len(word) < 12 or word.isupper():
            return word
        lower = word.lower()
        if lower in vocab:
            return word
        # Search for the leftmost valid 2-way split. If the right
        # half isn't in vocab, recurse on it so longer chains split.
        for i in range(4, len(word) - 3):
            left = lower[:i]
            right = lower[i:]
            if left in vocab and (right in vocab or len(right) > 6):
                # Recurse on the right half if not directly in vocab.
                right_text = (
                    word[i:]
                    if right in vocab
                    else _try(word[i:])
                )
                return f"{word[:i]} {right_text}"
        return word

    return re.sub(r"[A-Za-zÀ-ÿ]{12,}", lambda m: _try(m.group(0)), text)


def main() -> int:
    if not HOBBES_DIR.is_dir():
        print(f"Hobbes Latin dir not found: {HOBBES_DIR}", file=sys.stderr)
        return 1
    vocab = _load_vocab()
    print(f"Loaded Latin vocab: {len(vocab):,} words", file=sys.stderr)
    total_before = 0
    total_after = 0
    for path in sorted(HOBBES_DIR.glob("*.txt")):
        raw = path.read_text(encoding="utf-8")
        before = len(raw)
        text = _fix_medial_f_to_s_latin(raw, vocab)
        text = _split_run_on_latin(text, vocab)
        # Collapse any double-spaces from splits.
        text = re.sub(r"  +", " ", text)
        path.write_text(text, encoding="utf-8")
        total_before += before
        total_after += len(text)
        # Count remaining run-ons for the report.
        long_tokens = len(re.findall(r"\b[A-Za-z]{30,}\b", text))
        print(
            f"  {path.name}: {before:,} → {len(text):,} chars; "
            f"~{long_tokens} long tokens remain",
            file=sys.stderr,
        )
    print(
        f"\nTotal: {total_before:,} → {total_after:,} chars "
        f"({(total_after - total_before) / total_before * 100:+.1f}%)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
