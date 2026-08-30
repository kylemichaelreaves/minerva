"""Embedding storage and cache invalidation."""

from __future__ import annotations

import dataclasses
import sqlite3
import threading
from collections.abc import Iterable, Iterator

import numpy as np

from .schema import _set_meta, get_meta


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

    rows = [(cid, model, dim, vector_to_blob(v), cid) for cid, v in items]
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO embeddings(chunk_id, model, dim, vector, text_hash) "
        "VALUES (?, ?, ?, ?, (SELECT text_hash(text) FROM chunks WHERE chunk_id = ?))",
        rows,
    )
    _set_meta(conn, "embeddings.model", model)
    _set_meta(conn, "embeddings.dim", str(dim))
    bump_embedding_generation(conn)
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
    """Stream chunks that don't yet have a *current* embedding under ``model``.

    Skips a chunk when ``embeddings.chunk_id = chunks_full.chunk_id``,
    ``embeddings.model = ?``, AND ``embeddings.text_hash`` matches the
    chunk's current text. A model change therefore forces re-encoding —
    the ``INSERT OR REPLACE`` in ``upsert_embeddings`` overwrites the old
    vector — and so does a text edit, including one past character 120,
    where ``tei._make_chunk_id`` keeps the chunk's id and a bare
    ``(chunk_id, model)`` check would otherwise miss it forever (#285).
    Pairs with ``count_chunks_without_embeddings`` so ``cmd_embed`` can
    show progress against a known total without materializing every row
    in memory.

    Closes the ``embeddings`` doc/code mismatch documented in
    ``docs/INGESTION.md`` and called out in the 2026-05-29 ingestion-
    bottleneck remediation plan as Phase 1a.

    Relies on ``store.open_db`` having registered the ``text_hash()``
    SQL function on ``conn`` — not repeated here, because re-registering
    it while a caller (``cmd_embed``) still has an open cursor from a
    prior call to this generator raises "Error creating function".
    """

    if lang is None:
        cursor = conn.execute(
            "SELECT cf.* FROM chunks_full cf "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM embeddings e "
            "  WHERE e.chunk_id = cf.chunk_id AND e.model = ? "
            "        AND e.text_hash = text_hash(cf.text)"
            ") "
            "ORDER BY cf.chunk_id",
            (model,),
        )
    else:
        cursor = conn.execute(
            "SELECT cf.* FROM chunks_full cf "
            "WHERE cf.lang = ? AND NOT EXISTS ("
            "  SELECT 1 FROM embeddings e "
            "  WHERE e.chunk_id = cf.chunk_id AND e.model = ? "
            "        AND e.text_hash = text_hash(cf.text)"
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
    the whole result set in memory. Same reliance on ``store.open_db``
    having registered ``text_hash()`` as its neighbour above."""

    if lang is None:
        row = conn.execute(
            "SELECT COUNT(*) FROM chunks_full cf "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM embeddings e "
            "  WHERE e.chunk_id = cf.chunk_id AND e.model = ? "
            "        AND e.text_hash = text_hash(cf.text)"
            ")",
            (model,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) FROM chunks_full cf "
            "WHERE cf.lang = ? AND NOT EXISTS ("
            "  SELECT 1 FROM embeddings e "
            "  WHERE e.chunk_id = cf.chunk_id AND e.model = ? "
            "        AND e.text_hash = text_hash(cf.text)"
            ")",
            (lang, model),
        ).fetchone()
    return int(row[0])


# Monotonic generation counter for the embeddings table, stored in
# `meta`. Every code path that writes embeddings bumps it (the store
# insert helper above; `cmd_embed` writes through that helper). The
# cache below keys freshness on (generation, row count) — the row
# count alone misses a same-count re-embed (new vectors, same ids),
# and `id(conn)` alone can be reused by a different connection after
# close. DBs predating the key read as generation 0 (still validated
# on row count, as before).
_GENERATION_KEY = "embeddings.generation"


def embedding_generation(conn: sqlite3.Connection) -> int:
    raw = get_meta(conn, _GENERATION_KEY)
    try:
        return int(raw) if raw is not None else 0
    except ValueError:
        return 0


def bump_embedding_generation(conn: sqlite3.Connection) -> None:
    """Increment the embeddings generation counter. Call after any
    write to the embeddings table (insert, replace, delete)."""

    _set_meta(conn, _GENERATION_KEY, str(embedding_generation(conn) + 1))


@dataclasses.dataclass
class EmbeddingChunkMeta:
    """Per-chunk filter columns aligned 1:1 with the cached embedding
    ids/matrix. Fixed-width numpy arrays so vector-search filters run
    as vectorized comparisons instead of a per-request Python loop.
    Chunks missing from `chunks_full` (orphan embeddings) get sentinel
    values that fail every filter — same semantics as the old
    per-request dict lookup with a MISS default."""

    langs: np.ndarray  # unicode
    corpora: np.ndarray  # unicode
    speakers_lower: np.ndarray  # unicode, lowercased, "" for NULL
    text_lens: np.ndarray  # int64, 0 for missing
    work_ids: np.ndarray  # int64, -1 for NULL/missing
    block_types: np.ndarray  # unicode structural role, "" for body/NULL


@dataclasses.dataclass
class _CacheEntry:
    generation: int
    row_count: int
    ids: list[str]
    matrix: np.ndarray
    # Lazily built on the first *filtered* vector search; unfiltered
    # searches never pay for the chunks_full scan.
    meta: EmbeddingChunkMeta | None = None


# Embedding matrix cache. The corpus is ~35k chunks today; reading
# every embedding row + stacking into a float32 matrix on each hybrid
# search dominated retrieval latency at scale. We memoize keyed on the
# connection's `id()`, with freshness validated against the generation
# counter + row count above.
#
# Module-level dict, not per-connection, because the connection identity
# survives across server requests (one connection per worker process).
# Cleared by `upsert_embeddings` so a fresh embed run on a live server
# is reflected immediately.
_EMBEDDING_CACHE: dict[int, _CacheEntry] = {}
# Serialize cache misses so two concurrent first-requests don't both
# stack-load the full embeddings table (audit-flagged: a heavy load
# under the corpus lock could chew CPU + memory at startup). Hits stay
# lock-free — the dict.get is atomic in CPython and we only block on
# the slow load path.
_EMBEDDING_CACHE_LOCK = threading.Lock()


def _fresh_entry(conn: sqlite3.Connection) -> _CacheEntry:
    row_count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    generation = embedding_generation(conn)
    cached = _EMBEDDING_CACHE.get(id(conn))
    if cached is not None and cached.row_count == row_count and cached.generation == generation:
        return cached
    # Slow path. Acquire the lock and re-check — another thread may
    # have populated the cache while we were waiting (the classic
    # double-checked-locking pattern, but safe in CPython because dict
    # mutation is atomic).
    with _EMBEDDING_CACHE_LOCK:
        cached = _EMBEDDING_CACHE.get(id(conn))
        if cached is not None and cached.row_count == row_count and cached.generation == generation:
            return cached
        rows = conn.execute("SELECT chunk_id, vector FROM embeddings ORDER BY chunk_id").fetchall()
        if not rows:
            entry = _CacheEntry(generation, 0, [], np.zeros((0, 0), dtype=np.float32))
        else:
            ids = [r[0] for r in rows]
            vectors = np.stack([blob_to_vector(r[1]) for r in rows])
            entry = _CacheEntry(generation, row_count, ids, vectors)
        _EMBEDDING_CACHE[id(conn)] = entry
        return entry


def load_all_embeddings(
    conn: sqlite3.Connection,
) -> tuple[list[str], np.ndarray]:
    entry = _fresh_entry(conn)
    return entry.ids, entry.matrix


def load_embeddings_with_meta(
    conn: sqlite3.Connection,
) -> tuple[list[str], np.ndarray, EmbeddingChunkMeta]:
    """`load_all_embeddings` plus the aligned per-chunk filter columns.

    The meta arrays are memoized alongside the matrix with the same
    invalidation, so filtered vector searches don't re-scan
    `chunks_full` (~hundreds of k rows through view joins) on every
    request — audit-flagged as the dominant per-request cost under
    `corpus_lock`."""

    entry = _fresh_entry(conn)
    if entry.meta is not None:
        return entry.ids, entry.matrix, entry.meta
    with _EMBEDDING_CACHE_LOCK:
        if entry.meta is not None:
            return entry.ids, entry.matrix, entry.meta
        by_id = {
            r[0]: (r[1], r[2], r[3], r[4], r[5], r[6])
            for r in conn.execute(
                "SELECT chunk_id, lang, corpus, speaker, length(text), work_id, block_type "
                "FROM chunks_full"
            )
        }
        miss = ("", "", "", 0, None, None)
        cols = [by_id.get(cid, miss) for cid in entry.ids]
        entry.meta = EmbeddingChunkMeta(
            langs=np.array([c[0] or "" for c in cols], dtype=np.str_),
            corpora=np.array([c[1] or "" for c in cols], dtype=np.str_),
            speakers_lower=np.array([(c[2] or "").lower() for c in cols], dtype=np.str_),
            text_lens=np.array([c[3] or 0 for c in cols], dtype=np.int64),
            work_ids=np.array([c[4] if c[4] is not None else -1 for c in cols], dtype=np.int64),
            block_types=np.array([c[5] or "" for c in cols], dtype=np.str_),
        )
        return entry.ids, entry.matrix, entry.meta


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
