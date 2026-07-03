"""Tests for manifest chunk-count range validation."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from chunk_count_validation import (  # noqa: E402
    count_chunks_for_corpus,
    validate_chunk_counts,
)


@pytest.fixture
def manifest() -> dict:
    return {
        "authors": [
            {"display_name": "Theognis", "corpus_id": "theognis"},
            {"display_name": "Plato", "corpus_id": "plato"},
        ],
        "expected_chunks": {
            "theognis": {"min": 1000, "max": 2000},
            "plato": {"min": 100, "max": 500},
        },
    }


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.executescript(
        """
        CREATE TABLE works (
            work_id INTEGER PRIMARY KEY,
            author TEXT,
            title TEXT
        );
        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY,
            work_id INTEGER,
            ord INTEGER,
            text TEXT
        );
        CREATE VIEW chunks_full AS
        SELECT
            c.chunk_id,
            lower(w.author) AS corpus,
            w.author AS author,
            w.title AS work,
            'eng' AS lang,
            c.text AS text
        FROM chunks c
        JOIN works w ON w.work_id = c.work_id;
        """
    )
    c.execute("INSERT INTO works VALUES (1, 'Theognis', 'Theognidea')")
    for i in range(1500):
        c.execute(
            "INSERT INTO chunks VALUES (?, 1, ?, 'body')",
            (f"t{i}", i),
        )
    c.execute("INSERT INTO works VALUES (2, 'Plato', 'Republic')")
    for i in range(400):
        c.execute(
            "INSERT INTO chunks VALUES (?, 2, ?, 'body')",
            (f"p{i}", i),
        )
    return c


def test_count_chunks_for_corpus(conn: sqlite3.Connection) -> None:
    assert count_chunks_for_corpus(conn, ("theognis",)) == 1500


def test_validate_ok(conn: sqlite3.Connection, manifest: dict) -> None:
    assert validate_chunk_counts(conn, manifest) == []


def test_validate_above_max(conn: sqlite3.Connection, manifest: dict) -> None:
    conn.execute("INSERT INTO works VALUES (3, 'Theognis', 'Extra')")
    for i in range(600):
        conn.execute(
            "INSERT INTO chunks VALUES (?, 3, ?, 'junk')",
            (f"x{i}", 2000 + i),
        )
    errs = validate_chunk_counts(conn, manifest, corpus_ids=("theognis",))
    assert len(errs) == 1
    assert "above maximum" in errs[0]


def test_check_author_ingest_imports_chunk_validation() -> None:
    import importlib.util

    path = SCRIPTS / "check_author_ingest.py"
    spec = importlib.util.spec_from_file_location("check_author_ingest", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main")
