"""Failure semantics of the migrations runner + sqlite_util helpers.

The runner's contract — "if a migration raises, everything rolls back
and the version is NOT recorded, so the next open retries it" — was
fictional for ``executescript``-based migrations (each statement
autocommitted; a mid-script failure left the DB half-migrated and
permanently wedged on retry). These tests pin the repaired contract by
injecting probe migrations through a patched ``_discover`` (never by
writing files into the real package dir, which would leak into every
other test's ``open_db``).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from minerva import migrations, store
from minerva.sqlite_util import (
    execute_script_statements,
    foreign_keys_disabled,
    iter_sql_statements,
    table_exists,
)

# ---------- runner failure/rollback/retry ----------


def _probe_entry(version: int, script: str):
    """Build a runner-shaped ``_discover`` entry for a .sql probe."""

    return (
        version,
        f"{version:04d}_probe",
        "sql",
        lambda conn, s=script: execute_script_statements(conn, s),
    )


def test_sql_migration_failure_rolls_back_completely(tmp_path: Path, monkeypatch):
    """A .sql migration that fails on its SECOND statement must leave
    zero trace of its first — and stay unrecorded so the fixed version
    applies cleanly afterwards. (The executescript regression left the
    first statement committed → retry hit 'table already exists'.)"""

    conn = store.open_db(tmp_path / "m.sqlite")
    real_entries = migrations._discover()

    bad = _probe_entry(
        9900,
        "CREATE TABLE probe_ok (x INTEGER);\nINSERT INTO no_such_table VALUES (1);\n",
    )
    monkeypatch.setattr(migrations, "_discover", lambda: [*real_entries, bad])
    with pytest.raises(sqlite3.OperationalError):
        migrations.apply(conn)

    # First statement rolled back with the failure, version unrecorded.
    assert not table_exists(conn, "probe_ok")
    assert migrations.current_version(conn) < 9900

    # The "fixed" migration now applies cleanly — no wedge.
    good = _probe_entry(9900, "CREATE TABLE probe_ok (x INTEGER);")
    monkeypatch.setattr(migrations, "_discover", lambda: [*real_entries, good])
    assert migrations.apply(conn) == [9900]
    assert table_exists(conn, "probe_ok")
    assert migrations.current_version(conn) == 9900
    # And a re-run is a no-op.
    assert migrations.apply(conn) == []


def test_multi_statement_sql_migration_applies_atomically(tmp_path: Path, monkeypatch):
    """Happy path for the statement splitter inside the runner: a
    multi-statement script with comments and a trigger (internal
    semicolons) lands in one transaction."""

    conn = store.open_db(tmp_path / "m.sqlite")
    real_entries = migrations._discover()
    script = """
        -- a probe table
        CREATE TABLE probe_t (x INTEGER);
        CREATE TABLE probe_log (x INTEGER);
        CREATE TRIGGER probe_trg AFTER INSERT ON probe_t BEGIN
            INSERT INTO probe_log (x) VALUES (new.x);
            INSERT INTO probe_log (x) VALUES (new.x * 2);
        END;
        INSERT INTO probe_t (x) VALUES (21);
    """
    monkeypatch.setattr(
        migrations, "_discover", lambda: [*real_entries, _probe_entry(9901, script)]
    )
    assert migrations.apply(conn) == [9901]
    rows = [r[0] for r in conn.execute("SELECT x FROM probe_log ORDER BY x")]
    assert rows == [21, 42]


# ---------- iter_sql_statements ----------


def test_iter_sql_statements_keeps_trigger_bodies_whole():
    script = (
        "CREATE TABLE a (x);\n"
        "CREATE TRIGGER t AFTER INSERT ON a BEGIN\n"
        "  INSERT INTO b VALUES (1);\n"
        "  INSERT INTO c VALUES ('semi;colon in string');\n"
        "END;\n"
        "DROP TABLE a"
    )
    stmts = [s.strip() for s in iter_sql_statements(script)]
    assert len(stmts) == 3
    assert stmts[0].startswith("CREATE TABLE a")
    assert stmts[1].startswith("CREATE TRIGGER")
    assert stmts[1].endswith("END;")
    assert stmts[2].startswith("DROP TABLE a")


# ---------- foreign_keys_disabled ----------


def _mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_foreign_keys_disabled_restores_prior_state():
    conn = _mem_conn()
    with foreign_keys_disabled(conn):
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        conn.execute("CREATE TABLE t (x)")
        conn.commit()
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_foreign_keys_disabled_refuses_open_transaction():
    conn = _mem_conn()
    conn.execute("CREATE TABLE t (x)")
    conn.execute("INSERT INTO t VALUES (1)")  # opens a transaction
    assert conn.in_transaction
    with pytest.raises(RuntimeError, match="silent no-op"), foreign_keys_disabled(conn):
        pass  # pragma: no cover
    conn.rollback()


def test_foreign_keys_disabled_rolls_back_and_restores_on_error():
    conn = _mem_conn()
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    with pytest.raises(ValueError, match="boom"), foreign_keys_disabled(conn):
        conn.execute("INSERT INTO t VALUES (1)")
        raise ValueError("boom")
    # Work rolled back, FK setting restored despite the exception.
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert not conn.in_transaction


def test_foreign_keys_disabled_requires_commit_before_exit():
    """Leaving the block with an open transaction means the restore
    PRAGMA would silently no-op — the exact trap class this context
    manager exists to kill. It must roll back and raise instead."""

    conn = _mem_conn()
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    with pytest.raises(RuntimeError, match="open transaction"), foreign_keys_disabled(conn):
        conn.execute("INSERT INTO t VALUES (1)")
        # no commit — contract violation
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
