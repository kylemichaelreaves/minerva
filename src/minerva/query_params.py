"""Shared HTTP query-string parsing helpers."""

from __future__ import annotations

from .errors import BadRequestError


def escape_like_substring(value: str) -> str:
    """Escape ``%`` and ``_`` for use in a SQL ``LIKE`` pattern."""

    return value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def parse_int_param(
    query: dict[str, str],
    name: str,
    default: int,
    *,
    lo: int | None = None,
    hi: int | None = None,
    clamp: bool = False,
) -> int:
    """Parse one integer query param with optional bounds.

    When ``clamp`` is true, out-of-range values are pinned to ``lo`` /
    ``hi`` instead of raising ``BadRequestError``.
    """

    raw = query.get(name)
    if raw is None or raw == "":
        value = default
    else:
        try:
            value = int(raw)
        except ValueError:
            raise BadRequestError(f"invalid '{name}' query param") from None
    if lo is not None and value < lo:
        if clamp:
            value = lo
        else:
            raise BadRequestError(f"'{name}' must be >= {lo}")
    if hi is not None and value > hi:
        if clamp:
            value = hi
        else:
            raise BadRequestError(f"'{name}' must be <= {hi}")
    return value
