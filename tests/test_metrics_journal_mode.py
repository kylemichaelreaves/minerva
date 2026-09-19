"""The metrics DB runs in WAL (#617).

Every metrics write is one transaction on the request path, and in the SQLite
default (`journal_mode=delete`) each commit is an fsync of a rollback journal.
Measured on the current schema, 20,000 insert+commit:

    DELETE + synchronous=FULL   315.43 us      <- was
    WAL    + synchronous=FULL    57.34 us      <- is

The comparison is FULL-to-FULL, so this buys 5.5x at **no** change in
durability. `synchronous=NORMAL` would buy another 24 us and is deliberately
not taken — losing the last few timing samples on power loss is cheap, but the
same relaxation applied elsewhere would not be, and this module should not
model that trade for others.

Not novel: `data/index.sqlite` has been WAL all along.
"""

from __future__ import annotations

import sqlite3

from minerva.metrics import store as m


def _pragma(conn: sqlite3.Connection, name: str):
    return conn.execute(f"PRAGMA {name}").fetchone()[0]


def test_a_new_metrics_db_is_wal(tmp_path):
    conn = m.open_db(tmp_path / "metrics.sqlite")
    assert _pragma(conn, "journal_mode") == "wal"
    conn.close()


def test_durability_is_unchanged(tmp_path):
    """`synchronous` stays FULL. The speed-up comes from the journal mode, and
    a test that let NORMAL through would silently accept a different trade."""

    conn = m.open_db(tmp_path / "metrics.sqlite")
    assert _pragma(conn, "synchronous") == 2  # 2 == FULL
    conn.close()


def test_an_existing_delete_mode_database_is_converted(tmp_path):
    """`data/metrics.sqlite` already exists on operator machines in `delete`
    mode. Journal mode is a property of the FILE, so opening it has to convert
    it — otherwise the fix applies only to machines that never ran the server
    before."""

    path = tmp_path / "metrics.sqlite"
    plain = sqlite3.connect(path)
    plain.executescript(m.SCHEMA)
    plain.commit()
    assert _pragma(plain, "journal_mode") == "delete"
    plain.close()

    conn = m.open_db(path)
    assert _pragma(conn, "journal_mode") == "wal"
    conn.close()


def test_rows_survive_the_conversion(tmp_path):
    path = tmp_path / "metrics.sqlite"
    plain = sqlite3.connect(path)
    plain.executescript(m.SCHEMA)
    plain.execute(
        "INSERT INTO request_spans (id,at,label,method,status,total_ms,accounted_ms,phases)"
        " VALUES ('keep', 1.0, 'works list', 'GET', 200, 5.0, 0.0, '[]')"
    )
    plain.commit()
    plain.close()

    conn = m.open_db(path)
    assert conn.execute("SELECT id FROM request_spans").fetchone()[0] == "keep"
    conn.close()


def test_the_other_satellite_databases_are_left_alone(tmp_path):
    """Scope. `conversations`, `translations` and `concept_cache` are on the
    default for no recorded reason and have not been measured; changing them
    here would be an unmeasured change riding along with a measured one."""

    from minerva import conversations

    conn = conversations.open_db(tmp_path / "conv.sqlite")
    assert _pragma(conn, "journal_mode") == "delete"
    conn.close()
