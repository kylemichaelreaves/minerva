"""The timing context manager used at each `do_*` dispatch site.

One context manager per site rather than a unified dispatcher. The four
`do_*` methods diverge on cross-origin checks, rate limiting, body parsing
and response shape; folding them into one function means four or five
boolean flags, which is the shape that drove #559's cognitive complexity
to 29 while local coverage stayed green.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import secrets
import sqlite3
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from typing import Any

from .store import RequestRow, Sample, write_request

_log = logging.getLogger(__name__)

# Per-thread by construction: each thread gets its own top-level Context,
# which is what makes this safe under ThreadingHTTPServer. Threading the
# span through every handler signature would be the alternative.
_CURRENT: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
    "minerva_metrics_span", default=None
)


def current_span() -> Span | None:
    """The request being timed on this thread, or None outside one.

    Public because `_send_sse` needs it to mark time-to-first-event and
    must not reach for a private module global.
    """

    return _CURRENT.get()


class Span:
    """One in-flight request. Mutable; the dispatch site sets `status`."""

    __slots__ = ("_clock", "_subs", "_t0", "_ttfe_ms", "id", "label", "method", "status")

    def __init__(self, label: str, method: str, clock: Callable[[], float]) -> None:
        # Random, not a counter: a counter restarts at the same value in the
        # next process, so ids would collide across restarts — and this id is
        # the key of a durable table that outlives any one process.
        # `token_hex` over `uuid4` on measurement: 0.684 vs 1.253 us.
        self.id = secrets.token_hex(8)
        self.label = label
        self.method = method
        self.status = 200
        self._clock = clock
        self._t0 = clock()
        self._ttfe_ms: float | None = None
        self._subs: list[tuple[str, float]] = []

    def elapsed_ms(self) -> float:
        return (self._clock() - self._t0) * 1000.0

    def first_event(self) -> None:
        """Mark time-to-first-event. Called from every SSE write; only the
        first call counts, because that is the number that means anything."""

        if self._ttfe_ms is None:
            self._ttfe_ms = self.elapsed_ms()

    def add_sub(self, name: str, ms: float) -> None:
        self._subs.append((name, ms))


@contextlib.contextmanager
def sub_span(name: str, *, clock: Callable[[], float] = time.perf_counter) -> Iterator[None]:
    """Time a named step inside the active request. A no-op with no request
    in flight, so the same code path stays usable from the CLI."""

    span = _CURRENT.get()
    if span is None:
        yield
        return
    t0 = clock()
    try:
        yield
    finally:
        span.add_sub(name, (clock() - t0) * 1000.0)


class Recorder:
    """Owns the metrics connection, its lock, and the recent-request ring.

    `conn=None` records to the ring only. That is the `ServerDeps` default,
    so existing tests need no change and no dispatch site needs a guard.
    """

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        lock: threading.Lock | None = None,
        *,
        ring_size: int = 200,
        now: Callable[[], float] = time.time,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._conn = conn
        self._lock = lock or threading.Lock()
        self._ring: deque[dict[str, Any]] = deque(maxlen=ring_size)
        self._now = now
        self._clock = clock
        self._write_failures = 0
        self._write_failure_logged = False

    @contextlib.contextmanager
    def record(
        self,
        label: str,
        method: str,
        *,
        error_status: Callable[[BaseException], int] | None = None,
    ) -> Iterator[Span]:
        """Time one request, recording it on the way out however it ends.

        `error_status` maps a failing exception to the status the client
        is actually going to receive, so a handler that raises a 404 or a
        400 is not filed under `status_class = 5`. It is a callable rather
        than a mapping table because the translation is the HTTP layer's
        (`serve._route_error_status`); this module must not import HTTP
        types. Without it a failure records 500, which is what a caller
        with no error translation of its own means.
        """

        span = Span(label, method, self._clock)
        token = _CURRENT.set(span)
        try:
            yield span
        except BaseException as exc:
            span.status = 500 if error_status is None else error_status(exc)
            raise
        finally:
            _CURRENT.reset(token)
            self._finish(span)

    def _finish(self, span: Span) -> None:
        total_ms = span.elapsed_ms()
        at = self._now()
        status_class = span.status // 100
        samples = [
            Sample(at, span.label, span.method, "total", "", status_class, total_ms)
        ]
        if span._ttfe_ms is not None:
            samples.append(
                Sample(at, span.label, span.method, "ttfe", "", status_class, span._ttfe_ms)
            )
        samples.extend(
            Sample(at, span.label, span.method, "total", name, status_class, ms)
            for name, ms in span._subs
        )
        self._ring.append(
            {
                "at": at,
                "label": span.label,
                "method": span.method,
                "status": span.status,
                "ms": total_ms,
                "subs": list(span._subs),
            }
        )
        if self._conn is None:
            return
        row = RequestRow(
            id=span.id,
            at=at,
            label=span.label,
            method=span.method,
            # The FULL status, not `status_class`. The aggregate keeps the
            # class; a per-request row that also collapsed 404 into 4 would
            # answer fewer questions than the table it exists to refine.
            status=span.status,
            total_ms=total_ms,
            accounted_ms=sum(ms for _, ms in span._subs),
            phases=list(span._subs),
        )
        try:
            with self._lock:
                write_request(self._conn, samples, row)
        except sqlite3.Error:
            self._note_write_failure()

    def _note_write_failure(self) -> None:
        """Drop the sample instead of failing the request that produced it.

        A full disk, a `data/metrics.sqlite` held in a write transaction by
        another process, a corrupt file or a read-only filesystem would
        otherwise raise out of `record()`'s `finally` at every dispatch
        site — *inside* the route's `except Exception`, which answers 500
        for a request that succeeded. Losing a timing sample is strictly
        better than losing the server.

        The second consequence this docstring used to name — that on the
        streaming path it "writes a second response onto a connection whose
        SSE body was already flushed" — no longer follows: since #608 the
        route's error path checks `_response_begun` and logs instead of
        answering. The first consequence still stands, which is why this
        guard stays.

        Logged once per Recorder: a full disk fails on every request, and
        one line per request would bury the rest of the log.

        COUNTED every time, though, and the two are separate on purpose. A
        boolean latch — which this was — cannot tell "one failure hours ago"
        from "failing on every request right now", and that difference is the
        whole signal. `write_failures` is surfaced through
        /api/metrics/summary so an empty page can say which it is.
        """

        self._write_failures += 1
        if self._write_failure_logged:
            return
        self._write_failure_logged = True
        _log.warning(
            "metrics write failed; dropping timing samples (further failures are silent)",
            exc_info=True,
        )

    @property
    def write_failures(self) -> int:
        """How many samples have been dropped because the write failed."""

        return self._write_failures

    def recent(self) -> list[dict[str, Any]]:
        """Most recent requests, oldest first. In-memory only; lost on restart."""

        return list(self._ring)


__all__ = ["Recorder", "Span", "current_span", "sub_span"]
