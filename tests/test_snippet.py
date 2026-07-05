"""Tests for the shared occurrence-finder and context-window helpers
(issue #71 — consolidated from glossary_import and the terms CLI)."""

from __future__ import annotations

from minerva.text.snippet import find_occurrences, plain_window


class TestFindOccurrences:
    def test_non_overlapping_is_default(self) -> None:
        # "aa" in "aaaa": non-overlapping yields positions 0 and 2.
        assert find_occurrences("aaaa", "aa") == [0, 2]

    def test_overlapping_reports_every_position(self) -> None:
        # The manual-tagging semantics: advance by 1, so 0,1,2.
        assert find_occurrences("aaaa", "aa", allow_overlap=True) == [0, 1, 2]

    def test_distinct_matches_agree_regardless_of_flag(self) -> None:
        text = "Plato and Aristotle and Plato again"
        assert find_occurrences(text, "Plato") == find_occurrences(
            text, "Plato", allow_overlap=True
        )
        assert find_occurrences(text, "Plato") == [0, 24]

    def test_empty_form_returns_nothing(self) -> None:
        assert find_occurrences("anything", "") == []

    def test_absent_form(self) -> None:
        assert find_occurrences("abc", "z") == []


class TestPlainWindow:
    def test_collapses_whitespace(self) -> None:
        text = "the   quick\nbrown\t\tfox jumps"
        # match "brown" (index 12..17), small radius
        start = text.index("brown")
        out = plain_window(text, start, start + 5, radius=6)
        assert "  " not in out
        assert "\n" not in out
        assert "brown" in out

    def test_ellipsis_marks_truncation(self) -> None:
        text = "x" * 100 + " target " + "y" * 100
        start = text.index("target")
        out = plain_window(text, start, start + 6, radius=10, ellipsis=True)
        assert out.startswith("…")
        assert out.endswith("…")
        assert "target" in out

    def test_no_ellipsis_when_within_bounds(self) -> None:
        text = "short target here"
        start = text.index("target")
        out = plain_window(text, start, start + 6, radius=40, ellipsis=True)
        assert "…" not in out
        assert out == "short target here"
