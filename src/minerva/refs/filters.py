"""Cross-reference visibility filter parsing."""

from __future__ import annotations

from typing import Any

from ..errors import BadRequestError

# Status filter that excludes 'rejected' by default. Built dynamically so
# the include_rejected query param can toggle 'rejected' on without
# duplicating the SQL.
_DEFAULT_VISIBLE_STATUSES = ("approved", "manual", "auto")
_ALL_STATUSES = ("approved", "manual", "auto", "rejected")


def parse_filters(query: dict[str, str]) -> tuple[tuple[str, ...], float]:
    """Parse the shared visibility filters from the query string.

    Returns ``(statuses, min_confidence)`` where ``statuses`` is the
    tuple of curator_status values to include. Raises ``_HTTPError`` on
    a malformed ``min_confidence``."""

    if query.get("include_rejected") in {"1", "true", "True"}:
        statuses = _ALL_STATUSES
    else:
        statuses = _DEFAULT_VISIBLE_STATUSES

    raw_min = query.get("min_confidence")
    if raw_min is None:
        min_confidence = 0.8
    else:
        try:
            min_confidence = float(raw_min)
        except ValueError:
            raise BadRequestError(
                "invalid 'min_confidence' query param",
            ) from None
        if not (0.0 <= min_confidence <= 1.0):
            raise BadRequestError(
                "'min_confidence' must be in 0..1",
            )

    return statuses, min_confidence


def parse_limit_offset(
    query: dict[str, str],
    *,
    default_limit: int,
    max_limit: int,
) -> tuple[int, int]:
    """Parse ``limit`` and ``offset`` from a query string dict."""

    try:
        limit = int(query.get("limit", str(default_limit)))
    except ValueError:
        raise BadRequestError("invalid 'limit' query param") from None
    if limit <= 0 or limit > max_limit:
        raise BadRequestError(f"'limit' must be in 1..{max_limit}")

    try:
        offset = int(query.get("offset", "0"))
    except ValueError:
        raise BadRequestError("invalid 'offset' query param") from None
    if offset < 0:
        raise BadRequestError("'offset' must be >= 0")
    return limit, offset


def status_clause(statuses: tuple[str, ...], min_confidence: float) -> tuple[str, list[Any]]:
    """Compose the SQL fragment + params for the standard visibility
    filter: ``approved`` / ``manual`` always visible; ``auto`` rows
    visible only when confidence >= threshold."""

    parts: list[str] = []
    params: list[Any] = []
    pass_through = [s for s in statuses if s in ("approved", "manual")]
    if pass_through:
        placeholders = ",".join("?" * len(pass_through))
        parts.append(f"xr.curator_status IN ({placeholders})")
        params.extend(pass_through)
    if "auto" in statuses:
        parts.append("(xr.curator_status = 'auto' AND xr.confidence >= ?)")
        params.append(min_confidence)
    if "rejected" in statuses:
        parts.append("xr.curator_status = 'rejected'")
    if not parts:
        return ("0", [])
    return ("(" + " OR ".join(parts) + ")", params)
