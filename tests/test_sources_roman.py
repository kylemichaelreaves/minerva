"""Tests for the shared strict Roman-numeral converter
(`minerva.sources._roman.roman_to_int`) and its call sites.

The converter used to exist as three divergent per-module copies;
the ica_parse copy returned wrong nonzero values for garbage because
unknown characters contributed 0. The shared one returns None for
anything that isn't pure Roman.
"""

from __future__ import annotations

import pytest

from minerva.sources._roman import roman_to_int
from minerva.sources.ica_parse import _split_by_part


class TestRomanToInt:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("I", 1),
            ("III", 3),
            ("IV", 4),
            ("IX", 9),
            ("XIV", 14),
            ("XL", 40),
            ("XLVII", 47),
            ("LX", 60),
            ("MCMXCIV", 1994),
            # Lowercase tolerated.
            ("xiv", 14),
            # Non-classical but decodable forms.
            ("IIII", 4),
            ("IL", 49),
        ],
    )
    def test_valid(self, raw: str, expected: int) -> None:
        assert roman_to_int(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "hello",
            "4",  # arabic digits are NOT roman; callers convert those
            "X IV",  # internal whitespace is caller-side OCR repair
            "BOOK",  # mixed garbage used to yield 0 via the ica copy
            "PIVOT",  # contains valid glyphs but also garbage
        ],
    )
    def test_invalid_returns_none(self, raw: str) -> None:
        assert roman_to_int(raw) is None


class TestIcaBookHeaderCallSite:
    def test_book_roman_header_sets_section(self) -> None:
        body = "BOOK II\n\nPart 1\n\nSome prose here.\n"
        parts = list(_split_by_part(body))
        assert parts == [("2", "1", "Some prose here.")]

    def test_flat_part_works_synthesize_section_1(self) -> None:
        body = "Part 1\n\nProse without any BOOK header.\n"
        parts = list(_split_by_part(body))
        assert parts == [("1", "1", "Prose without any BOOK header.")]
