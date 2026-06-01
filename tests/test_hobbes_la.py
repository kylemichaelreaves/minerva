"""Tests for the OCR'd Latin Hobbes parser.

Pins:
  * All 47 chapters of the 1668 Latin Leviathan are recovered, even
    the 4 whose CAPVT headings were mangled by the Internet Archive
    OCR (Cap IV, XI, XXV, XXXI).
  * The De Cive parser is unaffected by the Leviathan-targeted regex
    broadening — it should continue to detect all 18 chapters.
  * `_roman_to_int` handles the OCR substitutions we rely on
    (trailing-L → I, internal whitespace, T → I) without breaking
    legitimate Roman numeral forms.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minerva.sources.hobbes_la import _roman_to_int, parse_file

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LEVIATHAN_LAT = _REPO_ROOT / "data" / "hobbes" / "raw_lat" / "leviathan_lat.txt"
_DE_CIVE_LAT = _REPO_ROOT / "data" / "hobbes" / "raw_lat" / "de_cive_lat.txt"


# Both Latin OCR files are large data inputs that aren't carried in
# every checkout. Skip the integration tests when the data isn't
# present — the unit tests for `_roman_to_int` still run.
_HAS_LEVIATHAN = _LEVIATHAN_LAT.is_file()
_HAS_DE_CIVE = _DE_CIVE_LAT.is_file()


@pytest.fixture(scope="module")
def leviathan_chunks() -> list:
    if not _HAS_LEVIATHAN:
        pytest.skip(f"Latin Leviathan OCR not present at {_LEVIATHAN_LAT}")
    return list(
        parse_file(
            _LEVIATHAN_LAT,
            work_title="Leviathan",
            work_code="leviathan_lat",
        )
    )


@pytest.fixture(scope="module")
def de_cive_chunks() -> list:
    if not _HAS_DE_CIVE:
        pytest.skip(f"De Cive OCR not present at {_DE_CIVE_LAT}")
    return list(
        parse_file(
            _DE_CIVE_LAT,
            work_title="De Cive",
            work_code="de_cive_lat",
        )
    )


# ════════════════════════════════════════════════════════════════════
# Integration: Latin Leviathan — all 47 chapters
# ════════════════════════════════════════════════════════════════════


class TestLeviathanChapters:

    def test_all_47_chapters_present(self, leviathan_chunks: list) -> None:
        sections = {
            int(c.section.split()[1]) for c in leviathan_chunks
        }
        assert sections == set(range(1, 48)), (
            f"missing chapters: "
            f"{sorted(set(range(1, 48)) - sections)}"
        )

    def test_chapter_count(self, leviathan_chunks: list) -> None:
        unique_sections = {c.section for c in leviathan_chunks}
        assert len(unique_sections) == 47

    def test_cap_iv_recovered_via_gap_fill(
        self, leviathan_chunks: list
    ) -> None:
        # Cap IV has no surviving CAPVT line in the OCR; the
        # post-pass should recover it from the "Cap. 4. De Homine."
        # page running heads. Verify the chunk exists with
        # substantive body and is genuinely the De Homine chapter.
        c4 = next(
            (c for c in leviathan_chunks if c.section == "Cap 4"),
            None,
        )
        assert c4 is not None, "Cap 4 not recovered"
        assert len(c4.text) > 500, (
            f"Cap 4 too short: {len(c4.text)} chars"
        )
        assert "Homine" in c4.text, (
            "Cap 4 should be 'De Homine' but doesn't contain "
            "'Homine' in its body"
        )

    def test_cap_xi_recovered(self, leviathan_chunks: list) -> None:
        # Cap XI's CAPVT line at L438 has a literal backslash
        # between T and the numeral. Recovered by the regex
        # broadening.
        c11 = next(
            (c for c in leviathan_chunks if c.section == "Cap 11"),
            None,
        )
        assert c11 is not None, "Cap 11 not recovered"
        assert len(c11.text) > 500

    def test_cap_xxv_recovered(self, leviathan_chunks: list) -> None:
        # Cap XXV's CAPVT line at L989 has F-for-P OCR
        # substitution. Recovered by the regex broadening.
        c25 = next(
            (c for c in leviathan_chunks if c.section == "Cap 25"),
            None,
        )
        assert c25 is not None, "Cap 25 not recovered"
        assert len(c25.text) > 500

    def test_cap_xxxi_recovered(
        self, leviathan_chunks: list
    ) -> None:
        # Cap XXXI's CAPVT line at L1326 reads "CAPVT  XXX  L"
        # (trailing I OCR'd as L). Recovered by the
        # trailing-L → I prefix in `_roman_to_int`.
        c31 = next(
            (c for c in leviathan_chunks if c.section == "Cap 31"),
            None,
        )
        assert c31 is not None, "Cap 31 not recovered"
        assert len(c31.text) > 500


# ════════════════════════════════════════════════════════════════════
# Regression: De Cive parser still works after Leviathan fixes
# ════════════════════════════════════════════════════════════════════


class TestDeCiveRegression:

    def test_de_cive_still_18_chapters(
        self, de_cive_chunks: list
    ) -> None:
        sections = {
            int(c.section.split()[1]) for c in de_cive_chunks
        }
        assert sections == set(range(1, 19)), (
            f"De Cive regressed; missing: "
            f"{sorted(set(range(1, 19)) - sections)}"
        )

    def test_de_cive_chunk_count(
        self, de_cive_chunks: list
    ) -> None:
        assert len(de_cive_chunks) == 18


# ════════════════════════════════════════════════════════════════════
# Unit: `_roman_to_int` OCR corrections
# ════════════════════════════════════════════════════════════════════


class TestRomanToInt:

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # OCR substitutions we ACTUALLY rely on
            ("XXXL", 31),       # trailing I OCR'd as L (Cap XXXI)
            ("XXX  L", 31),     # same, with internal whitespace
            ("XIL", 12),        # II final stroke as L (Cap XII)
            ("I L", 2),         # spaced "II" mis-OCR'd
            ("VIIL", 8),        # Cap VIII spaced form
            ("XXVIIL", 28),     # Cap XXVIII spaced form
            # Legitimate Roman forms that MUST NOT be corrupted
            ("XL", 40),
            ("XLI", 41),
            ("XLII", 42),
            ("XLV", 45),
            ("XLVI", 46),
            ("XLVII", 47),
            ("LX", 60),
            ("LXX", 70),
            ("L", 50),
            # Internal-whitespace handling
            ("X L", 40),
            ("X L I", 41),
            ("X L V", 45),
            ("X X V I I L", 28),
            # Edge / arabic
            ("4", 4),
            ("21", 21),
            ("III", 3),
            ("IV", 4),
            # T → I OCR substitution
            ("XII", 12),
            ("TI", 2),
        ],
    )
    def test_conversions(self, raw: str, expected: int) -> None:
        assert _roman_to_int(raw) == expected

    def test_empty_returns_none(self) -> None:
        assert _roman_to_int("") is None

    def test_garbage_returns_none(self) -> None:
        assert _roman_to_int("hello") is None
