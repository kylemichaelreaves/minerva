"""Tests for ``store.stats`` and ``minerva db inspect``."""

from __future__ import annotations

import argparse
import json
from io import StringIO
from unittest.mock import patch

from minerva import store
from minerva.cli.db_cmd import cmd_db
from minerva.cli.stats_cmd import cmd_stats


def test_store_stats_shape(populated_db):
    out = store.stats(populated_db)

    # 6 = the five original fixtures + the German syntax chunk (hegel-p17).
    assert out["chunks_total"] == 6
    assert out["embeddings_present"] is False
    assert isinstance(out["chunks_by_corpus_lang"], list)
    assert len(out["chunks_by_corpus_lang"]) >= 1
    assert "timing" in out


def test_store_tables_summary(populated_db):
    tables = store.tables_summary(populated_db)
    names = {row["name"] for row in tables}
    assert "chunks" in names
    assert all("rows" in row for row in tables)


def test_store_db_inspect(populated_db, db_path):
    info = store.db_inspect(populated_db, db_path)

    assert info["db_path"] == str(db_path)
    assert info["db_size_bytes"] > 0
    assert info["journal_mode"]
    assert "table" in info["schema_objects"]
    assert info["migrations_applied"] >= 1
    assert info["latest_migration"]


def test_cmd_stats_json(populated_db, db_path):
    args = argparse.Namespace(db=db_path, tables=False)
    buf = StringIO()

    with patch("sys.stdout", buf):
        rc = cmd_stats(args)

    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["chunks_total"] == 6


def test_cmd_db_inspect_json(populated_db, db_path):
    args = argparse.Namespace(db=db_path, action="inspect")
    buf = StringIO()

    with patch("sys.stdout", buf):
        rc = cmd_db(args)

    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["db_path"] == str(db_path)
    assert payload["latest_migration"]
