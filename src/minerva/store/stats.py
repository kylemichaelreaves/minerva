"""Store statistics helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .chunks import chunk_count
from .embeddings import has_embeddings
from .schema import get_meta


def stats(conn: sqlite3.Connection) -> dict[str, object]:
    by_corpus = conn.execute(
        "SELECT corpus, lang, COUNT(*) FROM chunks_full GROUP BY corpus, lang ORDER BY 1, 2"
    ).fetchall()
    return {
        "chunks_total": chunk_count(conn),
        "chunks_by_corpus_lang": [
            {"corpus": c, "lang": lang, "count": n} for (c, lang, n) in by_corpus
        ],
        "embeddings_present": has_embeddings(conn),
        "embeddings_model": get_meta(conn, "embeddings.model"),
        "embeddings_dim": get_meta(conn, "embeddings.dim"),
        "ingest_source": get_meta(conn, "ingest.source"),
        "timing": _read_timing(conn),
    }


def _read_timing(conn: sqlite3.Connection) -> dict[str, float]:
    """Pull the persisted ``meta.timing.*`` keys (written by
    :func:`minerva.cli._shared.record_timing` after each CLI stage)
    into a stage→seconds map.

    Phase D of the 2026-05-30 remediation II plan — exposes the
    last-run wall times alongside chunk counts so ``minerva stats``
    answers \"what did the last reingest actually cost?\" without
    grepping stderr logs. Returns an empty dict on a fresh DB or one
    that's never been --timing'd.
    """

    rows = conn.execute(
        "SELECT key, value FROM meta WHERE key LIKE 'timing.%'"
    ).fetchall()
    out: dict[str, float] = {}
    for key, value in rows:
        # Strip the ``timing.`` prefix so callers see ``ingest`` /
        # ``embed`` / ``index`` directly. Values are stored as
        # ``"%.3f"`` strings; coerce back to float so JSON consumers
        # don't have to.
        out[key[len("timing."):]] = float(value)
    return out


def to_meta_dict(row: sqlite3.Row) -> dict[str, object]:
    # `sqlite3.Row` iterates over VALUES, not keys, so `.keys()` is the
    # only way to enumerate column names — ruff's SIM118 misreads this.
    return {k: row[k] for k in row.keys()}  # noqa: SIM118


def tables_summary(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """One entry per non-sqlite_internal table: name + row count.

    Used by ``minerva stats --tables`` to give a quick inventory of
    what's in the DB. Excludes the ``sqlite_*`` internal tables but
    INCLUDES the ``*_fts*`` FTS5 shadow tables — they're real rows
    that take real space, useful to see at a glance after a re-index.
    """

    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    out: list[dict[str, object]] = []
    for (name,) in rows:
        # Every name from sqlite_master is a real table identifier (no
        # user input), so this f-string is safe; use double quotes per
        # SQLite's identifier-quoting rules in case any table name
        # collides with a reserved word.
        n = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        out.append({"name": name, "rows": int(n)})
    return out


def db_inspect(conn: sqlite3.Connection, db_path: Path) -> dict[str, object]:
    """Storage- and schema-level info for ``minerva db inspect``.

    Complements :func:`stats` (which is data-shaped) with the
    physical view: file size on disk, page count and free pages,
    journal mode, the count of each schema-object kind (table /
    index / view / trigger), and the latest applied migration.
    Useful for sanity-checking a re-ingest and spotting vacuum-
    worthy free-list buildup.
    """

    size_bytes = Path(db_path).stat().st_size
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    page_count = conn.execute("PRAGMA page_count").fetchone()[0]
    freelist_count = conn.execute("PRAGMA freelist_count").fetchone()[0]
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    sqlite_version = conn.execute("SELECT sqlite_version()").fetchone()[0]
    obj_rows = conn.execute(
        "SELECT type, COUNT(*) FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' "
        "GROUP BY type ORDER BY type"
    ).fetchall()
    schema_objects = {kind: int(n) for kind, n in obj_rows}
    # Migrations table is present after the first index pass; guard
    # the query so this works on a fresh DB too.
    mig_count, latest_migration = 0, None
    has_migrations = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if has_migrations:
        mig_count, latest_migration = conn.execute(
            "SELECT COUNT(*), MAX(version) FROM schema_migrations"
        ).fetchone()
    return {
        "db_path": str(db_path),
        "db_size_bytes": int(size_bytes),
        "db_size_human": _human_bytes(size_bytes),
        "sqlite_version": sqlite_version,
        "page_size": int(page_size),
        "page_count": int(page_count),
        "freelist_count": int(freelist_count),
        "freelist_bytes": int(freelist_count) * int(page_size),
        "journal_mode": journal_mode,
        "schema_objects": schema_objects,
        "migrations_applied": int(mig_count),
        "latest_migration": latest_migration,
    }


def _human_bytes(n: float) -> str:
    """Compact ``1.6 GiB`` / ``347 MiB`` formatting for the inspector."""

    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PiB"
