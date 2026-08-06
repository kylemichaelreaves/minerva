"""Shared SQLite connection helpers for satellite databases."""

from __future__ import annotations

import contextlib
import re
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path


def open_sqlite(
    path: Path,
    schema: str,
    *,
    foreign_keys: bool = True,
    check_same_thread: bool = True,
    post_open: object | None = None,
) -> sqlite3.Connection:
    """Open a SQLite file, apply ``schema``, optionally run ``post_open``.

    ``post_open`` receives the connection after ``executescript`` — used
    by the corpus store to run migrations.

    Connections come back with ``row_factory = sqlite3.Row``. Rows
    still support index access and unpacking, so tuple-style callers
    keep working; setting it once here replaced ~34 scattered
    per-function mutations whose only failure mode was a caller that
    relied on the side effect never being undone.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    if foreign_keys:
        conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema)
    if post_open is not None:
        post_open(conn)
    conn.commit()
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    """True when ``name`` exists as a table on ``conn``."""

    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


@contextlib.contextmanager
def foreign_keys_disabled(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Temporarily disable FK enforcement, restoring the prior setting.

    ``PRAGMA foreign_keys`` is a silent no-op while a transaction is
    open, so this context manager enforces the choreography at both
    edges: it refuses to start inside an open transaction, and it
    requires the caller to have committed before the block ends (an
    exception unwinding through it rolls back first) so the restore
    PRAGMA actually takes effect.
    """

    if conn.in_transaction:
        raise RuntimeError(
            "foreign_keys_disabled: a transaction is already open — "
            "PRAGMA foreign_keys would be a silent no-op. Commit or "
            "roll back before entering."
        )
    prev = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    restore = f"PRAGMA foreign_keys = {'ON' if prev else 'OFF'}"
    try:
        yield conn
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        conn.execute(restore)
        raise
    if conn.in_transaction:
        conn.rollback()
        conn.execute(restore)
        raise RuntimeError(
            "foreign_keys_disabled: block ended with an open transaction; "
            "commit inside the block so the FK restore isn't a no-op. "
            "(The uncommitted work has been rolled back.)"
        )
    conn.execute(restore)


@contextlib.contextmanager
def foreign_keys_off_for_transaction(
    conn: sqlite3.Connection,
) -> Iterator[sqlite3.Connection]:
    """Disable FK enforcement for a block that commits or rolls back inside.

    Unlike :func:`foreign_keys_disabled`, this allows an open transaction
    and restores the prior ``PRAGMA foreign_keys`` setting after commit or
    rollback — the pattern ``insert_chunks`` needs for its destructive
    delete/insert/rebind sequence.
    """

    prev = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    conn.execute("PRAGMA foreign_keys = OFF")
    restore = f"PRAGMA foreign_keys = {'ON' if prev else 'OFF'}"
    try:
        yield conn
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        conn.execute(restore)
        raise
    conn.execute(restore)


def sweep_orphan_chunk_ids(
    conn: sqlite3.Connection,
    table: str,
    *,
    column: str = "chunk_id",
    commit: bool = True,
) -> int:
    """Delete rows in ``table`` whose ``column`` is absent from ``chunks``.

    ``column`` names the chunk-referencing column, which is not always
    called ``chunk_id`` — ``term_occurrences`` anchors through
    ``source_chunk_id`` and ``occurrence_renderings`` through
    ``translation_chunk_id``.

    Returns the number of rows dropped. No-op when ``table`` is missing
    or empty.
    """

    if not table_exists(conn, table):
        return 0
    if conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is None:
        return 0
    before = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.execute(f"DELETE FROM {table} WHERE {column} NOT IN (SELECT chunk_id FROM chunks)")
    after = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if commit:
        conn.commit()
    return before - after


def iter_sql_statements(script: str) -> Iterator[str]:
    """Split a multi-statement SQL script into individual statements.

    Boundaries are detected with :func:`sqlite3.complete_statement`,
    so semicolons inside trigger bodies and string literals don't
    split. Leading comments stay attached to the statement they
    precede.
    """

    buf = ""
    for piece in script.split(";"):
        buf += piece + ";"
        if sqlite3.complete_statement(buf):
            yield buf
            buf = ""
    if buf.strip():
        # Script ended without a terminating semicolon.
        yield buf


def _sql_has_content(stmt: str) -> bool:
    """True when ``stmt`` contains SQL beyond comments/semicolons."""

    stripped = re.sub(r"/\*.*?\*/", "", stmt, flags=re.S)
    stripped = re.sub(r"--[^\n]*", "", stripped)
    return bool(stripped.replace(";", "").strip())


def execute_script_statements(conn: sqlite3.Connection, script: str) -> None:
    """Run a multi-statement SQL script one ``execute`` at a time.

    Unlike ``Connection.executescript`` — which issues a COMMIT before
    running and autocommits statement-by-statement — this keeps every
    statement inside whatever transaction is currently open, so a
    failure mid-script rolls the whole script back with it.
    """

    for stmt in iter_sql_statements(script):
        if _sql_has_content(stmt):
            conn.execute(stmt)


def insert_with_shadow_retry(
    *,
    max_retries: int,
    next_index: Callable[[], int],
    do_insert: Callable[[int], int],
    unique_table_substring: str,
    exhausted_error: Callable[[sqlite3.IntegrityError | None], Exception],
) -> int:
    """Insert with shadow-address ``instance_index`` retry on UNIQUE races."""

    last_error: sqlite3.IntegrityError | None = None
    for _attempt in range(max_retries):
        idx = next_index()
        try:
            return do_insert(idx)
        except sqlite3.IntegrityError as exc:
            msg = str(exc).lower()
            if unique_table_substring in msg and "unique" in msg:
                last_error = exc
                continue
            raise
    raise exhausted_error(last_error)
