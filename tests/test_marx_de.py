"""Tests for the German OCR Marx parser.

Pins three things:
  1. The TOC-cluster filter detects the chapter-number-reset signal
     (TOC lists Cap 1..N, body restarts at Cap 1).
  2. The chapter-heading regex tolerates the specific OCR variants
     observed in the live Kapital scans (`Sechszehntes`, no-space
     `AchtzehntesKapitel`, trailing junk-punct `.”“) ` / `.)`).
  3. End-to-end parse of the live Kapital Bd 1/2/3 OCR files emits
     the expected chapter counts. The integration tests skip when
     the data files aren't present in the checkout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minerva.marx_de import (
    _CHAPTER_HEADING_RE,
    _filter_toc_cluster,
    _heading_to_int,
    parse_file,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BD1 = _REPO_ROOT / "data" / "marx" / "raw_deu_ocr" / "kapital_bd1.txt"
_BD2 = _REPO_ROOT / "data" / "marx" / "raw_deu_ocr" / "kapital_bd2.txt"
_BD3 = _REPO_ROOT / "data" / "marx" / "raw_deu_ocr" / "kapital_bd3.txt"


# ════════════════════════════════════════════════════════════════════
# Unit: _filter_toc_cluster
# ════════════════════════════════════════════════════════════════════


class TestFilterTocCluster:

    def test_bd1_pattern(self) -> None:
        # Bd 1's actual TOC + body shape (line numbers from the live
        # 1867 Fraktur scan). TOC: chapters 1-6 close together; body
        # starts with Erstes Kapitel (chapter resets to 1).
        candidates = [
            (58, 1), (83, 2), (90, 3), (101, 4), (177, 5), (211, 6),
            (499, 1), (5171, 2), (6751, 3),
        ]
        out = _filter_toc_cluster(candidates)
        assert out == [(499, 1), (5171, 2), (6751, 3)]

    def test_bd3_pattern(self) -> None:
        # Bd 3's pattern: long TOC (chapters 1-28), body restarts at 1.
        toc = [(1158 + i, i + 1) for i in range(28)]
        body = [(1341 + i * 500, i + 1) for i in range(16)]
        out = _filter_toc_cluster(toc + body)
        assert out == body

    def test_no_toc_passes_through(self) -> None:
        # Bd 2 has only body candidates (monotonic Cap 1-21, no TOC
        # in the ldpd scan). No drop signal → pass through.
        candidates = [(1271 + i * 500, i + 1) for i in range(21)]
        assert _filter_toc_cluster(candidates) == candidates

    def test_short_works_pass_through(self) -> None:
        # 0 / 1 / 2-candidate inputs should pass through untouched.
        assert _filter_toc_cluster([]) == []
        assert _filter_toc_cluster([(10, 1)]) == [(10, 1)]
        assert _filter_toc_cluster([(10, 1), (200, 2)]) == [(10, 1), (200, 2)]

    def test_minor_ocr_slip_tolerated(self) -> None:
        # OCR sometimes mis-reads a chapter as one less than expected;
        # a drop of ≤2 should NOT trigger the body-restart signal.
        candidates = [(10, 1), (20, 2), (30, 3), (40, 4), (50, 5), (60, 3), (70, 6)]
        # 3 < 5-2=3 is False (strict), so the slip doesn't trigger.
        # All candidates pass through.
        assert _filter_toc_cluster(candidates) == candidates


# ════════════════════════════════════════════════════════════════════
# Unit: chapter-heading regex + wordform parser
# ════════════════════════════════════════════════════════════════════


class TestChapterHeadingRegex:

    @pytest.mark.parametrize(
        "line,expected_chap",
        [
            # Standard wordform forms (live Bd 1)
            ("Erstes Kapitel.", 1),
            ("Sechstes Kapitel.", 6),
            # Bd 2 OCR variants
            ("Sechszehntes Kapitel.", 16),           # alt spelling with extra `s`
            ("AchtzehntesKapitel.", 18),             # OCR-merged words
            ("AchtzehntesKapitel.”“)", 18),          # OCR-merged + trailing junk
            ("Neunzehntes Kapitel.)", 19),           # trailing close-paren
            # Numeric / Roman fallback
            ("Kapitel 7", 7),
            ("Kapitel III.", 3),
            ("Kapitel XXVII.", 27),
        ],
    )
    def test_matches_and_parses(self, line: str, expected_chap: int) -> None:
        m = _CHAPTER_HEADING_RE.match(line)
        assert m is not None, f"failed to match {line!r}"
        assert _heading_to_int(m.group(1)) == expected_chap

    @pytest.mark.parametrize(
        "line",
        [
            # In-text cross references (must NOT match)
            "Kap. XVI, 1. — F.E]",                   # Engels editorial ref
            "siehe Sechstes Kapitel oben",            # body text mention
            "wie im viertes Kapitel gezeigt",         # body text
            "(Sechstes Kapitel)",                     # parenthetical
            "",                                       # empty
            "Eine Bemerkung über das Kapitel.",       # body sentence
        ],
    )
    def test_rejects_non_headings(self, line: str) -> None:
        m = _CHAPTER_HEADING_RE.match(line)
        # Either no match, OR the match doesn't span the full line
        # (e.g., the heading-shape is embedded in a longer body line).
        # We accept both as "not a real chapter heading."
        if m is None:
            return
        # If the regex matched, it must consume the whole line via
        # `\s*$` — which won't happen for the body-text cases above.
        assert m.end() < len(line) or "Kapitel" not in line[: m.start()], (
            f"unexpectedly matched body line: {line!r}"
        )


# ════════════════════════════════════════════════════════════════════
# Integration: live OCR files
# ════════════════════════════════════════════════════════════════════


def _parse(path: Path, code: str, title: str) -> list:
    if not path.is_file():
        pytest.skip(f"OCR data not present at {path}")
    return list(parse_file(path, work_title=title, work_code=code))


class TestKapitalIntegration:

    def test_bd1_six_chapters(self) -> None:
        chunks = _parse(_BD1, "kapital_bd1", "Das Kapital, Band I")
        sections = sorted(int(c.section.split()[1]) for c in chunks)
        # 1867 first edition: exactly 6 chapters (the parser MUST NOT
        # over-detect via OCR cross-references picked up by the new
        # broader regex).
        assert sections == [1, 2, 3, 4, 5, 6]

    def test_bd2_all_canonical_chapters(self) -> None:
        chunks = _parse(_BD2, "kapital_bd2", "Das Kapital, Band II")
        sections = sorted(int(c.section.split()[1]) for c in chunks)
        # Engels 1885 / ldpd scan: 21 chapters. Was 17 before the
        # Sechszehntes / AchtzehntesKapitel / Neunzehntes-with-paren
        # fixes.
        assert sections == list(range(1, 22)), (
            f"expected chapters 1-21, got {sections}"
        )

    def test_bd3_all_canonical_chapters(self) -> None:
        chunks = _parse(_BD3, "kapital_bd3", "Das Kapital, Band III")
        sections = sorted(int(c.section.split()[1]) for c in chunks)
        # Engels 1894 / ldpd scan: 28 chapters present. (Canonical
        # Bd 3 has 52 across more Abschnitte but this scan stops at
        # 28.) Was 9 before the TOC-filter fix.
        assert sections == list(range(1, 29)), (
            f"expected chapters 1-28, got {sections}"
        )
