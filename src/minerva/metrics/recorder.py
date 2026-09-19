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
# CPU time comes from `thread_time`, which is scoped to the calling thread.
# NOT `process_time`: that is process-wide, and this server runs one thread per
# request, so a span would absorb every concurrent request's CPU. Measured with
# three neighbours, a span using 12.5 ms of CPU reported 56.5 ms — and the error
# is directional, turning a WAITING phase into a CPU-bound one exactly when the
# server is busy.
#
# `thread_time` is not on every platform. Absent, CPU capture turns off; it does
# NOT fall back to `process_time`, because a confidently wrong number is worse
# here than no number.
_THREAD_TIME: Callable[[], float] | None = getattr(time, "thread_time", None)


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

    __slots__ = (
        "_clock", "_cpu0", "_subs", "_subs_cpu", "_t0", "_ttfe_ms",
        "id", "label", "method", "sql_prefix", "sqlite_ms", "sqlite_queries",
        "status",
    )

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
        # Parallel to `_subs`, keyed by name, rather than widening the tuple:
        # every consumer of `_subs` unpacks exactly two elements, and the
        # backward-compatibility constraint rules a third out.
        self._subs_cpu: dict[str, float] = {}
        self._cpu0: float | None = _THREAD_TIME() if _THREAD_TIME else None
        # Database time is a sum over many DISJOINT intervals, not one
        # contiguous phase — which is why it is its own field rather than a
        # `sub_span`. Putting it in `phases` would make the waterfall's
        # ordering a lie.
        self.sqlite_ms: float = 0.0
        self.sqlite_queries: int = 0
        # Built ONCE, here, and reused for every statement this request
        # issues. Interpolating a fresh id per query would make each statement
        # a distinct SQL string and defeat Python's prepared-statement cache:
        # measured at 5.88x on a point lookup (0.59 -> 3.49 us). Constant
        # within a request, repeated shapes still hit the cache.
        self.sql_prefix: str = f"/*request_id='{self.id}'*/ "

    def elapsed_ms(self) -> float:
        return (self._clock() - self._t0) * 1000.0

    @property
    def cpu_ms(self) -> float | None:
        """CPU this request's thread has used, or None when unmeasurable.

        None and 0.0 are different answers — "not measured" versus "measured,
        and it was idle" — and a reader cannot tell them apart if both render
        as zero. Callers must preserve the distinction.
        """

        if self._cpu0 is None or _THREAD_TIME is None:
            return None
        return (_THREAD_TIME() - self._cpu0) * 1000.0

    def add_db(self, ms: float) -> None:
        """Accumulate one statement's duration. Called from the connection
        layer, so no handler has to know it is being measured."""

        self.sqlite_ms += ms
        self.sqlite_queries += 1

    def add_sub_cpu(self, name: str, ms: float) -> None:
        self._subs_cpu[name] = self._subs_cpu.get(name, 0.0) + ms

    def first_event(self) -> None:
        """Mark time-to-first-event. Called from every SSE write; only the
        first call counts, because that is the number that means anything."""

        if self._ttfe_ms is None:
            self._ttfe_ms = self.elapsed_ms()

    def add_sub(self, name: str, ms: float) -> None:
        self._subs.append((name, ms))


@contextlib.contextmanager
def sub_span(
    name: str,
    *,
    clock: Callable[[], float] | None = None,
    cpu_clock: Callable[[], float] | None = None,
) -> Iterator[None]:
    """Time a named step inside the active request, in wall AND cpu time.

    A no-op with no request in flight, so the same code path stays usable from
    the CLI.

    Both clocks default to None and are resolved HERE rather than in the
    signature. A default bound in the signature is evaluated at import, so
    monkeypatching `time.perf_counter` afterwards never reached it — which is
    the trap the audit recorded and Phase 1 deferred to this phase.

    One limitation, stated rather than hidden: `llm_call` wraps a generator
    that yields across `_send_sse`'s loop, so on a streaming call the consumer
    runs on this same thread between yields and its work lands in this span's
    `cpu_ms`. Thread-scoped CPU cannot separate them. The wall time is exact;
    the CPU time is an upper bound for that one span.
    """

    span = _CURRENT.get()
    if span is None:
        yield
        return
    wall = clock or time.perf_counter
    cpu = cpu_clock or _THREAD_TIME
    t0 = wall()
    c0 = cpu() if cpu else None
    try:
        yield
    finally:
        span.add_sub(name, (wall() - t0) * 1000.0)
        if cpu is not None and c0 is not None:
            span.add_sub_cpu(name, (cpu() - c0) * 1000.0)


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
            phase_cpu=dict(span._subs_cpu),
            cpu_ms=span.cpu_ms,
            sqlite_ms=span.sqlite_ms,
            sqlite_queries=span.sqlite_queries,
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
