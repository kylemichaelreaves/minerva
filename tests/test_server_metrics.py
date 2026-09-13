"""Request timing recorded through the real dispatch path."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
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
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
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
    row = metrics_conn.execute(
        "SELECT label, method, kind FROM request_timings"
    ).fetchone()
    assert row == ("works list", "GET", "total")


def test_recorder_survives_a_handler_exception(populated_db, metrics_conn):
    deps = make_deps(populated_db, StubBackend(reply="ok"))
    deps.metrics = Recorder(metrics_conn)
    with pytest.raises(ValueError), deps.metrics.record("work range", "GET"):
        raise ValueError("handler blew up")
    assert metrics_conn.execute(
        "SELECT status_class FROM request_timings"
    ).fetchone()[0] == 5


def test_sse_stream_marks_time_to_first_event(populated_db):
    """`_send_sse` calls the public `current_span()`, not the private
    `_CURRENT`, to mark time-to-first-event on a real streaming chat
    request. Drives a real `ThreadingHTTPServer` (see test_server_csrf.py)
    because the wiring under test is transport-level: `_send_sse` runs on
    a request-handling thread, and `current_span()` must see the same
    contextvar the dispatch site set.
    """

    deps = make_deps(populated_db, StubBackend(reply="Hello world [1]."))
    # Cross-thread-safe reopens, matching serve_cmd.py's check_same_thread=False.
    # These are NEW connections (the conftest-supplied originals are closed
    # by their own fixtures/teardown regardless of what `deps.*` points at
    # afterwards) — close them ourselves in `finally`, per #246.
    reopened_conn = store_mod.open_db(_path_of(deps.conn), check_same_thread=False)
    reopened_conv_conn = conversations_mod.open_db(
        _path_of(deps.conversations_conn), check_same_thread=False
    )
    reopened_trans_conn = translations_mod.open_db(
        _path_of(deps.translations_conn), check_same_thread=False
    )
    deps.conn = reopened_conn
    deps.conversations_conn = reopened_conv_conn
    deps.translations_conn = reopened_trans_conn
    metrics_conn = sqlite3.connect(":memory:", check_same_thread=False)
    metrics_conn.executescript(m.SCHEMA)
    metrics_lock = threading.Lock()
    deps.metrics = Recorder(metrics_conn, metrics_lock)

    try:
        with _running(deps) as base:
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

        # `ThreadingHTTPServer.daemon_threads` is True, so `server_close()`
        # (inside `_running`'s `finally`) does not join the request-handling
        # thread — the `ttfe` row is written there, potentially after this
        # thread's read loop above already broke out. Poll for it instead of
        # relying on `shutdown()`'s incidental ~0.5s cushion.
        deadline = time.monotonic() + 1.0
        row = None
        while row is None and time.monotonic() < deadline:
            # Same lock the Recorder writes under — reading `metrics_conn`
            # from this thread without it is the exact cross-thread race
            # `metrics_lock` exists to prevent.
            with metrics_lock:
                row = metrics_conn.execute(
                    "SELECT count FROM request_timings WHERE kind = 'ttfe'"
                ).fetchone()
            if row is None:
                time.sleep(0.01)
        assert row == (1,)
    finally:
        reopened_conn.close()
        reopened_conv_conn.close()
        reopened_trans_conn.close()
        metrics_conn.close()
