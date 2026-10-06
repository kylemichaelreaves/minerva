"""The five GET routes deleted by #504 stay deleted.

None of them had a caller in the SPA. Each is asserted twice: at the route
table, which says *which* route (if any) now claims the path, and over a real
socket, which says what a `curl` from an operator actually gets back.

`/api/works/<id>/term_occurrences` is the odd one out: with its own route gone
it has the shape of the readable reader URL `/api/works/<author>/<title>`
(#602), so the slug-pair route claims it and answers 404 because no author is
slugged "1". That is a 404 for a different reason than "no route", which is
why the table assertion names the label instead of asserting no match.
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

from minerva import store
from minerva.http.router import _match_route, build_get_routes
from minerva.http.serve import make_handler

_UNROUTED = (
    "/api/terms",
    "/api/terms/by_chunk/rep-509d",
    "/api/translations/1/renderings",
    "/api/chunks/rep-509d/references",
)
_SLUG_SHAPED = "/api/works/1/term_occurrences"


@contextmanager
def _running(deps: Any) -> Iterator[str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(deps))
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


@pytest.fixture
def deps(populated_db) -> Iterator[Any]:
    """Deps whose corpus connection survives the handler thread, as in
    test_server_syntax_transport.py — `populated_db` is single-thread."""

    d = make_deps(populated_db, StubBackend())
    path = Path(str(d.conn.execute("PRAGMA database_list").fetchone()[2]))
    d.conn = store.open_db(path, check_same_thread=False)
    try:
        yield d
    finally:
        d.conn.close()


def _get(url: str) -> tuple[int, dict[str, Any]]:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


@pytest.mark.parametrize("path", _UNROUTED)
def test_deleted_route_has_no_entry_in_the_get_table(deps, path):
    assert _match_route(path, build_get_routes(deps, dict)) is None


def test_term_occurrences_falls_through_to_the_slug_pair_route(deps):
    matched = _match_route(_SLUG_SHAPED, build_get_routes(deps, dict))
    assert matched is not None
    assert matched[0] == "work range by slug"


@pytest.mark.parametrize("path", (*_UNROUTED, _SLUG_SHAPED))
def test_deleted_route_answers_404_over_http(deps, path):
    with _running(deps) as base:
        status, _body = _get(f"{base}{path}")
    assert status == 404


@pytest.mark.parametrize("path", _UNROUTED)
def test_deleted_route_404_is_no_route_not_a_missing_row(deps, path):
    with _running(deps) as base:
        _status, body = _get(f"{base}{path}")
    assert body["error"] == f"no route for {path}"
