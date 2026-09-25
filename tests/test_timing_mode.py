"""`meta.timing.*` records which kind of run it timed (#658).

`timing.index` used to hold the wall time of whichever `minerva index` ran
last — 74.9 s on the live index after an incremental run, against 8 m 31 s
for a full `--reset` of the same corpus — with nothing to say which. A
reader planned a refresh budget around it. The key now carries the mode.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli._shared import record_timing
from minerva.cli.index_cmd import cmd_index


def _timing_keys(db: Path) -> dict[str, str]:
    conn = sqlite3.connect(db)
    try:
        return dict(conn.execute("SELECT key, value FROM meta WHERE key LIKE 'timing.%'"))
    finally:
        conn.close()


def _meta_only_db(tmp_path: Path) -> Path:
    db = tmp_path / "timing.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()
    conn.close()
    return db


def test_record_timing_keys_on_mode(tmp_path: Path):
    db = _meta_only_db(tmp_path)

    record_timing(db, "index", 511.5, mode="reset")
    record_timing(db, "index", 74.9, mode="incremental")

    # The fast run no longer overwrites the full one: both survive.
    assert _timing_keys(db) == {
        "timing.index.reset": "511.500",
        "timing.index.incremental": "74.900",
    }


def test_record_timing_drops_the_unqualified_key(tmp_path: Path):
    """A pre-#658 `timing.index` says nothing about its run, so the first
    mode-qualified write for that command retires it rather than leaving it
    beside the new keys to be read as a full run."""

    db = _meta_only_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO meta VALUES ('timing.index', '74.948')")
    conn.execute("INSERT INTO meta VALUES ('timing.embed', '28.471')")
    conn.commit()
    conn.close()

    record_timing(db, "index", 3.0, mode="append")

    assert _timing_keys(db) == {
        "timing.index.append": "3.000",
        # Another command's legacy key is its own writer's to retire.
        "timing.embed": "28.471",
    }


def test_stats_reports_timing_by_mode(tmp_path: Path):
    db = tmp_path / "stats.sqlite"
    store.open_db(db).close()
    record_timing(db, "index", 511.5, mode="reset")
    record_timing(db, "ingest", 151.6, mode="only")

    conn = store.open_db(db)
    try:
        assert store.stats(conn)["timing"] == {"index.reset": 511.5, "ingest.only": 151.6}
    finally:
        conn.close()


def _index(db: Path, jsonl: Path, **kw) -> None:
    args = argparse.Namespace(db=db, input=jsonl, **kw)
    assert cmd_index(args) == 0


def test_cmd_index_records_its_mode(tmp_path: Path):
    db = tmp_path / "idx.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(json.dumps(make_chunk(chunk_id="a", text="alpha beta")))

    _index(db, jsonl, reset=True)
    _index(db, jsonl, reset=False)
    _index(db, jsonl, reset=False, incremental=True, corpora="plato")

    assert set(_timing_keys(db)) == {
        "timing.index.reset",
        "timing.index.append",
        "timing.index.incremental",
    }
