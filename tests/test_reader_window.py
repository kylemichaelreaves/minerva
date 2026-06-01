"""Tests for reader/window.py — shared pagination + chunk-window helpers."""

from __future__ import annotations

import pytest

from minerva.errors import BadRequestError
from minerva.reader.window import parse_limit_only, parse_window_params


def test_parse_window_params_defaults() -> None:
    p = parse_window_params({})
    assert p.from_ord == 0
    assert p.limit == 200
    assert p.lang == "grc"


def test_parse_window_params_custom() -> None:
    p = parse_window_params({"from": "10", "limit": "50", "lang": "deu"})
    assert p.from_ord == 10
    assert p.limit == 50
    assert p.lang == "deu"


def test_parse_window_params_invalid_from() -> None:
    with pytest.raises(BadRequestError):
        parse_window_params({"from": "x"})


def test_parse_window_params_negative_from() -> None:
    with pytest.raises(BadRequestError):
        parse_window_params({"from": "-1"})


def test_parse_window_params_invalid_limit() -> None:
    with pytest.raises(BadRequestError):
        parse_window_params({"limit": "nope"})


def test_parse_window_params_limit_zero() -> None:
    with pytest.raises(BadRequestError):
        parse_window_params({"limit": "0"})


def test_parse_window_params_limit_over_max() -> None:
    with pytest.raises(BadRequestError):
        parse_window_params({"limit": "1001"})


def test_parse_limit_only_defaults() -> None:
    assert parse_limit_only({}) == 200


def test_parse_limit_only_invalid() -> None:
    with pytest.raises(BadRequestError):
        parse_limit_only({"limit": "0"})


def test_empty_window_response_basic() -> None:
    from minerva.reader.window import WindowParams, empty_window_response

    params = WindowParams(from_ord=5, limit=20, lang="deu")
    out = empty_window_response(42, params)
    assert out == {
        "work_id": 42,
        "lang": "deu",
        "from": 5,
        "limit": 20,
        "by_chunk": {},
    }


def test_empty_window_response_extra() -> None:
    from minerva.reader.window import WindowParams, empty_window_response

    params = WindowParams(from_ord=0, limit=200, lang="grc")
    out = empty_window_response(1, params, extra={"lemma": "logos"})
    assert out["lemma"] == "logos"
    assert out["by_chunk"] == {}
