"""Request timing recorded through the real dispatch path."""

from __future__ import annotations

import json
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from conftest import StubBackend, make_deps

from minerva import conversations as conversations_mod
from minerva import store as store_mod
from minerva import translations as translations_mod
from minerva.http.serve import make_handler
from minerva.metrics import store as m
from minerva.metrics.recorder import Recorder


@pytest.fixture
def metrics_conn():
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    yield c
    c.close()


def _path_of(conn: sqlite3.Connection) -> Path:
    """The file a connection is attached to (see test_server_csrf.py)."""

    return Path(str(conn.execute("PRAGMA database_list").fetchone()[2]))


@contextmanager
def _running(deps: object) -> Iterator[str]:
    """Serve *deps* on an ephemeral port for the duration of the block."""

    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(deps))
    # shutdown() blocks until serve_forever next polls; the 0.5s default
    # made every test using this fixture cost half a second of sleep.
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def test_deps_default_recorder_is_inert(populated_db):
    # Every existing test constructs deps without metrics; that must stay
    # a no-op rather than requiring each of them to be updated.
    deps = make_deps(populated_db, StubBackend(reply="ok"))
    assert deps.metrics.recent() == []


def test_get_route_records_a_sample(populated_db, metrics_conn):
    deps = make_deps(populated_db, StubBackend(reply="ok"))
    deps.metrics = Recorder(metrics_conn)
    with deps.metrics.record("works list", "GET") as span:
        span.status = 200
    # Selected by kind: a request now also writes a `cpu` row, so the first
    # row returned is no longer guaranteed to be the one this asserts on.
    row = metrics_conn.execute(
        "SELECT label, method, kind FROM request_timings WHERE kind = 'total'"
    ).fetchone()
    assert row == ("works list", "GET", "total")


def test_recorder_survives_a_handler_exception(populated_db, metrics_conn):
    deps = make_deps(populated_db, StubBackend(reply="ok"))
    deps.metrics = Recorder(metrics_conn)
    with pytest.raises(ValueError), deps.metrics.record("work range", "GET"):
        raise ValueError("handler blew up")
    assert metrics_conn.execute("SELECT status_class FROM request_timings").fetchone()[0] == 5


