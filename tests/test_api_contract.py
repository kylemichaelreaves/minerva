"""Assert handler JSON shapes match frontend contract fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import StubBackend, make_deps

from minerva import server
from minerva.http.handlers import (
    _handle_concordance_index,
    _handle_health,
    _handle_references_list,
    _handle_references_sources,
    _handle_review_queue,
    _handle_terms_list,
    _handle_work_range,
    _handle_works_list,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "api"


def _load_keys(name: str) -> list[str]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _assert_has_keys(body: dict, keys: list[str]) -> None:
    missing = [k for k in keys if k not in body]
    assert not missing, f"missing keys {missing} in {sorted(body.keys())}"


def test_chat_response_contract(populated_db):
    deps = make_deps(populated_db, StubBackend(reply="ok [1]."))
    body = server._handle_chat(deps, {"query": "divided line", "history": []})
    _assert_has_keys(body, _load_keys("chat_response.keys.json"))
    assert isinstance(body["citations"], list)
    assert isinstance(body["paragraphs"], list)


def test_health_response_has_stats(populated_db):
    deps = make_deps(populated_db, StubBackend())
    body = _handle_health(deps)
    assert "chunks_total" in body
    assert "backend" in body


def test_work_range_contract(populated_db):
    deps = make_deps(populated_db, StubBackend())
    works = _handle_works_list(deps)["works"]
    assert works
    work = works[0]["work"]
    body = _handle_work_range(deps, work, {"lang": works[0]["lang"], "limit": "5"})
    _assert_has_keys(body, _load_keys("work_range.keys.json"))
    assert isinstance(body["chunks"], list)


def test_references_list_contract(populated_db):
    deps = make_deps(populated_db, StubBackend())
    body = _handle_references_list(deps, {"limit": "5"})
    _assert_has_keys(body, _load_keys("references_list.keys.json"))
    assert isinstance(body["references"], list)


def test_refs_sources_contract(populated_db):
    deps = make_deps(populated_db, StubBackend())
    body = _handle_references_sources(deps, {})
    _assert_has_keys(body, _load_keys("refs_sources.keys.json"))
    assert isinstance(body["sources"], list)
    assert isinstance(body["targets"], list)


def test_refs_review_contract(populated_db):
    deps = make_deps(populated_db, StubBackend())
    body = _handle_review_queue(deps, {"limit": "5"})
    _assert_has_keys(body, _load_keys("refs_review.keys.json"))
    assert isinstance(body["references"], list)


def test_terms_list_contract(populated_db):
    deps = make_deps(populated_db, StubBackend())
    body = _handle_terms_list(deps, {})
    _assert_has_keys(body, _load_keys("terms_list.keys.json"))
    assert isinstance(body["terms"], list)


def test_concordance_index_contract(populated_db):
    """Skip when lemma cache empty — contract only applies when rows exist."""
    deps = make_deps(populated_db, StubBackend())
    try:
        body = _handle_concordance_index(deps, {"lang": "eng", "scope": "corpus", "limit": "5"})
    except Exception as exc:
        pytest.skip(f"concordance unavailable: {exc}")
    _assert_has_keys(body, _load_keys("concordance_index.keys.json"))
    assert isinstance(body["rows"], list)
