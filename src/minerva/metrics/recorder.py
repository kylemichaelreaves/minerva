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
import sqlite3
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from typing import Any

from .store import Sample, write

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

    __slots__ = ("_clock", "_subs", "_t0", "_ttfe_ms", "label", "method", "status")

    def __init__(self, label: str, method: str, clock: Callable[[], float]) -> None:
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

    @contextlib.contextmanager
    def record(self, label: str, method: str) -> Iterator[Span]:
        span = Span(label, method, self._clock)
        token = _CURRENT.set(span)
        try:
            yield span
        except BaseException:
            span.status = 500
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
        with self._lock:
            write(self._conn, samples)

    def recent(self) -> list[dict[str, Any]]:
        """Most recent requests, oldest first. In-memory only; lost on restart."""

        return list(self._ring)


__all__ = ["Recorder", "Span", "current_span", "sub_span"]
