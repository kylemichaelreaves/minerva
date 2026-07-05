"""Tests for translate/parse.py — dual-label parsing and refusal detection."""

from __future__ import annotations

from minerva.translate.parse import (
    is_dual_translation,
    looks_like_refusal,
    parse_dual_translation,
)


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


def test_is_dual_translation_true_for_labeled() -> None:
    assert is_dual_translation("LITERAL:\nx\n\nLITERARY:\ny\n")


def test_is_dual_translation_false_for_prose() -> None:
    assert not is_dual_translation("The source passage seems incomplete.")


def test_labeled_translation_with_refusal_word_is_not_a_refusal() -> None:
    # A valid translation whose CONTENT contains "incomplete" must be
    # recognized as a structured translation so the handler doesn't
    # blank it out via a substring refusal match (issue #58).
    raw = "LITERAL:\nthe work is incomplete\n\nLITERARY:\nthe work is unfinished\n"
    assert is_dual_translation(raw)
    literal, _literary = parse_dual_translation(raw)
    assert "incomplete" in literal
