"""One request gets one response, even when the write fails (#597, #587, #588).

Three defects filed separately turned out to share a root cause: once any byte
of a response has been written, a later failure was still being answered with a
*second* full HTTP response on the same connection. On the JSON path that
surfaced as a `BrokenPipeError` traceback and a request logged twice (#597); on
the SSE path, as a status line and headers landing inside the event stream a
client was still reading (#587).

These drive a real `ThreadingHTTPServer` over a raw socket rather than
`urllib`, for two reasons: `urllib` parses one response and discards whatever
follows, which is exactly the byte range under test, and the disconnect case
needs an RST rather than a clean FIN.
"""

from __future__ import annotations

import json
import socket
import struct
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from conftest import StubBackend, make_deps
from test_server_references import _seed_two_refs

from minerva import conversations, store, translations
from minerva.http import serve as serve_mod
from minerva.http.serve import make_handler


def _path_of(conn: Any) -> Path:
    """The file a connection is attached to (see test_server_csrf.py)."""

    return Path(str(conn.execute("PRAGMA database_list").fetchone()[2]))


def _one_done_event():
    yield ("done", {"response": "ok"})


@pytest.fixture
def deps(populated_db):
    """`ServerDeps` whose connections are safe on the handler threads a real
    `ThreadingHTTPServer` dispatches on (see test_server_csrf.py)."""

    d = make_deps(populated_db, StubBackend(reply="Hello world"))
    d.conn = store.open_db(_path_of(d.conn), check_same_thread=False)
    d.conversations_conn = conversations.open_db(
        _path_of(d.conversations_conn), check_same_thread=False
    )
    d.translations_conn = translations.open_db(
        _path_of(d.translations_conn), check_same_thread=False
    )
    return d


class _RecordingServer(ThreadingHTTPServer):
    """Records what `socketserver` would otherwise only print to stderr.

    `handle_error` firing is the machine-readable form of "a traceback landed
    in an otherwise green run" — the symptom #597 reports.
    """

    def __init__(self, *args, **kwargs):
        self.errors: list[BaseException] = []
        super().__init__(*args, **kwargs)

    def handle_error(self, request, client_address):
        self.errors.append(sys.exception())


@contextmanager
def _running(deps: Any) -> Iterator[_RecordingServer]:
    srv = _RecordingServer(("127.0.0.1", 0), make_handler(deps))
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _send(srv: _RecordingServer, raw: bytes, *, read: bool = True) -> str:
    """Write *raw* to the server and read until EOF (or a 2s stall)."""

    s = socket.create_connection(("127.0.0.1", srv.server_address[1]), timeout=10)
    s.sendall(raw)
    if not read:
        return ""
    out: list[bytes] = []
    s.settimeout(2.0)
    try:
        while True:
            try:
                data = s.recv(65536)
            except TimeoutError:
                out.append(b"<NO EOF: connection still open>")
                break
            if not data:
                break
            out.append(data)
    finally:
        s.close()
    return b"".join(out).decode("utf-8", "replace")


