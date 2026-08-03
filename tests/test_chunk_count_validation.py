"""Tests for manifest chunk-count range validation."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from chunk_count_validation import (  # noqa: E402
    build_snapshot,
    count_chunks_for_corpus,
    snapshot_drift,
    validate_chunk_counts,
    validate_snapshot,
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


# ---------- committed counts snapshot (#157) ----------
# CI has no `data/index.sqlite` (gitignored), so the DB-backed check above
# cannot run there. These cover the snapshot that stands in for it.


def test_build_snapshot_counts_every_banded_corpus(
    conn: sqlite3.Connection, manifest: dict
) -> None:
    assert build_snapshot(conn, manifest) == {"theognis": 1500, "plato": 400}


def test_validate_snapshot_catches_out_of_band_without_a_db(manifest: dict) -> None:
    """The #150 failure — a corpus blowing past its ceiling — must be
    caught from the committed snapshot alone, with no DB present."""

    errs = validate_snapshot({"theognis": 30_061, "plato": 400}, manifest)
    assert len(errs) == 1
    assert "above maximum" in errs[0]
    assert "30,061" in errs[0]


def test_validate_snapshot_rejects_a_corpus_missing_from_the_snapshot(
    manifest: dict,
) -> None:
    """A newly-banded corpus that never got a snapshot entry must fail
    rather than be silently unchecked — that is the bug this replaces."""

    errs = validate_snapshot({"theognis": 1500}, manifest)
    assert len(errs) == 1
    assert "plato" in errs[0]
    assert "missing from snapshot" in errs[0]


def test_validate_snapshot_rejects_unknown_corpus(manifest: dict) -> None:
    """A snapshot entry with no manifest band is stale leftovers."""

    errs = validate_snapshot({"theognis": 1500, "plato": 400, "gone": 7}, manifest)
    assert len(errs) == 1
    assert "gone" in errs[0]


def test_snapshot_drift_flags_a_stale_snapshot(conn: sqlite3.Connection, manifest: dict) -> None:
    """Local runs have the real DB, so they must catch a snapshot that
    was never refreshed after an ingest — the hole a committed file
    would otherwise open."""

    errs = snapshot_drift(conn, manifest, {"theognis": 1500, "plato": 399})
    assert len(errs) == 1
    assert "plato" in errs[0]
    assert "399" in errs[0] and "400" in errs[0]


def test_snapshot_drift_silent_when_fresh(conn: sqlite3.Connection, manifest: dict) -> None:
    assert snapshot_drift(conn, manifest, build_snapshot(conn, manifest)) == []


def test_committed_snapshot_is_in_band() -> None:
    """The real `data/authors/chunk_counts.json` against the real
    manifest bands. This is the assertion CI actually runs."""

    from chunk_count_validation import load_manifest, load_snapshot

    assert validate_snapshot(load_snapshot(), load_manifest()) == []


def test_check_author_ingest_imports_chunk_validation() -> None:
    import importlib.util

    path = SCRIPTS / "check_author_ingest.py"
    spec = importlib.util.spec_from_file_location("check_author_ingest", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main")
