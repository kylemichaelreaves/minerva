"""Server tests for the reader endpoints: `/api/translate`, `/api/works`,
`/api/works/:work`. Split from `test_server.py` to keep the chat-side
test file focused on chat behaviour."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from conftest import StubBackend
from conftest import make_deps as _make_deps

from minerva import server

# ---------- /api/translate ----------


def test_handle_translate_cache_miss_calls_llm_and_stores(populated_db, translations_conn):
    backend = StubBackend(reply="Sing, goddess, the wrath")
    deps = _make_deps(populated_db, backend, translations_conn=translations_conn)
    body = server._handle_translate(
        deps,
        {
            "source_text": "Μῆνιν ἄειδε θεὰ",
            "target_lang": "eng",
        },
    )
    assert body["translated_text"] == "Sing, goddess, the wrath"
    assert body["cached"] is False
    assert body["model"] == "stub"
    # Persisted in the cache.
    row = translations_conn.execute(
        "SELECT translated_text, model FROM translations WHERE source_text=? AND target_lang=?",
        ("Μῆνιν ἄειδε θεὰ", "eng"),
    ).fetchone()
    # sqlite3.Row supports tuple-like indexing.
    assert (row[0], row[1]) == ("Sing, goddess, the wrath", "stub")


def test_handle_translate_cache_hit_skips_llm(populated_db, translations_conn):
    backend = StubBackend(reply="should not be called")
    deps = _make_deps(populated_db, backend, translations_conn=translations_conn)
    # First call populates the cache.
    server._handle_translate(deps, {"source_text": "Μῆνιν", "target_lang": "eng"})
    assert len(backend.captured) == 1
    # Second call hits cache — backend is not invoked again.
    body = server._handle_translate(deps, {"source_text": "Μῆνιν", "target_lang": "eng"})
    assert body["cached"] is True
    assert len(backend.captured) == 1  # unchanged


def test_handle_translate_rejects_empty_source(populated_db, translations_conn):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend, translations_conn=translations_conn)
    with pytest.raises(server._HTTPError) as info:
        server._handle_translate(deps, {"source_text": "   ", "target_lang": "eng"})
    assert info.value.status == HTTPStatus.BAD_REQUEST


def test_handle_translate_rejects_bad_lang(populated_db, translations_conn):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend, translations_conn=translations_conn)
    with pytest.raises(server._HTTPError) as info:
        server._handle_translate(deps, {"source_text": "x", "target_lang": "zz"})
    assert info.value.status == HTTPStatus.BAD_REQUEST


def test_handle_translate_rejects_oversize_source(populated_db, translations_conn):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend, translations_conn=translations_conn)
    huge = "x" * (server._MAX_TRANSLATE_CHARS + 1)
    with pytest.raises(server._HTTPError) as info:
        server._handle_translate(deps, {"source_text": huge, "target_lang": "eng"})
    assert info.value.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def test_handle_translate_none_backend_returns_placeholder(populated_db, translations_conn):
    backend = StubBackend(name="none")
    deps = _make_deps(populated_db, backend, translations_conn=translations_conn)
    body = server._handle_translate(deps, {"source_text": "Μῆνιν", "target_lang": "eng"})
    # Placeholder when there's no real LLM; nothing written to the cache.
    assert (
        "retrieval-only" in body["translated_text"].lower()
        or "unavailable" in body["translated_text"].lower()
    )
    assert body["cached"] is False
    assert translations_conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0] == 0


def test_handle_translate_uses_temperature_zero(populated_db, translations_conn):
    backend = StubBackend(reply="t")
    deps = _make_deps(populated_db, backend, translations_conn=translations_conn)
    server._handle_translate(deps, {"source_text": "x", "target_lang": "eng"})
    # The stub records the temperature it was called with.
    assert backend.captured[-1][1] == 0.0


# ---------- /api/works ----------


def test_handle_works_list_returns_distinct_work_lang_pairs(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    body = server._handle_works_list(deps)
    works = body["works"]
    assert len(works) > 0
    # Each entry has the four key fields plus a count.
    for w in works:
        assert {"corpus", "author", "work", "lang", "chunks"} <= w.keys()
    # Republic and Nicomachean Ethics are both in the populated fixture.
    titles = {w["work"] for w in works}
    assert "Republic" in titles


def test_handle_work_range_returns_ordered_chunks(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    body = server._handle_work_range(deps, "Republic", {"lang": "eng"})
    assert body["work"] == "Republic"
    assert body["lang"] == "eng"
    assert body["total"] >= 1
    # Chunks come back ordered by ord.
    ords = [c["ord"] for c in body["chunks"]]
    assert ords == sorted(ords)


def test_handle_work_range_404_for_unknown_work(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    with pytest.raises(server._HTTPError) as info:
        server._handle_work_range(deps, "Does Not Exist", {"lang": "eng"})
    assert info.value.status == HTTPStatus.NOT_FOUND


def test_handle_work_range_rejects_invalid_pagination(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    with pytest.raises(server._HTTPError):
        server._handle_work_range(deps, "Republic", {"lang": "eng", "from": "-1"})
    with pytest.raises(server._HTTPError):
        server._handle_work_range(deps, "Republic", {"lang": "eng", "limit": "0"})
    with pytest.raises(server._HTTPError):
        server._handle_work_range(deps, "Republic", {"lang": "eng", "from": "abc"})


def test_handle_work_range_with_around_centers_window_on_chunk(populated_db):
    """`around=<chunk_id>` resolves to that chunk's (work, lang, ord) and
    returns a window centered on it — frees citation deep-links from
    needing to know the chunk's offset or even its containing work."""
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    # Find a known chunk to pivot around.
    row = populated_db.execute(
        "SELECT chunk_id, work, lang, ord FROM chunks_full "
        "WHERE work='Republic' AND lang='eng' ORDER BY ord LIMIT 1 OFFSET 0"
    ).fetchone()
    body = server._handle_work_range(deps, "ignored", {"around": row[0], "limit": "5"})
    assert body["work"] == row[1]
    assert body["lang"] == row[2]
    returned_ids = {c["chunk_id"] for c in body["chunks"]}
    assert row[0] in returned_ids


