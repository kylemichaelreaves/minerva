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
  int | None``. Use these when the migration needs branching logic or
  row-by-row processing that would be unreadable in pure SQL. The runner
  loads them via ``importlib.util`` so they can live alongside the
  ``.sql`` peers.
* **A migration that repairs data returns the number of rows it
  changed.** The runner stores it in ``schema_migrations.rows_changed``
  and prints a warning when an established database gets 0 — because
  "applied" means the code ran, which is the same fact as "the schema
  changed" and a different fact from "the repair happened". #551 is the
  difference: ``0035_relink_targets`` was applied to a developer index
  three days before its branch merged, found the corpus not yet in the
  state it expected, changed nothing, and was never revisited. Returning
  None means "not measured" and is right for every schema migration;
  it is 0 that is worth reporting, so do not return 0 for "not
  applicable".
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
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            -- Rows the migration reported changing, or NULL when it
            -- reported nothing. NULL and 0 are different facts: the
            -- first means "not measured" (every .sql file, every schema
            -- change), the second means "measured, and it did nothing".
            -- Only the second is worth anyone's attention. See #551.
            rows_changed INTEGER
        )
        """
    )
    # Databases written before this column existed carry the three-column
    # table. Widened here rather than by a numbered migration because
    # this table is the runner's own bookkeeping — a migration that adds
    # the column would have to run before there was anywhere to record
    # the result of running it.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(schema_migrations)")}
    if "rows_changed" not in cols:
        conn.execute("ALTER TABLE schema_migrations ADD COLUMN rows_changed INTEGER")


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


def _warn_repair_did_nothing(stem: str, version: int) -> None:
    """A data repair ran and changed nothing on an established database.

    Not an error: it is legitimate when an earlier run already did the
    work. It is reported because the failure it also describes is
    invisible otherwise — #551's `0035_relink_targets` ran against a
    developer index three days before its branch merged, found the
    corpus not yet in the state it expected, and was recorded as applied.
    The four rows it existed to fix stayed broken, and the runner never
    looked at that version again.
    """

    print(
        f"warning: migration {stem} ran and changed 0 rows. Version "
        f"{version} is now recorded as applied and will not be retried. "
        f"If this database holds the data the repair targets, re-run its "
        f"`apply()` directly once the data is in place.",
        file=sys.stderr,
    )


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
    # An established database being upgraded, as against a fresh one
    # bootstrapping. A repair that changes nothing is expected on a fresh
    # database — there is no data to repair yet — and suspicious on an
    # established one. Warning on both would put a false positive in
    # front of every new checkout and every test, which is how a real
    # signal gets tuned out.
    preexisting = bool(applied)
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
            # A data repair reports what it changed by returning a count.
            # Anything else returns None and is recorded as unmeasured.
            changed = runner(conn)
            if not isinstance(changed, int) or isinstance(changed, bool):
                changed = None
            conn.execute(
                "INSERT INTO schema_migrations(version, name, rows_changed) "
                "VALUES (?, ?, ?)",
                (version, stem, changed),
            )
            conn.commit()
            if changed == 0 and preexisting:
                _warn_repair_did_nothing(stem, version)
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
