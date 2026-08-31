"""Top-level `minerva` subcommands must close the DB connection they open.

#227 fixed this for the `terms` subcommands and
`test_terms_cli_conn_lifecycle.py` guards them. The same bug was still
live in six handlers outside that family — found while turning on
`-W error::ResourceWarning` for #246, where `cmd_index` alone accounted
for 54 of the suite's remaining `unclosed database` warnings:

    src/minerva/cli/index_cmd.py:84        cmd_index              54
    src/minerva/cli/refs/load_spec_cmd.py  cmd_refs_load_spec      5
    src/minerva/cli/refs/review.py         cmd_refs_review         2
    src/minerva/cli/embed_cmd.py           cmd_embed               1
    src/minerva/cli/db_cmd.py              _cmd_db_inspect         1
    src/minerva/cli/stats_cmd.py           cmd_stats               1

Like #227 it is invisible in normal use — the CLI process exits after
one command — and like #227 it matters because these handlers are plain
functions that invite being called in a loop (`make reingest` drives
`cmd_index` repeatedly in-process, and every test that indexes a fixture
DB strands a handle).

Each test drives a *path*, not just the happy case: the early-`return`
exits are where a `close()` at the bottom of the body would still miss.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pytest
from conftest import make_chunk  # type: ignore[import-not-found]

from minerva import store
from minerva.cli import embed_cmd
from minerva.cli.db_cmd import cmd_db
from minerva.cli.index_cmd import cmd_index
from minerva.cli.refs.load_spec_cmd import cmd_refs_load_spec
from minerva.cli.refs.review import cmd_refs_review
from minerva.cli.stats_cmd import cmd_stats


def _is_closed(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[sqlite3.Connection]:
    """Record every connection `store.open_db` hands to the code under test.

    Both `store.open_db` and the `terms._io._open` indirection the refs
    handlers use funnel through this, so one spy covers all six.
    """

    conns: list[sqlite3.Connection] = []
    real = store.open_db

    def spy(path, **kwargs):  # type: ignore[no-untyped-def]
        conn = real(path, **kwargs)
        conns.append(conn)
        return conn

    monkeypatch.setattr(store, "open_db", spy)
    return conns


def _assert_all_closed(conns: list[sqlite3.Connection]) -> None:
    assert conns, "handler opened no connection — the spy is not wired up"
    unclosed = [c for c in conns if not _is_closed(c)]
    assert not unclosed, f"{len(unclosed)} of {len(conns)} connections left open"


@pytest.fixture
def seeded_index(tmp_path: Path) -> Path:
    """An indexed store with one chunk, built without the spy in place."""

    db = tmp_path / "idx.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(json.dumps(make_chunk(chunk_id="c1", text="Some text.")) + "\n")
    conn = store.open_db(db)
    store.insert_chunks(conn, jsonl)
    conn.close()
    return db


def test_cmd_stats_closes_its_connection(seeded_index, opened, capsys):
    assert cmd_stats(argparse.Namespace(db=seeded_index, tables=False)) == 0
    capsys.readouterr()
    _assert_all_closed(opened)


def test_cmd_db_inspect_closes_its_connection(seeded_index, opened, capsys):
    assert cmd_db(argparse.Namespace(db=seeded_index, action="inspect")) == 0
    capsys.readouterr()
    _assert_all_closed(opened)


def test_cmd_index_closes_its_connection(tmp_path, opened, capsys):
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text(json.dumps(make_chunk(chunk_id="c1", text="Some text.")) + "\n")
    args = argparse.Namespace(
        db=tmp_path / "new.sqlite",
        input=jsonl,
        reset=False,
        incremental=False,
        corpora="",
        from_ingest_only=False,
    )
    assert cmd_index(args) == 0
    capsys.readouterr()
    _assert_all_closed(opened)


def test_cmd_embed_closes_its_connection_on_the_empty_lang_exit(
    seeded_index, opened, monkeypatch, capsys
):
    """`embed` bails with 2 when the requested language has no chunks —
    after opening the connection, so this is the leaking path."""

    class _FakeEmbedder:
        dim = 4

        def encode(self, texts, batch_size=32):
            return []

    monkeypatch.setattr(embed_cmd.embed, "Embedder", lambda _model: _FakeEmbedder())
    monkeypatch.setattr(embed_cmd, "record_timing", lambda *a, **k: None)

    args = argparse.Namespace(
        db=seeded_index,
        model="fake-model",
        lang="grc",
        all=True,
        batch_size=64,
        encode_batch_size=32,
        timing=False,
    )
    assert embed_cmd.cmd_embed(args) == 2
    capsys.readouterr()
    _assert_all_closed(opened)


def test_cmd_refs_load_spec_closes_its_connection_on_a_missing_path(seeded_index, opened, capsys):
    """The `path does not exist` guard returns 2 from inside the loop,
    well after `_open` — a `close()` at the end of the body misses it."""

    args = argparse.Namespace(
        db=seeded_index,
        paths=[str(seeded_index.parent / "nope.yaml")],
        dry_run=True,
    )
    assert cmd_refs_load_spec(args) == 2
    capsys.readouterr()
    _assert_all_closed(opened)


def test_cmd_refs_review_closes_its_connection_when_there_is_nothing_to_review(
    seeded_index, opened, capsys
):
    args = argparse.Namespace(
        db=seeded_index,
        limit=1,
        source_author=None,
        target_author=None,
    )
    assert cmd_refs_review(args) == 0
    capsys.readouterr()
    _assert_all_closed(opened)
