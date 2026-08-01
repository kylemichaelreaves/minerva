"""CSRF protection at the HTTP boundary (issue #118).

`minerva serve` has no authentication — anything that can reach the port can
drive it. That is a deliberate single-operator tradeoff, but it makes the
browser a confused deputy: any page the operator visits can POST to
``http://127.0.0.1:8000`` and the request carries whatever local access the
browser has.

CORS does not stop this. The allowlist governs whether a response can be
*read*; it does nothing about whether the request is *executed*. And a POST
whose Content-Type is one of the three CORS-safelisted values
(``text/plain``, ``application/x-www-form-urlencoded``, ``multipart/form-data``)
is a "simple request" — no preflight is issued at all, so the allowlist is
never consulted before the side effect happens.

These tests drive a real ``ThreadingHTTPServer`` rather than calling handlers
directly. The bug lived entirely in the transport layer, which no test
exercised; asserting on helpers alone would have missed it the same way.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from conftest import StubBackend, make_deps

from minerva import conversations, store, translations
from minerva.http.serve import make_handler

ALLOWED = "http://127.0.0.1:5173"
EVIL = "https://evil.example"


@contextmanager
def running(deps: Any) -> Iterator[str]:
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


def request(
    url: str,
    *,
    method: str = "POST",
    body: dict[str, Any] | None = None,
    content_type: str | None = "application/json",
    origin: str | None = None,
    host: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """Issue one request, returning ``(status, parsed_body)``.

    ``content_type=None`` omits the header entirely — which urllib then fills
    in as ``application/x-www-form-urlencoded``, exactly what a cross-origin
    HTML form POST sends.
    """

    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers: dict[str, str] = {}
    if content_type is not None:
        headers["Content-Type"] = content_type
    if origin is not None:
        headers["Origin"] = origin
    if host is not None:
        headers["Host"] = host

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, (json.loads(raw) if raw else {})


def _path_of(conn: Any) -> Path:
    """The file a connection is attached to. `PRAGMA database_list` returns
    `(seq, name, file)` per attached database; `main` is the first."""

    return Path(str(conn.execute("PRAGMA database_list").fetchone()[2]))


@pytest.fixture
def deps(populated_db):
    """`ServerDeps` whose connections are safe to use from the handler
    threads a real server dispatches on.

    The conftest fixtures open with `check_same_thread=True`, which is right
    for handler-level tests calling in-process. `serve_cmd.py` opens with
    `False` and relies on the per-resource locks in `ServerDeps` instead.
    Reopen the same files the same way, or every request 500s on a
    cross-thread SQLite access rather than exercising the boundary.
    """

    d = make_deps(populated_db, StubBackend(reply="ok"))
    d.conn = store.open_db(_path_of(d.conn), check_same_thread=False)
    d.conversations_conn = conversations.open_db(
        _path_of(d.conversations_conn), check_same_thread=False
    )
    d.translations_conn = translations.open_db(
        _path_of(d.translations_conn), check_same_thread=False
    )
    d.allowed_origins = frozenset({ALLOWED})
    return d


# ---------- The reported attack ----------


def test_cross_origin_simple_post_is_refused(deps) -> None:
    """The exact repro from #118: a CORS simple request, no preflight."""

    with running(deps) as base:
        status, body = request(
            f"{base}/api/chat",
            body={"query": "csrf probe"},
            content_type="text/plain;charset=UTF-8",
            origin=EVIL,
        )

    assert status == 403
    assert "error" in body


def test_cross_origin_form_post_is_refused(deps) -> None:
    """The other no-preflight shape: an HTML form submission."""

    with running(deps) as base:
        status, _ = request(
            f"{base}/api/chat",
            body={"query": "csrf probe"},
            content_type=None,  # urllib sends x-www-form-urlencoded
            origin=EVIL,
        )

    assert status == 403


def test_cross_origin_delete_is_refused(deps) -> None:
    with running(deps) as base:
        status, _ = request(
            f"{base}/api/conversations/abc123",
            method="DELETE",
            content_type=None,
            origin=EVIL,
        )

    assert status == 403


def test_no_conversation_is_created_by_a_refused_request(deps) -> None:
    """The side effect is the whole point — assert it did not happen."""

    with running(deps) as base:
        request(
            f"{base}/api/chat",
            body={"query": "csrf probe"},
            content_type="text/plain",
            origin=EVIL,
        )
        _status, listing = request(f"{base}/api/conversations", method="GET", body=None)

    assert listing["conversations"] == []


# ---------- The two independent gates ----------


def test_json_body_from_a_hostile_origin_is_refused(deps) -> None:
    """Declaring the right Content-Type does not buy an attacker anything —
    it only means the browser would have preflighted. Check Origin too."""

    with running(deps) as base:
        status, _ = request(f"{base}/api/chat", body={"query": "hi"}, origin=EVIL)

    assert status == 403


def test_non_json_body_from_an_allowed_origin_is_refused(deps) -> None:
    """And the Content-Type gate holds independently of Origin, so a
    same-origin XSS cannot downgrade to a simple request."""

    with running(deps) as base:
        status, _ = request(
            f"{base}/api/chat",
            body={"query": "hi"},
            content_type="text/plain",
            origin=ALLOWED,
        )

    assert status == 415


# ---------- What must keep working ----------


def test_allowlisted_origin_with_json_succeeds(deps) -> None:
    """The Vite dev proxy case: browser on :5173, API on another port."""

    with running(deps) as base:
        status, body = request(f"{base}/api/chat", body={"query": "divided line"}, origin=ALLOWED)

    assert status == 200
    assert "conversation_id" in body


def test_request_without_an_origin_succeeds(deps) -> None:
    """curl, the CLI, and the e2e harness send no Origin. Absence is not
    evidence of a cross-origin request — browsers always send one on POST."""

    with running(deps) as base:
        status, _ = request(f"{base}/api/chat", body={"query": "divided line"})

    assert status == 200


def test_same_origin_as_the_host_succeeds_without_an_allowlist(deps) -> None:
    """A request whose Origin is the very host it was sent to is same-origin
    by definition. Without this, binding to a LAN address and serving the SPA
    from that same port (`serve --host 0.0.0.0 --static`) would reject every
    POST unless the operator also passed --allow-origin.
    """

    deps.allowed_origins = frozenset()

    with running(deps) as base:
        host = base.removeprefix("http://")
        status, _ = request(
            f"{base}/api/chat",
            body={"query": "divided line"},
            origin=f"http://{host}",
        )

    assert status == 200


def test_preflight_still_answers(deps) -> None:
    """OPTIONS must keep working, or the browser never gets far enough to
    learn that a real cross-origin request would be rejected."""

    with running(deps) as base:
        status, _ = request(f"{base}/api/chat", method="OPTIONS", content_type=None)

    assert status == 204


def test_get_routes_are_unaffected(deps) -> None:
    """Reads are safe and idempotent; the gates apply to state change only."""

    with running(deps) as base:
        status, body = request(f"{base}/api/health", method="GET", content_type=None, origin=EVIL)

    assert status == 200
    assert body["backend"] == "stub"
