"""Shared SQLite connection helpers for satellite databases."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
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
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    if foreign_keys:
        conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema)
    if post_open is not None:
        post_open(conn)
    conn.commit()
    return conn


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
