"""Phase 6 tests — refs incremental scan via `refs_scan_state` + the
LLM-verify `--resume` checkpoint."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index
from minerva.refs import llm_verify
from minerva.refs.rules import iter_chunks_for_rules, record_scan_state


def _seed_chunks(tmp_path: Path) -> Path:
    db = tmp_path / "scan.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(
                    chunk_id="ch-a",
                    author="Aquinas",
                    text="Philosophus dixit virtus est habitus electivus.",
                ),
                make_chunk(
                    chunk_id="ch-b",
                    author="Aquinas",
                    text="Augustinus in libro de Trinitate plurima dicit.",
                ),
            ]
        )
    )
    cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False))
    return db


def test_iter_chunks_for_rules_skips_already_scanned(tmp_path: Path) -> None:
    db = _seed_chunks(tmp_path)
    conn = store.open_db(db)
    try:
        # First call — no scan_state rows, should yield both chunks.
        first = list(iter_chunks_for_rules(conn))
        assert {c.chunk_id for c in first} == {"ch-a", "ch-b"}

        # Mark them scanned.
        n = record_scan_state(conn, first)
        assert n == 2

        # Second call — every chunk's hash matches, should yield nothing.
        second = list(iter_chunks_for_rules(conn))
        assert second == [], "content-stable rescan must be a no-op"

        # rescan_all=True bypasses the cache.
        forced = list(iter_chunks_for_rules(conn, rescan_all=True))
        assert {c.chunk_id for c in forced} == {"ch-a", "ch-b"}
    finally:
        conn.close()


def test_iter_chunks_for_rules_reyields_when_text_changes(tmp_path: Path) -> None:
    db = _seed_chunks(tmp_path)
    conn = store.open_db(db)
    try:
        first = list(iter_chunks_for_rules(conn))
        record_scan_state(conn, first)

        # Stamp a stale hash for ch-a — simulate the text having
        # changed since the prior scan. The iterator should re-yield
        # it but NOT ch-b.
        conn.execute(
            "UPDATE refs_scan_state SET text_hash = ? WHERE chunk_id = ?",
            ("bogus", "ch-a"),
        )
        conn.commit()

        stale = list(iter_chunks_for_rules(conn))
        assert {c.chunk_id for c in stale} == {"ch-a"}
    finally:
        conn.close()


def test_record_scan_state_is_noop_on_pre_migration_db(tmp_path: Path) -> None:
    """A DB built before migration 0020 doesn't have the table — the
    helper must silently no-op rather than raise."""

    db = tmp_path / "pre.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE chunks_full (chunk_id TEXT)")  # dummy schema
    conn.commit()
    try:
        from minerva.refs.rules import ChunkInfo

        n = record_scan_state(
            conn,
            [ChunkInfo("x", "A", "W", "lat", None, "t")],
        )
        assert n == 0
    finally:
        conn.close()


def test_llm_verify_resume_checkpoint_round_trip(tmp_path: Path) -> None:
    """The checkpoint reader returns None when nothing is stored,
    and the writer/reader round-trip preserves the integer id."""

    db = _seed_chunks(tmp_path)
    conn = store.open_db(db)
    try:
        assert llm_verify._read_checkpoint(conn) is None
        llm_verify._write_checkpoint(conn, 4321)
        conn.commit()
        assert llm_verify._read_checkpoint(conn) == 4321

        # Reading is robust to garbage values someone might paste in.
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES "
            "('refs.llm_verify.last_row_id', 'not-an-int')"
        )
        conn.commit()
        assert llm_verify._read_checkpoint(conn) is None
    finally:
        conn.close()


def test_llm_verify_resume_emits_resume_clause(tmp_path: Path) -> None:
    """When `resume=True` and a checkpoint exists, the eligible-rows
    SQL must include the ``xr.id > <last>`` clause."""

    sql, params = llm_verify._eligible_rows_sql(resume_from_id=99)
    assert "xr.id > ?" in sql
    assert 99 in params

    sql, params = llm_verify._eligible_rows_sql(resume_from_id=None)
    assert "xr.id > ?" not in sql
