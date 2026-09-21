"""Tests for `minerva.store` — schema, connection settings, transactional
ingest behavior. The fixture `populated_db` (in conftest.py) is the
canonical in-temp-dir SQLite store used elsewhere; this file focuses on
behavior the other test files don't exercise directly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import make_chunk

from minerva import store


def test_insert_chunks_rolls_back_on_malformed_jsonl(tmp_path: Path):
    """If the JSONL fails partway through (e.g. a row missing required keys),
    the prior corpus must survive — DELETE FROM chunks should be reverted."""

    db = tmp_path / "rollback.sqlite"
    conn = store.open_db(db)

    # Seed: a clean three-chunk index.
    seed = tmp_path / "seed.jsonl"
    seed.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(chunk_id="a"),
                make_chunk(chunk_id="b", section="510a"),
                make_chunk(chunk_id="c", section="514a"),
            ]
        )
    )
    assert store.insert_chunks(conn, seed) == 3
    assert store.chunk_count(conn) == 3

    # Now feed a JSONL whose second line is missing `chunk_id`. The first
    # line gets parsed and queued for insert; iteration on the second
    # raises KeyError; we want the seeded three chunks to still be there.
    bad = tmp_path / "bad.jsonl"
    good_first = make_chunk(chunk_id="x", section="600a")
    malformed = {**make_chunk(), "chunk_id": None}
    del malformed["chunk_id"]
    bad.write_text("\n".join([json.dumps(good_first), json.dumps(malformed)]))

    with pytest.raises(KeyError):
        store.insert_chunks(conn, bad)

    # Pre-existing chunks must still be present.
    assert store.chunk_count(conn) == 3


def test_insert_chunks_commits_on_clean_load(tmp_path: Path):
    """Sanity: the rollback path doesn't break the happy path."""

    db = tmp_path / "ok.sqlite"
    conn = store.open_db(db)
    p = tmp_path / "ok.jsonl"
    p.write_text(json.dumps(make_chunk(chunk_id="z")))
    assert store.insert_chunks(conn, p) == 1
    assert store.chunk_count(conn) == 1


def test_fetch_chunk_context_unknown_id(populated_db):
    focus, before, after = store.fetch_chunk_context(populated_db, "missing", radius=1)
    assert focus is None
    assert before == []
    assert after == []


def test_fetch_chunk_context_radius_zero(populated_db):
    focus, before, after = store.fetch_chunk_context(populated_db, "rep-510a", radius=0)
    assert focus is not None
    assert focus["chunk_id"] == "rep-510a"
    assert before == []
    assert after == []


def test_fetch_chunk_context_neighbors_ordered(populated_db):
    focus, before, after = store.fetch_chunk_context(populated_db, "rep-510a", radius=1)
    assert focus["chunk_id"] == "rep-510a"
    assert len(before) == 1
    assert before[0]["chunk_id"] == "rep-509d"
    assert before[0]["ord"] < focus["ord"]
    assert len(after) == 1
    assert after[0]["chunk_id"] == "rep-514a"
    assert after[0]["ord"] > focus["ord"]


def test_open_db_check_same_thread_flag_is_passed_through(tmp_path: Path):
    """The HTTP server opens the DB with `check_same_thread=False` so its
    request-handling threads can share the connection (serialized via lock).
    Without this flag, sqlite3 raises 'objects created in a thread can only
    be used in that same thread'."""
    import threading

    db = tmp_path / "thread.sqlite"
    conn = store.open_db(db, check_same_thread=False)

    err: list[BaseException] = []

    def bg():
        try:
            conn.execute("SELECT 1").fetchone()
        except BaseException as e:
            err.append(e)

    t = threading.Thread(target=bg)
    t.start()
    t.join()
    assert err == []


# ──────────────────────────────────────────────────────────────────
#  Page cache (#645)
# ──────────────────────────────────────────────────────────────────


def test_corpus_connection_sizes_its_page_cache(tmp_path: Path) -> None:
    """The corpus database is 8.4 GB; SQLite's default page cache is 2 MB,
    which holds 0.02% of it.

    Asserted as the negative (KiB) form rather than a page count: the two
    are only equal at the current 4 KiB page size, and a future
    `page_size` change would silently shrink a positive value by the same
    factor.
    """

    conn = store.open_db(tmp_path / "corpus.sqlite")
    try:
        (cache_size,) = conn.execute("PRAGMA cache_size").fetchone()
    finally:
        conn.close()
    assert cache_size == -65536, "expected 64 MiB, expressed in KiB"


def test_the_page_cache_is_set_on_the_corpus_store_not_the_shared_helper(
    tmp_path: Path,
) -> None:
    """Scoping, and the reason the pragma is not in `sqlite_util.open_db`.

    `serve` holds five connections — corpus, metrics, conversations,
    translations, concept cache — and only the first one reads an 8 GB
    file. Setting this in the shared helper would multiply the budget by
    five to buy nothing on the other four.
    """

    from minerva import metrics

    conn = metrics.open_db(tmp_path / "metrics.sqlite")
    try:
        (cache_size,) = conn.execute("PRAGMA cache_size").fetchone()
    finally:
        conn.close()
    assert cache_size == -2000, "the metrics DB keeps SQLite's default"
