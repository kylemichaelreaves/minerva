"""Read endpoints over the request-timing store.

Granularity is derived here rather than stored. Summing the histogram
columns is what lets the quantiles survive the regrouping — the reason
the store keeps buckets instead of raw rows.
"""

from __future__ import annotations

import time
from http import HTTPStatus
from typing import Any

from ...metrics import store as metrics_store
from ..server_core import ServerDeps, _HTTPError

_WINDOWS: dict[str, int | None] = {
    "1h": 3_600,
    "6h": 21_600,
    "24h": 86_400,
    "7d": 604_800,
    "30d": 2_592_000,
    "all": None,
}

# Granularity thresholds, in seconds of window span.
_SIX_HOURS = 21_600
_SEVEN_DAYS = 604_800


def _parse_window(value: str) -> int | None:
    """Seconds for a named window, or None for 'all'."""

    if value not in _WINDOWS:
        allowed = ", ".join(_WINDOWS)
        raise _HTTPError(HTTPStatus.BAD_REQUEST, f"window must be one of: {allowed}")
    return _WINDOWS[value]


def _bucket_seconds_for(span_seconds: int) -> int:
    if span_seconds <= _SIX_HOURS:
        return metrics_store.BUCKET_SECONDS
    if span_seconds <= _SEVEN_DAYS:
        return 3_600
    return 86_400


def _parse_offset(value: str | None) -> int:
    """Whole windows to shift the range back; 0 (the default) ends now.

    `isascii()` guards `isdigit()`: superscript two is a digit by
    `str.isdigit()` but not by `int()`, which would raise ValueError and
    escape as a 500 rather than the 400 this is here to produce.
    """

    if value is None:
        return 0
    if not (value.isascii() and value.isdigit()):
        raise _HTTPError(HTTPStatus.BAD_REQUEST, "offset must be a non-negative integer")
    return int(value)


def _range(qs: dict[str, str]) -> tuple[float, float, str]:
    name = qs.get("window", "24h")
    width = _parse_window(name)
    offset = _parse_offset(qs.get("offset"))
    if width is None:
        # `all` starts at the epoch, so there is no previous window to
        # shift to. Ignoring the offset silently would hand the caller the
        # rows it already had and let it render a 0% delta as a measured
        # one.
        if offset:
            raise _HTTPError(HTTPStatus.BAD_REQUEST, "offset is not valid for window=all")
        return 0.0, time.time(), name
    until = time.time() - width * offset
    return until - width, until, name


def _handle_metrics_summary(deps: ServerDeps, qs: dict[str, str]) -> dict[str, Any]:
    since, until, name = _range(qs)
    label = qs.get("label") or None
    # `--no-metrics` leaves no connection. Render an empty page rather than
    # 500ing: persistence being off is a configuration, not an error.
    if deps.metrics_conn is None:
        rows: list[dict[str, Any]] = []
    else:
        # The Recorder writes to this connection from other worker threads.
        with deps.metrics_lock:
            rows = metrics_store.summary(
                deps.metrics_conn, since=since, until=until, label=label
            )
    return {
        "window": name,
        "since": since,
        "until": until,
        "rows": rows,
        # Additive (#615-era `health`): three states used to render identically
        # as an empty page — no traffic, metrics switched off, and every write
        # failing. `persisting` separates the second; `write_failures` the
        # third. Existing consumers ignore the key.
        "health": {
            "write_failures": deps.metrics.write_failures,
            "persisting": deps.metrics_conn is not None,
        },
    }


def _parse_limit(raw: str | None) -> int:
    """A junk `limit` is a 400, not a silently-ignored default.

    Ignoring it would answer a question the caller did not ask and look like
    a small table rather than a rejected parameter.
    """

    if raw is None or raw == "":
        return 200
    try:
        return int(raw)
    except ValueError:
        raise _HTTPError(HTTPStatus.BAD_REQUEST, f"limit is not a number: {raw!r}") from None


def _handle_metrics_requests(deps: ServerDeps, qs: dict[str, str]) -> dict[str, Any]:
    """Per-request rows (#619's `request_spans`), newest first.

    The aggregate endpoints answer "how is this route behaving"; a 5-minute
    bucket mixes requests, so it cannot answer "which request was slow, and
    where did its time go". This one can.
    """

    since, until, name = _range(qs)
    limit = _parse_limit(qs.get("limit"))
    if deps.metrics_conn is None:
        rows: list[dict[str, Any]] = []
    else:
        with deps.metrics_lock:
            rows = metrics_store.requests(
                deps.metrics_conn,
                since=since,
                until=until,
                label=qs.get("label") or None,
                method=qs.get("method") or None,
                errors_only=qs.get("errors") in ("1", "true"),
                phased_only=qs.get("phased") in ("1", "true"),
                limit=limit,
            )
    return {
        "window": name,
        "since": since,
        "until": until,
        "rows": rows,
        # The CLAMPED limit, not what was asked for: a caller requesting
        # 100,000 rows should see it got 500, not infer a small table.
        "limit": max(1, min(limit, metrics_store.REQUESTS_MAX_LIMIT)),
    }


def _handle_metrics_series(deps: ServerDeps, qs: dict[str, str]) -> dict[str, Any]:
    label = qs.get("label")
    if not label:
        raise _HTTPError(HTTPStatus.BAD_REQUEST, "label is required")
    since, until, _ = _range(qs)
    bucket_seconds = _bucket_seconds_for(int(until - since))
    kind = qs.get("kind", "total")
    span = qs.get("span", "")
    if deps.metrics_conn is None:
        points: list[dict[str, Any]] = []
    else:
        with deps.metrics_lock:
            points = metrics_store.series(
                deps.metrics_conn,
                label=label, kind=kind, span=span,
                since=since, until=until, bucket_seconds=bucket_seconds,
            )
    return {
        "label": label,
        "kind": kind,
        "span": span,
        "bucket_seconds": bucket_seconds,
        "points": points,
    }


__all__ = ["_handle_metrics_requests", "_handle_metrics_series", "_handle_metrics_summary"]
