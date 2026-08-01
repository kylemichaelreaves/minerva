"""HTTP routing tests for POST/PATCH/DELETE dispatch."""

from __future__ import annotations

import pytest
from conftest import StubBackend, make_deps

from minerva.http.router import (
    _match_route,
    build_delete_routes,
    build_get_routes,
    build_patch_routes,
    build_post_routes,
)
from minerva.http.server_core import _HTTPError


def test_post_routes_match_chat_and_translate(populated_db) -> None:
    deps = make_deps(populated_db, StubBackend())
    routes = build_post_routes(deps)
    assert _match_route("/api/chat", routes) is not None
    assert _match_route("/api/translate", routes) is not None
    assert _match_route("/api/health", routes) is None


def test_patch_route_matches_reference_id(populated_db) -> None:
    deps = make_deps(populated_db, StubBackend())
    routes = build_patch_routes(deps)
    matched = _match_route("/api/references/42", routes)
    assert matched is not None
    _label, handler, args = matched
    with pytest.raises(_HTTPError) as exc_info:
        handler(*args, {})
    assert exc_info.value.status == 400


def test_delete_route_matches_conversation(populated_db) -> None:
    deps = make_deps(populated_db, StubBackend())
    routes = build_delete_routes(deps)
    matched = _match_route("/api/conversations/!!!", routes)
    assert matched is not None
    _label, handler, args = matched
    with pytest.raises(_HTTPError) as exc_info:
        handler(*args)
    assert exc_info.value.status == 400


def test_post_route_matches_syntax_corrections(populated_db) -> None:
    deps = make_deps(populated_db, StubBackend())
    routes = build_post_routes(deps)
    assert _match_route("/api/chunks/abc123/syntax/corrections", routes) is not None


def test_syntax_correction_post_does_not_shadow_the_syntax_get(populated_db) -> None:
    """`…/syntax` and `…/syntax/corrections` are different routes on different
    verbs; the GET pattern is anchored so the longer path cannot fall into it."""

    deps = make_deps(populated_db, StubBackend())
    assert _match_route("/api/chunks/abc/syntax/corrections", build_get_routes(deps, dict)) is None


def test_delete_route_matches_a_syntax_correction(populated_db) -> None:
    deps = make_deps(populated_db, StubBackend())
    routes = build_delete_routes(deps)
    matched = _match_route("/api/syntax/corrections/42", routes)
    assert matched is not None
    _label, handler, args = matched
    # No such correction, so the handler reports that nothing was removed and
    # the transport turns it into a 404.
    assert handler(*args) is False


def test_a_non_numeric_correction_id_is_not_a_route(populated_db) -> None:
    deps = make_deps(populated_db, StubBackend())
    routes = build_delete_routes(deps)
    assert _match_route("/api/syntax/corrections/all", routes) is None
