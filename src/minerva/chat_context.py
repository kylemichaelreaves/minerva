"""Domain context for chat orchestration — no HTTP-layer types."""

from __future__ import annotations

import dataclasses
import sqlite3
import threading

from . import embed as embed_mod
from . import llm


@dataclasses.dataclass
class ChatContext:
    index_conn: sqlite3.Connection
    conversations_conn: sqlite3.Connection
    concept_cache_conn: sqlite3.Connection | None
    backend: llm.LLMBackend
    embedder: embed_mod.Embedder | None
    lang: str | None
    corpus: str | None
    speaker: str | None
    top_k: int
    allow_client_rewrite: bool = True
    force_rewrite: bool = True
    enable_concept_expand: bool = True
    corpus_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    conv_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    concept_cache_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)

    @property
    def conn(self) -> sqlite3.Connection:
        """Alias used by retrieval helpers."""
        return self.index_conn
