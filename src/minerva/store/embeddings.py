"""Embedding storage and cache invalidation."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable, Iterator

import numpy as np

from .schema import _set_meta


def vector_to_blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def blob_to_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def upsert_embeddings(
    conn: sqlite3.Connection,
    *,
    model: str,
    dim: int,
    items: Iterable[tuple[str, np.ndarray]],
    invalidate_cache: bool = True,
    commit: bool = True,
) -> int:
    """Insert-or-replace a batch of ``(chunk_id, vector)`` rows.

    ``invalidate_cache`` and ``commit`` default to True for callers
    that only run a single batch. Long-running batch loops
    (``cmd_embed``) override both to False, calling
    ``conn.commit()`` once per N batches and
    ``invalidate_embedding_cache(conn)`` once at the end — the
    previous per-batch invalidation was an audit-flagged hot-path
    waste (the cache rebuild on the next retrieval re-stacks every
    embedding row).
    """

    rows = [(cid, model, dim, vector_to_blob(v)) for cid, v in items]
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO embeddings(chunk_id, model, dim, vector) VALUES (?, ?, ?, ?)",
        rows,
    )
    _set_meta(conn, "embeddings.model", model)
    _set_meta(conn, "embeddings.dim", str(dim))
    if commit:
        conn.commit()
    if invalidate_cache:
        # Embeddings just changed — drop the cached matrix for this conn
        # so the next vector search rebuilds against the new rows.
        invalidate_embedding_cache(conn)
    return len(rows)


def has_embeddings(conn: sqlite3.Connection) -> bool:
    return bool(conn.execute("SELECT 1 FROM embeddings LIMIT 1").fetchone())


def iter_chunks_without_embeddings(
    conn: sqlite3.Connection,
    *,
    model: str,
    lang: str | None = None,
) -> Iterator[sqlite3.Row]:
    """Stream chunks that don't yet have an embedding under ``model``.

    Skips a chunk when ``embeddings.chunk_id = chunks_full.chunk_id``
    AND ``embeddings.model = ?``. A model change therefore forces
    re-encoding — the ``INSERT OR REPLACE`` in ``upsert_embeddings``
    overwrites the old vector. Pairs with ``count_chunks_without_embeddings``
    so ``cmd_embed`` can show progress against a known total without
    materializing every row in memory.

    Closes the ``embeddings`` doc/code mismatch documented in
    ``docs/INGESTION.md`` and called out in the 2026-05-29 ingestion-
    bottleneck remediation plan as Phase 1a.
    """

    conn.row_factory = sqlite3.Row
    if lang is None:
        cursor = conn.execute(
            "SELECT cf.* FROM chunks_full cf "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM embeddings e "
            "  WHERE e.chunk_id = cf.chunk_id AND e.model = ?"
            ") "
            "ORDER BY cf.chunk_id",
            (model,),
        )
    else:
        cursor = conn.execute(
            "SELECT cf.* FROM chunks_full cf "
            "WHERE cf.lang = ? AND NOT EXISTS ("
            "  SELECT 1 FROM embeddings e "
            "  WHERE e.chunk_id = cf.chunk_id AND e.model = ?"
            ") "
            "ORDER BY cf.chunk_id",
            (lang, model),
        )
    yield from cursor


def count_chunks_without_embeddings(
    conn: sqlite3.Connection,
    *,
    model: str,
    lang: str | None = None,
) -> int:
    """Cheap COUNT(*) twin of ``iter_chunks_without_embeddings``. Used
    by ``cmd_embed`` to print "{n}/{total}" progress without holding
    the whole result set in memory."""

    if lang is None:
        row = conn.execute(
            "SELECT COUNT(*) FROM chunks_full cf "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM embeddings e "
            "  WHERE e.chunk_id = cf.chunk_id AND e.model = ?"
            ")",
            (model,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) FROM chunks_full cf "
            "WHERE cf.lang = ? AND NOT EXISTS ("
            "  SELECT 1 FROM embeddings e "
            "  WHERE e.chunk_id = cf.chunk_id AND e.model = ?"
            ")",
            (lang, model),
        ).fetchone()
    return int(row[0])


# Embedding matrix cache. The corpus is ~35k chunks today; reading
# every embedding row + stacking into a float32 matrix on each hybrid
# search dominated retrieval latency at scale. We memoize keyed on the
# connection's `id()` and the embeddings row count: a re-ingest changes
# the count (and the chunks themselves), invalidating naturally.
#
# Module-level dict, not per-connection, because the connection identity
# survives across server requests (one connection per worker process).
# Cleared by `upsert_embeddings` so a fresh embed run on a live server
# is reflected immediately.
_EMBEDDING_CACHE: dict[int, tuple[int, list[str], np.ndarray]] = {}
# Serialize cache misses so two concurrent first-requests don't both
# stack-load the full embeddings table (audit-flagged: a heavy load
# under the corpus lock could chew CPU + memory at startup). Hits stay
# lock-free — the dict.get is atomic in CPython and we only block on
# the slow load path.
_EMBEDDING_CACHE_LOCK = threading.Lock()


def load_all_embeddings(
    conn: sqlite3.Connection,
) -> tuple[list[str], np.ndarray]:
    row_count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    cached = _EMBEDDING_CACHE.get(id(conn))
    if cached is not None and cached[0] == row_count:
        return cached[1], cached[2]
    # Slow path. Acquire the lock and re-check — another thread may
    # have populated the cache while we were waiting (the classic
    # double-checked-locking pattern, but safe in CPython because dict
    # mutation is atomic).
    with _EMBEDDING_CACHE_LOCK:
        cached = _EMBEDDING_CACHE.get(id(conn))
        if cached is not None and cached[0] == row_count:
            return cached[1], cached[2]
        rows = conn.execute(
            "SELECT chunk_id, vector FROM embeddings ORDER BY chunk_id"
        ).fetchall()
        if not rows:
            empty = ([], np.zeros((0, 0), dtype=np.float32))
            _EMBEDDING_CACHE[id(conn)] = (0, *empty)
            return empty
        ids = [r[0] for r in rows]
        vectors = np.stack([blob_to_vector(r[1]) for r in rows])
        _EMBEDDING_CACHE[id(conn)] = (row_count, ids, vectors)
        return ids, vectors


def invalidate_embedding_cache(conn: sqlite3.Connection | None = None) -> None:
    """Drop the embedding-matrix cache. Pass a specific connection to
    invalidate just its entry; pass nothing to wipe everything (useful
    in tests). Called by `upsert_embeddings` so an in-process embed run
    is reflected on the next retrieval."""

    with _EMBEDDING_CACHE_LOCK:
        if conn is None:
            _EMBEDDING_CACHE.clear()
        else:
            _EMBEDDING_CACHE.pop(id(conn), None)

