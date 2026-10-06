"""The runner records what a data-repair migration actually changed.

`schema_migrations` records that the code *ran*. For a schema change
those are the same fact — the column either exists or it does not. For
a data repair they are different facts, and #551 is what the gap costs:
`0035_relink_targets` was applied to a developer index on 2026-09-08,
three days before the branch merged, found nothing to link because the
corpus had not caught up yet, and was then skipped forever. The version
was recorded, the four rows stayed unlinked, and nothing said so.

A migration opts into being measured by returning its row count from
`apply()`. Returning None — every schema migration, and every `.sql`
file — records NULL and is never warned about.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from minerva import migrations, store
from minerva.sqlite_util import execute_script_statements


def _py_probe(version: int, changed):
    """A `.py`-shaped probe whose `apply` returns ``changed``."""

    def _apply(conn: sqlite3.Connection):
        conn.execute("CREATE TABLE IF NOT EXISTS probe_marker (x INTEGER)")
        return changed

    return (version, f"{version:04d}_probe_repair", "py", _apply)


def _sql_probe(version: int):
    return (
        version,
        f"{version:04d}_probe_schema",
        "sql",
        lambda conn: execute_script_statements(conn, "CREATE TABLE probe_schema (x INTEGER);\n"),
    )


def _row(conn: sqlite3.Connection, version: int):
    return conn.execute(
        "SELECT name, rows_changed FROM schema_migrations WHERE version = ?",
        (version,),
    ).fetchone()


def test_a_repair_records_the_rows_it_changed(tmp_path: Path, monkeypatch):
    conn = store.open_db(tmp_path / "m.sqlite")
    real = migrations._discover()
    monkeypatch.setattr(migrations, "_discover", lambda: [*real, _py_probe(9910, 7)])
    migrations.apply(conn)

    assert _row(conn, 9910)["rows_changed"] == 7


def test_a_repair_that_changed_nothing_on_an_existing_db_says_so(
    tmp_path: Path, monkeypatch, capsys
):
    """The #551 case exactly: an established database, a repair that
    finds nothing, a version recorded anyway."""

    conn = store.open_db(tmp_path / "m.sqlite")
    real = migrations._discover()
    monkeypatch.setattr(migrations, "_discover", lambda: [*real, _py_probe(9911, 0)])
    migrations.apply(conn)

    assert _row(conn, 9911)["rows_changed"] == 0
    err = capsys.readouterr().err
    assert "9911_probe_repair" in err
    assert "changed 0 rows" in err
    # The warning has to say why it matters, or it reads as noise.
    assert "will not be retried" in err


def test_a_fresh_database_is_not_warned_about(tmp_path: Path, monkeypatch, capsys):
    """A repair legitimately finds nothing on an empty database — every
    migration applies in one pass and there is no data to repair yet.
    Warning there would put a false positive in front of every fresh
    checkout and every test, which is how a real signal gets ignored.
    """

    conn = sqlite3.connect(tmp_path / "fresh.sqlite")
    conn.row_factory = sqlite3.Row
    monkeypatch.setattr(migrations, "_discover", lambda: [_py_probe(9912, 0)])
    migrations.apply(conn)

    assert _row(conn, 9912)["rows_changed"] == 0
    assert "9912" not in capsys.readouterr().err
    conn.close()


def test_a_schema_migration_records_null_not_zero(tmp_path: Path, monkeypatch, capsys):
    """`apply()` returning None means "not measured", which is not the
    same as "measured, zero" — and only the second is worth a warning."""

    conn = store.open_db(tmp_path / "m.sqlite")
    real = migrations._discover()
    monkeypatch.setattr(
        migrations,
        "_discover",
        lambda: [*real, _sql_probe(9913), _py_probe(9914, None)],
    )
    migrations.apply(conn)

    assert _row(conn, 9913)["rows_changed"] is None
    assert _row(conn, 9914)["rows_changed"] is None
    err = capsys.readouterr().err
    assert "9913" not in err and "9914" not in err


def test_the_column_is_added_to_a_pre_existing_bookkeeping_table(tmp_path: Path):
    """Databases written before this change have the three-column table.
    The runner owns `schema_migrations`, so it widens it itself rather
    than through a migration — which would have to run before the table
    it records into could hold the result of running it."""

    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
        "name TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    # Version 9999 matches no migration file, so the real chain still
    # applies in full and this row is left alone to be inspected.
    conn.execute("INSERT INTO schema_migrations(version, name) VALUES (9999, 'old')")
    conn.commit()
    conn.close()

    conn = store.open_db(path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(schema_migrations)")}
    assert "rows_changed" in cols
    # The pre-existing row survives, with no invented count.
    assert (
        conn.execute("SELECT rows_changed FROM schema_migrations WHERE version = 9999").fetchone()[
            0
        ]
        is None
    )
