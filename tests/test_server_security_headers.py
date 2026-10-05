"""Security headers on every response path (#124).

`minerva serve` answered with no `nosniff`, no framing policy, no CSP and
no referrer policy. The threat model is the same one the CSRF work
addressed: the operator's browser visits a hostile page while the server
is up. A missing header only matters on the path that omits it, so these
tests assert the whole set on each *kind* of response — JSON, error JSON,
204, and static — rather than on one happy path.

Like the CSRF suite, this drives a real `ThreadingHTTPServer`: the
headers are a transport concern, and asserting on a helper would not
notice a response path that forgot to call it.
"""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from typing import Any

import pytest
from conftest import StubBackend, make_deps

from minerva.http.serve import _SECURITY_HEADERS, make_handler


@contextmanager
def running(deps: Any) -> Iterator[str]:
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


def headers_for(url: str, *, method: str = "GET") -> dict[str, str]:
    """Return one response's headers, whatever its status."""

    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return dict(exc.headers)


def assert_hardened(headers: dict[str, str]) -> None:
    for name, value in _SECURITY_HEADERS.items():
        assert headers.get(name) == value, f"missing/wrong {name}"


def test_json_response_is_hardened(populated_db):
    deps = make_deps(populated_db, StubBackend())
    with running(deps) as base:
        assert_hardened(headers_for(f"{base}/api/health"))


def test_error_response_is_hardened(populated_db):
    # A 404 is a response too — and the path most likely to be reached by
    # something poking at the port.
    deps = make_deps(populated_db, StubBackend())
    with running(deps) as base:
        assert_hardened(headers_for(f"{base}/api/nope"))


def test_options_preflight_is_hardened(populated_db):
    deps = make_deps(populated_db, StubBackend())
    with running(deps) as base:
        assert_hardened(headers_for(f"{base}/api/chat", method="OPTIONS"))


def test_static_response_is_hardened(populated_db, tmp_path):
    # The static path is the one that serves HTML to a browser, so it is
    # where framing and sniffing policy actually bite.
    (tmp_path / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    deps = make_deps(populated_db, StubBackend())
    deps.static_dir = tmp_path
    with running(deps) as base:
        headers = headers_for(f"{base}/")
        assert_hardened(headers)
        assert headers["Content-Type"] == "text/html"


def test_csp_forbids_framing_and_foreign_origins(populated_db):
    # Pin the two directives the issue turns on, so a future loosening of
    # the policy string has to be deliberate.
    deps = make_deps(populated_db, StubBackend())
    with running(deps) as base:
        csp = headers_for(f"{base}/api/health")["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp
    assert "default-src 'self'" in csp
    # script-src must not fall back to something permissive: the SPA
    # ships no inline <script>, so 'unsafe-inline' belongs to styles only.
    assert "script-src" not in csp or "'unsafe-inline'" not in csp.split("script-src")[1]


def test_server_header_does_not_advertise_the_runtime(populated_db):
    deps = make_deps(populated_db, StubBackend())
    with running(deps) as base:
        assert headers_for(f"{base}/api/health")["Server"] == "minerva"


@pytest.mark.parametrize("name", sorted(_SECURITY_HEADERS))
def test_every_declared_header_reaches_the_wire(populated_db, name):
    # Guards the declaration itself: a header added to the dict but
    # dropped by a send path would otherwise pass the set-comparison
    # above only because both sides read the same dict.
    deps = make_deps(populated_db, StubBackend())
    with running(deps) as base:
        assert name in headers_for(f"{base}/api/health")
