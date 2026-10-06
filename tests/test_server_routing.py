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


# ── Slug-pair work route (#602) ──────────────────────────────────────────
# `#/r/<authorSlug>/<titleSlug>` resolves through `/api/works/<a>/<t>`, which
# has to sit between the numeric sub-resource routes and the `(.+)` catch-all.
# Both neighbours can swallow it, in opposite directions, so both are asserted.


def test_slug_pair_route_matches_two_segments(populated_db) -> None:
    deps = make_deps(populated_db, StubBackend())
    matched = _match_route("/api/works/plato/republic", build_get_routes(deps, dict))
    assert matched is not None
    assert matched[0] == "work range by slug"


def test_slug_pair_route_does_not_shadow_the_numeric_sub_resources(populated_db) -> None:
    """`/api/works/42/occurrence_map` is two segments too.

    Registered before the numeric routes, the slug pattern would eat every one
    of them and the reader would lose occurrence maps, lemma highlights and the
    references map at once.
    """

    deps = make_deps(populated_db, StubBackend())
    routes = build_get_routes(deps, dict)
    for path, label in (
        ("/api/works/42/occurrence_map", "work-occurrence-map"),
        ("/api/works/42/lemma_highlights", "lemma-highlights"),
        ("/api/works/42/references_map", "work references map"),
    ):
        matched = _match_route(path, routes)
        assert matched is not None, f"{path} matched no route at all"
        assert matched[0] == label, f"{path} reached {matched[0]!r}, not {label!r}"


def test_the_single_segment_work_route_still_reaches_work_range(populated_db) -> None:
    deps = make_deps(populated_db, StubBackend())
    matched = _match_route("/api/works/Republic", build_get_routes(deps, dict))
    assert matched is not None
    assert matched[0] == "work range"
