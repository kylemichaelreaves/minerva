"""Forward-only schema migrations for `data/index.sqlite`.

Each numbered ``NNNN_name.sql`` or ``NNNN_name.py`` file in this
directory is applied once, in version order, and recorded in
``schema_migrations``. The runner is called from ``store.open_db()``
so a fresh checkout and an existing database converge on the same
schema without manual steps.

Conventions
-----------
* File names: ``0001_term_glossary.sql``, ``0003_chunks_backfill.py``.
  Four-digit zero-padded version, snake_case description. The version
  prefix is what's tracked; the description is for humans.
* ``.sql`` files may hold multiple statements separated by ``;``. The
  runner executes them statement-by-statement inside one explicit
  transaction — NEVER via ``executescript``, whose implicit COMMITs
  would persist a half-applied script with the version unrecorded
  (re-apply then fails on e.g. "duplicate column" and the DB is
  wedged).
* ``.py`` files must define ``def apply(conn: sqlite3.Connection) ->
  None``. Use these when the migration needs branching logic or row-
  by-row processing that would be unreadable in pure SQL. The runner
  loads them via ``importlib.util`` so they can live alongside the
  ``.sql`` peers.
* ``.py`` migrations MUST NOT call ``conn.executescript`` (same
  implicit-COMMIT trap; use ``sqlite_util.execute_script_statements``
  or plain ``execute`` loops — see 0021/0022 for the pattern). A
  migration that needs PRAGMAs (``foreign_keys``,
  ``legacy_alter_table``) must set them BEFORE opening its own
  explicit ``BEGIN`` — PRAGMAs are silent no-ops inside a
  transaction — and commit before restoring them (see 0003/0013).
* If a migration raises, the runner rolls back and the version is
  NOT recorded, so the next ``open_db`` retries it. ``.py``
  migrations must therefore be re-entrant against a partially
  committed prior attempt (idempotency guards like 0003's
  column probe / 0021's ``IF NOT EXISTS``).
* No down migrations. Adding a column or table is forward-only; if a
  decision needs reversing, write a new migration that does it.
* The legacy ``chunks`` / ``chunks_fts`` / ``embeddings`` / ``meta``
  tables defined in ``store.SCHEMA`` exist BEFORE this runner ran the
  first time; subsequent reshape happens here.

The runner is intentionally minimal (no Alembic, no SQLAlchemy). The
repo is single-process, single-developer; ~80 lines of stdlib is the
right size.
"""

from __future__ import annotations

import importlib.util
import re
import sqlite3
import sys
from importlib import resources
from pathlib import Path
from typing import Callable

from minerva.sqlite_util import execute_script_statements


_VERSION_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.(sql|py)$")


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _discover() -> list[tuple[int, str, str, Callable[[sqlite3.Connection], None]]]:
    """Return ``(version, stem, kind, runner)`` for every migration file
    present, sorted by version. ``kind`` is ``'sql'`` or ``'py'``;
    ``runner`` is a callable that applies the migration to a given
    connection. Files that don't match the naming convention are
    skipped silently so editor backups (``.sql.bak``) don't break the
    runner."""

    out: list[tuple[int, str, str, Callable[[sqlite3.Connection], None]]] = []
    root = resources.files(__package__)
    for entry in root.iterdir():
        name = entry.name
        m = _VERSION_RE.match(name)
        if not m:
            continue
        version = int(m.group(1))
        kind = m.group(2)
        stem = name[: -(len(kind) + 1)]
        if kind == "sql":
            sql = entry.read_text(encoding="utf-8")
            runner = (
                lambda script=sql: lambda conn: execute_script_statements(conn, script)
            )()
        else:
            # importlib by file path. We don't go through `__package__` /
            # `from . import` because we don't want to expose migration
            # modules under the package namespace; they're one-shot
            # scripts, not API.
            path = Path(str(entry))
            mod_name = f"_minerva_migration_{stem}"
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"could not load migration {name}")
            module = importlib.util.module_from_spec(spec)
            # Insert into sys.modules so relative imports inside the
            # migration (rare but allowed) resolve.
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            if not hasattr(module, "apply"):
                raise RuntimeError(
                    f"migration {name} must define `apply(conn)`"
                )
            runner = module.apply
        out.append((version, stem, kind, runner))
    out.sort(key=lambda t: t[0])
    return out


def apply(conn: sqlite3.Connection) -> list[int]:
    """Apply pending migrations to ``conn`` and return the versions that
    ran. Idempotent: a connection that's already up-to-date returns
    an empty list.

    The caller is expected to have ``PRAGMA foreign_keys = ON`` set;
    new schemas declared by migrations rely on FK enforcement for
    cascading deletes.
    """

    _ensure_table(conn)
    applied: set[int] = {
        row[0] for row in conn.execute("SELECT version FROM schema_migrations")
    }
    ran: list[int] = []
    for version, stem, kind, runner in _discover():
        if version in applied:
            continue
        try:
            # .sql migrations get one explicit transaction around the
            # whole script + version record: DDL statements don't
            # auto-begin a transaction in Python's legacy isolation
            # mode, so without this a failure mid-script would leave
            # earlier statements committed with the version unrecorded.
            # .py migrations manage their own transaction shape (they
            # may need PRAGMAs, which are no-ops inside an open
            # transaction) — see the module docstring conventions.
            if kind == "sql" and not conn.in_transaction:
                conn.execute("BEGIN")
            runner(conn)
            conn.execute(
                "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
                (version, stem),
            )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        ran.append(version)
    return ran


def current_version(conn: sqlite3.Connection) -> int | None:
    """Highest applied migration version, or None if the table is empty."""

    _ensure_table(conn)
    row = conn.execute(
        "SELECT MAX(version) FROM schema_migrations"
    ).fetchone()
    return row[0] if row and row[0] is not None else None


# Re-exported for tests that need the path on disk (e.g., to write
# a probe migration).
def migrations_dir() -> Path:
    """Return the on-disk directory holding migration .sql files. Only
    meaningful when running from a regular checkout; raises if minerva
    is installed from a zipped wheel."""

    root = resources.files(__package__)
    # `Path(traversable)` works for regular dir layouts.
    return Path(str(root))
