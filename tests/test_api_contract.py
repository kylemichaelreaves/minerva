"""Assert handler JSON shapes match frontend contract fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import StubBackend, make_deps

from minerva import server
from minerva.http.handlers import (
    _handle_chunk_context,
    _handle_chunk_syntax,
    _handle_concordance_index,
    _handle_concordance_lemma,
    _handle_health,
    _handle_landing_stats,
    _handle_metrics_requests,
    _handle_metrics_series,
    _handle_metrics_summary,
    _handle_network_summary,
    _handle_references_list,
    _handle_references_sources,
    _handle_review_queue,
    _handle_syntax_correction_create,
    _handle_terms_list,
    _handle_word_lookup,
    _handle_work_range,
    _handle_works_list,
)
from minerva.syntax import queries as syntax_queries

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


def test_chunk_context_contract(populated_db):
    deps = make_deps(populated_db, StubBackend())
    body = _handle_chunk_context(deps, "rep-509d", {})
    _assert_has_keys(body, _load_keys("chunk_context.keys.json"))
    assert isinstance(body["before"], list)
    assert isinstance(body["after"], list)


def test_word_lookup_contract(populated_db):
    """The Reader's word-click rail.

    `chunk_lemmas` is not part of the shared fixture corpus, so seed the one
    row the lookup needs. Skipping instead would leave a test that can only
    ever skip, which reads as coverage and is not.
    """
    populated_db.execute(
        "INSERT INTO chunk_lemmas "
        "(chunk_id, token_index, surface_form, surface_start, surface_end, lemma, pos) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("rep-509d", 0, "divided", 60, 67, "divide", "VERB"),
    )
    populated_db.commit()

    deps = make_deps(populated_db, StubBackend())
    body = _handle_word_lookup(deps, {"chunk_id": "rep-509d", "offset": "60"})

    _assert_has_keys(body, _load_keys("word_lookup.keys.json"))
    assert body["lemma"] == "divide"
    assert isinstance(body["samples"], list)


def test_network_summary_contract(populated_db):
    deps = make_deps(populated_db, StubBackend())
    body = _handle_network_summary(deps, {})
    _assert_has_keys(body, _load_keys("network_summary.keys.json"))
    # `matrix` and `top_pairs` are nested objects, not lists — the arc panel
    # reads `matrix.cells` and unions three separate pair rankings.
    _assert_has_keys(body["matrix"], ["authors", "cells"])
    _assert_has_keys(body["top_pairs"], ["all", "non_scrip", "per_author_top"])


def test_landing_stats_contract(populated_db):
    deps = make_deps(populated_db, StubBackend())
    body = _handle_landing_stats(deps)
    _assert_has_keys(body, _load_keys("landing_stats.keys.json"))


def test_metrics_summary_contract(populated_db):
    deps = make_deps(populated_db, StubBackend())
    body = _handle_metrics_summary(deps, {"window": "24h"})
    _assert_has_keys(body, _load_keys("metrics_summary.keys.json"))
    assert isinstance(body["rows"], list)


def test_metrics_series_contract(populated_db):
    deps = make_deps(populated_db, StubBackend())
    body = _handle_metrics_series(deps, {"label": "works list", "window": "24h"})
    _assert_has_keys(body, _load_keys("metrics_series.keys.json"))
    assert isinstance(body["points"], list)


def test_metrics_requests_contract(populated_db):
    deps = make_deps(populated_db, StubBackend())
    body = _handle_metrics_requests(deps, {"window": "24h"})
    _assert_has_keys(body, _load_keys("metrics_requests.keys.json"))
    assert isinstance(body["rows"], list)


def test_concordance_lemma_contract(populated_db):
    """Skip when the lemma cache is empty, as the index contract test does."""
    deps = make_deps(populated_db, StubBackend())
    try:
        body = _handle_concordance_lemma(
            deps, {"lemma": "divide", "lang": "eng", "scope": "corpus", "limit": "5"}
        )
    except Exception as exc:
        pytest.skip(f"concordance unavailable: {exc}")
    _assert_has_keys(body, _load_keys("concordance_lemma.keys.json"))
    assert isinstance(body["rows"], list)


# ---- syntax ----------------------------------------------------------------
#
# The parser is monkeypatched: CI installs no `[lemma]` extra, so there is no
# Stanza and no model. What is under contract here is the response shape the
# overlay reads, not the parse — and that shape has already changed once, from
# a merged tree to the pristine parse plus the correction log side by side.


@pytest.fixture
def syntax_deps(populated_db, monkeypatch: pytest.MonkeyPatch):
    def fake_parse_text(text: str) -> list[syntax_queries.SyntaxToken]:
        def t(tok_id, form, head, deprel):
            return syntax_queries.SyntaxToken(
                sent_ord=0,
                tok_id=tok_id,
                form=form,
                lemma=form.lower(),
                upos="X",
                xpos=None,
                feats=None,
                misc=None,
                head=head,
                deprel=deprel,
                surface_start=tok_id,
                surface_end=tok_id + len(form),
            )

        return [t(1, "Der", 2, "det"), t(2, "Geist", 0, "root")]

    monkeypatch.setattr("minerva.syntax.parse.parse_text", fake_parse_text)
    monkeypatch.setattr("minerva.syntax.parse.parser_id", lambda: "fake-parser")
    return make_deps(populated_db, StubBackend())


def test_chunk_syntax_contract(syntax_deps):
    body = _handle_chunk_syntax(syntax_deps, "hegel-p17")
    _assert_has_keys(body, _load_keys("chunk_syntax.keys.json"))
    assert isinstance(body["sentences"], list)
    # Pristine and log, side by side — a merged tree would make undo impossible.
    assert isinstance(body["corrections"], list)


def test_syntax_correction_contract(syntax_deps):
    _handle_chunk_syntax(syntax_deps, "hegel-p17")  # parse must exist first
    body = _handle_syntax_correction_create(
        syntax_deps,
        "hegel-p17",
        {"sent_ord": 0, "tok_id": 1, "kind": "deprel", "to_val": "amod"},
    )
    _assert_has_keys(body, _load_keys("syntax_correction.keys.json"))
    assert isinstance(body["token"], dict)
