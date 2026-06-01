"""Shared reader-window helpers — pagination params and chunk-id lookup.

Every windowed-map endpoint (term occurrences, xref map, lemma
highlights) scopes its join to the chunks the reader just rendered.
This module centralises the ``from`` / ``limit`` / ``lang`` parsing
and the ``SELECT chunk_id FROM chunks_full … LIMIT ? OFFSET ?`` query
so the three query modules stay DRY.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from typing import Any

from ..errors import BadRequestError


@dataclasses.dataclass(frozen=True)
class WindowParams:
    from_ord: int
    limit: int
    lang: str


def parse_window_params(
    query: dict[str, str],
    *,
    default_limit: int = 200,
    max_limit: int = 1000,
    default_lang: str = "grc",
) -> WindowParams:
    """Parse ``from``, ``limit``, and ``lang`` from a query string dict.

    Raises ``_HTTPError`` (400) on malformed or out-of-range values.
    """

    lang = query.get("lang", default_lang)
    try:
        from_ord = int(query.get("from", "0"))
    except ValueError:
        raise BadRequestError(
            "invalid 'from' query param",
        ) from None
    try:
        limit = int(query.get("limit", str(default_limit)))
    except ValueError:
        raise BadRequestError(
            "invalid 'limit' query param",
        ) from None
    if from_ord < 0:
        raise BadRequestError("'from' must be >= 0")
    if limit <= 0 or limit > max_limit:
        raise BadRequestError(
            f"'limit' must be in 1..{max_limit}",
        )
    return WindowParams(from_ord=from_ord, limit=limit, lang=lang)


def parse_limit_only(
    query: dict[str, str],
    *,
    default_limit: int = 200,
    max_limit: int = 1000,
) -> int:
    """Parse ``limit`` alone — used by ``work_range`` which has custom
    ``from`` / ``around`` handling."""

    try:
        limit = int(query.get("limit", str(default_limit)))
    except ValueError:
        raise BadRequestError(
            "invalid 'limit' query param",
        ) from None
    if limit <= 0 or limit > max_limit:
        raise BadRequestError(
            f"'limit' must be in 1..{max_limit}",
        )
    return limit


def fetch_chunk_ids_in_window(
    conn: sqlite3.Connection,
    work_id: int | str,
    lang: str,
    from_ord: int,
    limit: int,
) -> list[str]:
    """Return chunk_ids for one (work_id, lang) window, ordered by ``ord``."""

    conn.row_factory = sqlite3.Row
    chunk_rows = conn.execute(
        "SELECT chunk_id FROM chunks_full "
        "WHERE work_id = ? AND lang = ? "
        "ORDER BY ord LIMIT ? OFFSET ?",
        (work_id, lang, limit, from_ord),
    ).fetchall()
    return [r["chunk_id"] for r in chunk_rows]


def empty_window_response(
    work_id: int | str,
    params: WindowParams,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Standard empty payload when a window has no chunks."""

    out: dict[str, Any] = {
        "work_id": work_id,
        "lang": params.lang,
        "from": params.from_ord,
        "limit": params.limit,
        "by_chunk": {},
    }
    if extra:
        out.update(extra)
    return out
