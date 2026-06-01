"""Tests for the versioned locator formatter + section parser in
`minerva.locations`."""

from __future__ import annotations

import pytest

from minerva import locations

# ════════════════════════════════════════════════════════════════════
# format_sort_key — version-frozen contract.
# ════════════════════════════════════════════════════════════════════


class TestSortKey:
    def test_version_constant_is_present(self):
        assert isinstance(locations.SORT_KEY_VERSION, int)
        assert locations.SORT_KEY_VERSION >= 1

    @pytest.mark.parametrize(
        ("kind", "payload", "expected"),
        [
            ("stephanus", {"page": 514, "section": "a"}, "S0514a"),
            ("stephanus", {"page": 327, "section": "e"}, "S0327e"),
            ("bekker", {"page": 1094, "column": "a", "line": 1}, "B1094a001"),
            ("bekker", {"page": 1094, "column": "b", "line": 25}, "B1094b025"),
            ("kant_ab", {"edition": "A", "page": 123}, "KA0123"),
            ("kant_ab", {"edition": "B", "page": 7}, "KB0007"),
            ("sz_marginal", {"page": 42}, "H0042"),
            ("paragraph", {"symbol": "§", "number": 44}, "P§00044"),
            ("paragraph", {"symbol": "¶", "number": 17, "suffix": "a"}, "P¶00017a"),
            ("bcv", {"book": "Genesis", "chapter": 1, "verse": 1}, "V00100010001"),
            ("bcv", {"book": "Matthew", "chapter": 5, "verse": 3}, "V04700050003"),
            (
                "bcv",
                {"book": "Esther", "chapter": 4, "verse": 17, "verse_suffix": "a"},
                "V01900040017a",
            ),
            (
                "bcv",
                {"book": "Revelation", "chapter": 22, "verse": 21},
                "V07300220021",
            ),
            # surah_ayah: Q-prefixed, fixed-width surah ordinal (3
            # digits) + ayah (4 digits). Al-Fatiha 1:1, Throne Verse
            # Q 2:255, An-Nas 114:6.
            ("surah_ayah", {"surah": 1, "ayah": 1}, "Q0010001"),
            ("surah_ayah", {"surah": 2, "ayah": 255}, "Q0020255"),
            ("surah_ayah", {"surah": 114, "ayah": 6}, "Q1140006"),
            (
                "surah_ayah",
                {"surah": 2, "ayah": 255, "ayah_suffix": "a"},
                "Q0020255a",
            ),
        ],
    )
    def test_known_payloads_format_stably(self, kind, payload, expected):
        # The whole point of versioning: changing this output without
        # bumping SORT_KEY_VERSION would orphan every term_occurrences
        # row's location_sort_key. Lock the values down so a sneaky
        # edit fails CI loudly.
        assert locations.format_sort_key(kind, payload) == expected

    def test_unknown_kind_raises(self):
        with pytest.raises(locations.LocationError):
            locations.format_sort_key("vatican", {"page": 1})

    def test_missing_field_raises_location_error(self):
        with pytest.raises(locations.LocationError):
            locations.format_sort_key("stephanus", {"page": 514})

    def test_out_of_range_raises(self):
        with pytest.raises(locations.LocationError):
            locations.format_sort_key("stephanus", {"page": 99999, "section": "a"})

    def test_paragraph_suffix_is_optional(self):
        # `paragraph` payload without suffix should still produce a
        # valid sort key (no trailing junk).
        out = locations.format_sort_key("paragraph", {"symbol": "§", "number": 1})
        assert out == "P§00001"


# ════════════════════════════════════════════════════════════════════
# parse_section — inverse parser used by the curator CLI.
# ════════════════════════════════════════════════════════════════════


class TestParseSection:
    @pytest.mark.parametrize(
        ("kind", "section", "expected"),
        [
            ("stephanus", "514a", {"kind": "stephanus", "page": 514, "section": "a"}),
            ("stephanus", " 327e ", {"kind": "stephanus", "page": 327, "section": "e"}),
            ("bekker", "1094a", {"kind": "bekker", "page": 1094, "column": "a", "line": 1}),
            ("bekker", "1094b25", {"kind": "bekker", "page": 1094, "column": "b", "line": 25}),
            ("kant_ab", "A123", {"kind": "kant_ab", "edition": "A", "page": 123}),
            ("sz_marginal", "42", {"kind": "sz_marginal", "page": 42}),
            ("sz_marginal", "SZ 42", {"kind": "sz_marginal", "page": 42}),
            ("paragraph", "§44", {"kind": "paragraph", "symbol": "§", "number": 44}),
            (
                "paragraph",
                "¶17a",
                {"kind": "paragraph", "symbol": "¶", "number": 17, "suffix": "a"},
            ),
            (
                "bcv",
                "Gen 1:1",
                {"kind": "bcv", "book": "Genesis", "chapter": 1, "verse": 1},
            ),
            (
                "bcv",
                "1Cor 13:4",
                {"kind": "bcv", "book": "1 Corinthians", "chapter": 13, "verse": 4},
            ),
            (
                "bcv",
                "Rev 22:21",
                {"kind": "bcv", "book": "Revelation", "chapter": 22, "verse": 21},
            ),
            (
                "bcv",
                "Esth 4:17a",
                {
                    "kind": "bcv",
                    "book": "Esther",
                    "chapter": 4,
                    "verse": 17,
                    "verse_suffix": "a",
                },
            ),
            # surah_ayah accepts bare ``2:255``, ``Q 2:255``, and
            # ``Surah 2:255`` so rule-based scripture-cite matching
            # works on Arabic-philosophy text written either way.
            (
                "surah_ayah",
                "2:255",
                {"kind": "surah_ayah", "surah": 2, "ayah": 255},
            ),
            (
                "surah_ayah",
                "Q 2:255",
                {"kind": "surah_ayah", "surah": 2, "ayah": 255},
            ),
            (
                "surah_ayah",
                "Surah 1:1",
                {"kind": "surah_ayah", "surah": 1, "ayah": 1},
            ),
        ],
    )
    def test_round_trip(self, kind, section, expected):
        assert locations.parse_section(kind, section) == expected

    def test_round_trip_to_sort_key(self):
        # parse_section → format_sort_key should agree end-to-end.
        payload = locations.parse_section("stephanus", "514a")
        assert locations.format_sort_key("stephanus", payload) == "S0514a"

    def test_malformed_input_raises(self):
        with pytest.raises(locations.LocationError):
            locations.parse_section("stephanus", "five-fourteen-a")

    def test_unknown_kind_raises(self):
        with pytest.raises(locations.LocationError):
            locations.parse_section("vatican", "514a")
