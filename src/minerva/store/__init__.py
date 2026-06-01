"""SQLite-backed corpus store — package facade."""

from .chunks import (
    chunk_count,
    fetch_chunk_context,
    fetch_chunks,
    insert_chunks,
    iter_chunks,
    neighbor_ids,
)
from .embeddings import (
    blob_to_vector,
    count_chunks_without_embeddings,
    has_embeddings,
    invalidate_embedding_cache,
    iter_chunks_without_embeddings,
    load_all_embeddings,
    upsert_embeddings,
    vector_to_blob,
)
from .schema import SCHEMA, get_meta, open_db, reset_db
from .stats import db_inspect, stats, tables_summary, to_meta_dict

__all__ = [
    "SCHEMA",
    "blob_to_vector",
    "chunk_count",
    "count_chunks_without_embeddings",
    "db_inspect",
    "fetch_chunk_context",
    "fetch_chunks",
    "get_meta",
    "has_embeddings",
    "insert_chunks",
    "invalidate_embedding_cache",
    "iter_chunks",
    "iter_chunks_without_embeddings",
    "load_all_embeddings",
    "neighbor_ids",
    "open_db",
    "reset_db",
    "stats",
    "tables_summary",
    "to_meta_dict",
    "upsert_embeddings",
    "vector_to_blob",
]