def test_handle_work_range_around_404_for_unknown_chunk(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    with pytest.raises(server._HTTPError) as info:
        server._handle_work_range(deps, "Republic", {"around": "nope"})
    assert info.value.status == HTTPStatus.NOT_FOUND


# ---------- /api/chunks/:id/context ----------


def test_handle_chunk_context_returns_focus_and_neighbors(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    # Pick a non-edge chunk so before/after both have material.
    row = populated_db.execute(
        "SELECT chunk_id FROM chunks_full WHERE work='Republic' AND lang='eng' "
        "ORDER BY ord LIMIT 1 OFFSET 1"
    ).fetchone()
    body = server._handle_chunk_context(deps, row[0], {"radius": "1"})
    assert body["focus"]["chunk_id"] == row[0]
    assert body["work"] == "Republic"
    assert body["lang"] == "eng"
    # Same-work, same-lang neighbors, ordered.
    for n in body["before"] + body["after"]:
        assert isinstance(n["text"], str)
    if body["before"]:
        assert body["before"][-1]["ord"] < body["focus"]["ord"]
    if body["after"]:
        assert body["after"][0]["ord"] > body["focus"]["ord"]


def test_handle_chunk_context_radius_zero_skips_neighbors(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    row = populated_db.execute("SELECT chunk_id FROM chunks LIMIT 1").fetchone()
    body = server._handle_chunk_context(deps, row[0], {"radius": "0"})
    assert body["before"] == []
    assert body["after"] == []
    assert body["focus"]["chunk_id"] == row[0]


def test_handle_chunk_context_404_for_unknown_chunk(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    with pytest.raises(server._HTTPError) as info:
        server._handle_chunk_context(deps, "does-not-exist", {})
    assert info.value.status == HTTPStatus.NOT_FOUND


def test_handle_chunk_context_rejects_invalid_radius(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    row = populated_db.execute("SELECT chunk_id FROM chunks LIMIT 1").fetchone()
    with pytest.raises(server._HTTPError):
        server._handle_chunk_context(deps, row[0], {"radius": "abc"})
    with pytest.raises(server._HTTPError):
        server._handle_chunk_context(deps, row[0], {"radius": "99"})


def test_handle_translate_refusal_is_not_cached(populated_db, translations_conn):
    """Regression: a refusal used to be cached as empty strings, and
    translations.lookup treats an empty-string row as a valid hit — one
    transient refusal made every later request return cached:true with
    an empty translation, forever. Refusals must not be cached, so the
    next request retries the LLM."""

    backend = StubBackend(reply="The source passage seems incomplete.")
    deps = _make_deps(populated_db, backend, translations_conn=translations_conn)
    body = server._handle_translate(deps, {"source_text": "Μῆνιν ἄειδε θεὰ", "target_lang": "eng"})
    assert body["translated_text"] == ""
    assert body["cached"] is False
    row = translations_conn.execute(
        "SELECT 1 FROM translations WHERE source_text=? AND target_lang=?",
        ("Μῆνιν ἄειδε θεὰ", "eng"),
    ).fetchone()
    assert row is None, "refusal must not poison the cache"

    # The model recovers → next request retries and lands a real row.
    backend.reply = "Sing, goddess, the wrath"
    body = server._handle_translate(deps, {"source_text": "Μῆνιν ἄειδε θεὰ", "target_lang": "eng"})
    assert body["translated_text"] == "Sing, goddess, the wrath"
    assert body["cached"] is False


# ---------- /api/works/:authorSlug/:titleSlug (#602) ----------


def test_work_range_by_slug_resolves_the_pair_to_the_canonical_work(populated_db):
    deps = _make_deps(populated_db, StubBackend())
    body = server._handle_work_range_by_slug(
        deps, "aristotle", "nicomachean-ethics", {"lang": "eng"}
    )
    assert (body["author"], body["work"]) == ("Aristotle", "Nicomachean Ethics")


def test_work_range_by_slug_disambiguates_on_the_author_slug(populated_db):
    """The author is part of identity now, not an optional `?author=` hint.

    Two works sharing a title is the case `?author=` was added for (Luther 1912
    vs 1545); carrying the author in the path is what makes the pair unique.
    """

    populated_db.execute(
        "INSERT INTO works (author, title, original_language, citation_system) "
        "VALUES ('Xenophon', 'Republic', 'grc', 'stephanus')"
    )
    deps = _make_deps(populated_db, StubBackend())
    body = server._handle_work_range_by_slug(deps, "plato", "republic", {"lang": "eng"})
    assert body["author"] == "Plato"


def test_work_range_by_slug_404s_on_an_unknown_pair(populated_db):
    deps = _make_deps(populated_db, StubBackend())
    with pytest.raises(server._HTTPError) as info:
        server._handle_work_range_by_slug(deps, "plato", "no-such-dialogue", {"lang": "eng"})
    assert info.value.status == HTTPStatus.NOT_FOUND


def test_work_range_by_slug_404s_on_an_unknown_author_slug(populated_db):
    deps = _make_deps(populated_db, StubBackend())
    with pytest.raises(server._HTTPError) as info:
        server._handle_work_range_by_slug(deps, "nobody", "republic", {"lang": "eng"})
    assert info.value.status == HTTPStatus.NOT_FOUND


def test_work_range_by_slug_ignores_the_path_when_the_query_deep_links_a_chunk(populated_db):
    """`around=` resolves work, lang and edition off the chunk row itself.

    That is what lets a citation deep-link emit the single-segment form with no
    author — the path segment is decoration once `around=` is present, and this
    asserts it stays that way rather than becoming a second, conflicting
    source of truth.
    """

    deps = _make_deps(populated_db, StubBackend())
    body = server._handle_work_range_by_slug(
        deps, "plato", "republic", {"around": "ne-1097b"}
    )
    assert body["work"] == "Nicomachean Ethics"


def test_single_segment_work_route_accepts_a_title_slug(populated_db):
    """A chunk deep-link has a title but no author, so it emits one segment.

    Without this the slug would reach the title-keyed lookup, match nothing and
    404 — the failure would only appear on links that carry no `around=`.
    """

    deps = _make_deps(populated_db, StubBackend())
    body = server._handle_work_range(deps, "nicomachean-ethics", {"lang": "eng"})
    assert body["work"] == "Nicomachean Ethics"


def test_single_segment_work_route_still_prefers_an_exact_title(populated_db):
    """The slug pass is a FALLBACK. `/api/works/<title>` is a public shape with
    callers older than this change, and an exact title must never be reinterpreted."""

    deps = _make_deps(populated_db, StubBackend())
    body = server._handle_work_range(deps, "Nicomachean Ethics", {"lang": "eng"})
    assert body["work"] == "Nicomachean Ethics"


def test_single_segment_work_route_404s_when_neither_title_nor_slug_matches(populated_db):
    deps = _make_deps(populated_db, StubBackend())
    with pytest.raises(server._HTTPError) as info:
        server._handle_work_range(deps, "no-such-work", {"lang": "eng"})
    assert info.value.status == HTTPStatus.NOT_FOUND