class FailingMetricsConn:
    """A metrics connection that cannot be written to.

    Stands in for the real triggers — a full disk, `data/metrics.sqlite`
    held in a write transaction by another process, a corrupt file, a
    read-only filesystem. `store.write` opens `with conn:` before it calls
    `executemany`, so both halves are stubbed here.
    """

    def __enter__(self) -> FailingMetricsConn:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def executemany(self, *args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError("database or disk is full")


@contextmanager
def _serving_with_metrics(
    populated_db: sqlite3.Connection,
    backend: StubBackend,
    recorder: Recorder,
    *,
    metrics_conn: sqlite3.Connection | None = None,
) -> Iterator[str]:
    """Serve *populated_db* on an ephemeral port with *recorder* wired in.

    The request is handled on another thread, so the three application
    connections are reopened with `check_same_thread=False`, matching
    `serve_cmd.py`. Those are NEW handles (the conftest-supplied originals
    are closed by their own fixtures regardless of what `deps.*` points at
    afterwards), so this closes them itself, per #246.

    *metrics_conn* is what the read endpoints query; it is deliberately
    separate from whatever connection the Recorder writes to, because the
    failure tests below give the Recorder one that raises.
    """

    deps = make_deps(populated_db, backend)
    reopened = [
        store_mod.open_db(_path_of(deps.conn), check_same_thread=False),
        conversations_mod.open_db(_path_of(deps.conversations_conn), check_same_thread=False),
        translations_mod.open_db(_path_of(deps.translations_conn), check_same_thread=False),
    ]
    deps.conn, deps.conversations_conn, deps.translations_conn = reopened
    deps.metrics = recorder
    deps.metrics_conn = metrics_conn
    try:
        with _running(deps) as base:
            yield base
    finally:
        for conn in reopened:
            conn.close()


def _raw_exchange(base: str, request: bytes, until: bytes, grace: float = 1.0) -> bytes:
    """Send *request* verbatim and return every byte the server writes.

    urllib parses the FIRST response and stops, so a second status line on
    the same connection is invisible to it; this test has to count them,
    which means speaking the protocol directly.

    Reads to *until* and then keeps reading for *grace* seconds rather than
    to EOF: `_send_sse` sends `Connection: keep-alive`, which makes
    `BaseHTTPRequestHandler` hold the socket open for another request, so
    there is no EOF to wait for. A second response would be written on the
    same thread immediately after the stream ends.
    """

    host, port = base.removeprefix("http://").split(":")
    with socket.create_connection((host, int(port)), timeout=15) as sock:
        sock.sendall(request)
        buf = b""
        while until not in buf:
            chunk = sock.recv(65536)
            if not chunk:
                return buf
            buf += chunk
        sock.settimeout(grace)
        try:
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
        except TimeoutError:
            pass
    return buf


def _memory_metrics_conn() -> sqlite3.Connection:
    """An in-memory metrics DB the request-handling thread may also use —
    `check_same_thread=False`, matching `serve_cmd.py`. The caller closes it.
    """

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.executescript(m.SCHEMA)
    return conn


def _await_row(conn: sqlite3.Connection, lock: threading.Lock, sql: str) -> tuple | None:
    """Poll for a row the request-handling thread writes.

    `ThreadingHTTPServer.daemon_threads` is True, so `server_close()` does
    not join that thread — the sample can land after the client-side read
    already returned. Read under the Recorder's own lock: reading the
    connection from this thread without it is the exact cross-thread race
    the lock exists to prevent.
    """

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        with lock:
            row = conn.execute(sql).fetchone()
        if row is not None:
            return row
        time.sleep(0.01)
    return None


def test_a_failing_metrics_write_still_answers_the_request(populated_db):
    """C1: the metrics write happens in `record()`'s `finally`, inside the
    route's `except Exception`. Unguarded, a `sqlite3.OperationalError`
    there is translated into `{"error": "server error"}` and the client is
    told a request that SUCCEEDED failed — on every route at once, for as
    long as the disk stays full."""

    recorder = Recorder(FailingMetricsConn(), threading.Lock())  # type: ignore[arg-type]
    with (
        _serving_with_metrics(populated_db, StubBackend(reply="ok"), recorder) as base,
        urllib.request.urlopen(f"{base}/api/health", timeout=15) as resp,
    ):
        assert resp.status == 200
        assert json.loads(resp.read())["backend"] == "stub"
    # The sample is dropped, but the ring still has it: losing durable
    # history is the whole cost of the guard.
    assert [r["label"] for r in recorder.recent()] == ["health"]


def test_streaming_path_writes_one_status_line_when_metrics_fail(populated_db):
    """C2: the streaming branch `return`s from inside the `with`, so the
    metrics write runs at the `return`, still inside the `try`. When it
    raised, `_send_error_json` wrote a SECOND response onto a connection
    whose SSE body had already been flushed — `event: done` followed by
    `HTTP/1.0 500 Internal Server Error`."""

    recorder = Recorder(FailingMetricsConn(), threading.Lock())  # type: ignore[arg-type]
    backend = StubBackend(reply="Hello world [1].")
    with _serving_with_metrics(populated_db, backend, recorder) as base:
        body = json.dumps({"query": "What is justice?", "stream": True}).encode()
        raw = _raw_exchange(
            base,
            b"POST /api/chat HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Connection: close\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body,
            until=b"event: done",
        )
    assert raw.count(b"HTTP/1.") == 1, raw
    assert raw.startswith(b"HTTP/1.0 200 OK")
    assert b"event: done" in raw
    assert b"server error" not in raw


def test_a_client_error_is_recorded_as_status_class_4(populated_db):
    """I1: GET, PATCH and non-streaming POST reach a non-200 only by
    raising, so before `error_status` every 404 and 400 those verbs
    answered was stored as `status_class = 5` — the leaderboard's Errors
    column reading 100% for a route that is merely rejecting bad input.

    `/api/metrics/series` with no `label` is this branch's own 400."""

    metrics_conn = _memory_metrics_conn()
    lock = threading.Lock()
    recorder = Recorder(metrics_conn, lock)
    try:
        with _serving_with_metrics(
            populated_db, StubBackend(reply="ok"), recorder, metrics_conn=metrics_conn
        ) as base:
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(f"{base}/api/metrics/series", timeout=15)
            assert exc_info.value.code == 400
            # `HTTPError` IS the response object, and `pytest.raises` keeps it
            # alive past the block — without this the socket is only closed by
            # the GC, which surfaces as a ResourceWarning (#246).
            exc_info.value.close()
        row = _await_row(
            metrics_conn,
            lock,
            "SELECT label, method, status_class FROM request_timings",
        )
        assert row == ("metrics series", "GET", 4)
    finally:
        metrics_conn.close()


def test_sse_stream_marks_time_to_first_event(populated_db):
    """`_send_sse` calls the public `current_span()`, not the private
    `_CURRENT`, to mark time-to-first-event on a real streaming chat
    request. Drives a real `ThreadingHTTPServer` (see test_server_csrf.py)
    because the wiring under test is transport-level: `_send_sse` runs on
    a request-handling thread, and `current_span()` must see the same
    contextvar the dispatch site set.
    """

    metrics_conn = _memory_metrics_conn()
    metrics_lock = threading.Lock()
    recorder = Recorder(metrics_conn, metrics_lock)
    backend = StubBackend(reply="Hello world [1].")
    try:
        with _serving_with_metrics(populated_db, backend, recorder) as base:
            req = urllib.request.Request(
                f"{base}/api/chat",
                data=json.dumps({"query": "What is justice?", "stream": True}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                assert resp.status == 200
                # The response has no Content-Length or chunked framing (SSE
                # is unbounded), so `.read()` would block until the
                # connection closes. Read line-by-line until the terminal
                # event instead.
                for line in resp:
                    if line.startswith(b"event: done"):
                        break

        row = _await_row(
            metrics_conn,
            metrics_lock,
            "SELECT count FROM request_timings WHERE kind = 'ttfe'",
        )
        assert row == (1,)
    finally:
        metrics_conn.close()
