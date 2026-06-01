"""Tests for translate/parse.py — dual-label parsing and refusal detection."""

from __future__ import annotations

from minerva.translate.parse import looks_like_refusal, parse_dual_translation


def test_parse_dual_translation_labeled() -> None:
    raw = "LITERAL:\nword-for-word\n\nLITERARY:\nidiomatic prose\n"
    literal, literary = parse_dual_translation(raw)
    assert literal == "word-for-word"
    assert literary == "idiomatic prose"


def test_parse_dual_translation_fallback() -> None:
    literal, literary = parse_dual_translation("plain output")
    assert literal == ""
    assert literary == "plain output"


def test_looks_like_refusal_positive() -> None:
    assert looks_like_refusal("The source passage seems incomplete.")


def test_looks_like_refusal_negative() -> None:
    assert not looks_like_refusal("Being and time")