def _chat_stream_request(body: bytes = b'{"query":"hi","stream":true}') -> bytes:
    return (
        b"POST /api/chat HTTP/1.1\r\nHost: 127.0.0.1\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    )


def _status_lines(wire: str) -> int:
    return wire.count("HTTP/1.")


# ---------- #587: a failure mid-stream must not start a second response ----------


def _raises_after_first_event():
    yield ("meta", {"citations": [], "abstained": False})
    raise RuntimeError("generator blew up mid-stream")


def _yields_unencodable_payload():
    yield ("meta", {"citations": [], "abstained": False})
    yield ("delta", {"text": object()})  # json.dumps fails inside _send_sse


@pytest.mark.parametrize(
    "generator",
    [_raises_after_first_event, _yields_unencodable_payload],
    ids=["generator raises", "unencodable event payload"],
)
def test_failure_mid_stream_writes_only_one_status_line(deps, monkeypatch, generator):
    monkeypatch.setattr(
        serve_mod, "_handle_chat_stream", lambda d, p, _g=generator: _g()
    )
    with _running(deps) as srv:
        wire = _send(srv, _chat_stream_request())
    assert _status_lines(wire) == 1, f"second HTTP response written into stream:\n{wire}"


def test_failure_mid_stream_ends_the_stream_with_an_error_event(deps, monkeypatch):
    """The client is mid-read; the only honest signal is an SSE error event."""

    monkeypatch.setattr(
        serve_mod, "_handle_chat_stream", lambda d, p: _raises_after_first_event()
    )
    with _running(deps) as srv:
        wire = _send(srv, _chat_stream_request())
    assert "event: error" in wire, wire
    payload = wire.split("event: error\ndata: ")[1].split("\n")[0]
    assert json.loads(payload) == {"error": "server error"}


# ---------- #597: a vanished client is not a server error ----------


def test_client_disconnect_mid_response_is_not_an_unhandled_error(deps):
    """The peer is gone before the headers flush — the response is moot.

    `SO_LINGER {1, 0}` makes close() send an RST rather than a FIN, which is
    what makes the server's next write fail rather than succeed into a buffer.
    """

    with _running(deps) as srv:
        s = socket.create_connection(("127.0.0.1", srv.server_address[1]), timeout=5)
        s.sendall(b"GET /api/works HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        s.close()
        # Let the handler thread reach its write and finish.
        for _ in range(100):
            if srv.errors:
                break
            threading.Event().wait(0.02)
    assert srv.errors == [], f"client disconnect escaped as a server error: {srv.errors}"


def test_broken_pipe_during_the_sse_body_is_swallowed(deps, monkeypatch):
    """The guard `_send_sse` already had, now actually exercised."""

    def _pipe_dies_after_first_event():
        yield ("meta", {"citations": [], "abstained": False})
        raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setattr(
        serve_mod, "_handle_chat_stream", lambda d, p: _pipe_dies_after_first_event()
    )
    with _running(deps) as srv:
        wire = _send(srv, _chat_stream_request())
    assert srv.errors == []
    assert _status_lines(wire) == 1
    assert "event: error" not in wire, "a gone peer cannot read an error event"


def test_write_failure_after_headers_does_not_start_a_second_response(deps, monkeypatch):
    """The JSON path's half of #597, isolated from the disconnect race.

    `ConnectionAbortedError` is a real `OSError` the socket can raise and is
    deliberately *not* one of the two the write guard swallows — so it reaches
    the route's `except Exception`, which is the clause that used to answer a
    committed response with a second one.
    """

    real_send_json = serve_mod.ChatHandler._send_json

    def _die_after_headers(self, status, body):
        real_send_json(self, status, body)
        raise ConnectionAbortedError(53, "Software caused connection abort")

    monkeypatch.setattr(serve_mod.ChatHandler, "_send_json", _die_after_headers)
    with _running(deps) as srv:
        wire = _send(srv, b"GET /api/works HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
    assert _status_lines(wire) == 1, f"second HTTP response after a committed one:\n{wire}"


# ---------- #588: the stream must release its thread and socket ----------


def test_sse_response_does_not_advertise_keep_alive(deps, monkeypatch):
    monkeypatch.setattr(
        serve_mod,
        "_handle_chat_stream",
        lambda d, p: _one_done_event(),
    )
    with _running(deps) as srv:
        wire = _send(srv, _chat_stream_request())
    headers = wire.split("\r\n\r\n")[0].lower()
    assert "connection: keep-alive" not in headers, (
        "HTTP/1.0 gives the client no framing to know the body ended; "
        f"inviting it to hold the connection pins a thread for `timeout`:\n{headers}"
    )


def test_sse_response_closes_the_connection_when_the_stream_ends(deps, monkeypatch):
    monkeypatch.setattr(
        serve_mod,
        "_handle_chat_stream",
        lambda d, p: _one_done_event(),
    )
    with _running(deps) as srv:
        wire = _send(srv, _chat_stream_request())
    assert "<NO EOF: connection still open>" not in wire, (
        "the server never closed the stream; the handler thread and its fd "
        "stay held until ChatHandler.timeout expires"
    )


# ---------- #583: do_PATCH through a real request ----------


def test_patch_reference_through_real_http(deps, populated_db):
    ids = _seed_two_refs(deps.conn)
    body = json.dumps({"curator_status": "approved"}).encode()
    with _running(deps) as srv:
        wire = _send(
            srv,
            b"PATCH /api/references/" + str(ids["plato_to_aristotle"]).encode()
            + b" HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body,
        )
    assert "200 OK" in wire, wire
    payload = json.loads(wire.split("\r\n\r\n", 1)[1])
    assert payload["id"] == ids["plato_to_aristotle"]
    assert payload["curator_status"] == "approved"
    row = deps.conn.execute(
        "SELECT curator_status FROM cross_references WHERE id=?",
        (ids["plato_to_aristotle"],),
    ).fetchone()
    assert row[0] == "approved"


def test_patch_unknown_route_404s_through_real_http(deps):
    body = b"{}"
    with _running(deps) as srv:
        wire = _send(
            srv,
            b"PATCH /api/nonesuch HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body,
        )
    assert "404 Not Found" in wire, wire
    assert json.loads(wire.split("\r\n\r\n", 1)[1])["error"] == "no route for /api/nonesuch"


# ---------- #583: do_PATCH's exception translation, and do_DELETE's ----------


@pytest.mark.parametrize(
    ("verb", "path", "body"),
    [
        ("PATCH", b"/api/references/1", b'{"curator_status": "approved"}'),
        ("DELETE", b"/api/conversations/whatever", b""),
    ],
    ids=["PATCH", "DELETE"],
)
def test_route_handler_exception_becomes_a_500(deps, monkeypatch, verb, path, body):
    """The half of `do_PATCH` #583 names as unverified: exception translation.

    A route that raises before anything is written must still get a clean
    single error response — the `_response_begun` branch must take the
    *other* fork from the one the disconnect tests exercise.
    """

    def _boom(*args, **kwargs):
        raise RuntimeError("handler blew up")

    monkeypatch.setattr(serve_mod, "_dispatch_json_mutation", _boom)
    monkeypatch.setattr(serve_mod, "_match_route", lambda p, routes: ("x route", _boom, ()))
    head = verb.encode() + b" " + path + b" HTTP/1.1\r\nHost: 127.0.0.1\r\n"
    if body:
        head += b"Content-Type: application/json\r\nContent-Length: " + str(
            len(body)
        ).encode() + b"\r\n"
    with _running(deps) as srv:
        wire = _send(srv, head + b"\r\n" + body)
    assert "500 Internal Server Error" in wire, wire
    assert _status_lines(wire) == 1
    assert json.loads(wire.split("\r\n\r\n", 1)[1])["error"] == "server error"


def test_sse_stream_records_time_to_first_event(deps, monkeypatch):
    """With a Recorder attached, `_send_sse` reports TTFE on the first write."""

    import sqlite3

    from minerva.metrics import store as m
    from minerva.metrics.recorder import Recorder

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.executescript(m.SCHEMA)
    deps.metrics = Recorder(conn)
    monkeypatch.setattr(serve_mod, "_handle_chat_stream", lambda d, p: _one_done_event())
    with _running(deps) as srv:
        wire = _send(srv, _chat_stream_request())
    assert _status_lines(wire) == 1
    kinds = [r[0] for r in conn.execute("SELECT kind FROM request_timings").fetchall()]
    conn.close()
    assert "ttfe" in kinds, f"no time-to-first-event sample recorded: {kinds}"


# ---------- #609: `_send_sse` needs a generator, and says so before the headers ----------


def test_plain_iterator_is_refused_before_any_bytes_are_written(deps, monkeypatch):
    """`events` must be closeable, and the check has to precede `send_response`.

    `_send_sse`'s `finally` calls `it.close()`. A plain iterator has none, so
    passing one used to raise *after* the headers and the whole body were on
    the wire — the caller's mistake surfacing as a mid-stream failure the
    client had already begun reading. Nothing in the signature said otherwise:
    `events: Any` (#609).

    Checked at runtime rather than by a type checker because this repo runs
    none — `make check`'s `typecheck` target is `tsc --noEmit`, frontend only.
    """

    monkeypatch.setattr(
        serve_mod,
        "_handle_chat_stream",
        lambda d, p: iter([("done", {"response": "ok"})]),
    )
    with _running(deps) as srv:
        wire = _send(srv, _chat_stream_request())

    assert _status_lines(wire) == 1, f"more than one response written:\n{wire}"
    assert "500" in wire.split("\r\n", 1)[0], f"expected a 500, got:\n{wire}"
    assert "text/event-stream" not in wire, (
        f"headers were committed before the contract was checked:\n{wire}"
    )
