"""Tests for refs/filters.py pagination helper."""

from __future__ import annotations

import pytest

from minerva.errors import BadRequestError
from minerva.refs.filters import parse_limit_offset


def test_parse_limit_offset_defaults() -> None:
    limit, offset = parse_limit_offset({}, default_limit=100, max_limit=500)
    assert limit == 100
    assert offset == 0


def test_parse_limit_offset_custom() -> None:
    limit, offset = parse_limit_offset(
        {"limit": "25", "offset": "10"},
        default_limit=100,
        max_limit=500,
    )
    assert limit == 25
    assert offset == 10


def test_parse_limit_offset_review_defaults() -> None:
    limit, offset = parse_limit_offset({}, default_limit=50, max_limit=200)
    assert limit == 50
    assert offset == 0


def test_parse_limit_offset_invalid_limit() -> None:
    with pytest.raises(BadRequestError):
        parse_limit_offset({"limit": "x"}, default_limit=100, max_limit=500)


def test_parse_limit_offset_limit_zero() -> None:
    with pytest.raises(BadRequestError):
        parse_limit_offset({"limit": "0"}, default_limit=100, max_limit=500)


def test_parse_limit_offset_limit_over_max() -> None:
    with pytest.raises(BadRequestError):
        parse_limit_offset({"limit": "501"}, default_limit=100, max_limit=500)


def test_parse_limit_offset_invalid_offset() -> None:
    with pytest.raises(BadRequestError):
        parse_limit_offset({"offset": "bad"}, default_limit=100, max_limit=500)


def test_parse_limit_offset_negative_offset() -> None:
    with pytest.raises(BadRequestError):
        parse_limit_offset({"offset": "-1"}, default_limit=100, max_limit=500)
