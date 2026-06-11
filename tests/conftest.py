"""Shared pytest fixtures for the backend test suite.

Provides:
- `make_chunk` — build a chunk dict with sane defaults
- `db_path` / `populated_db` — in-temp-dir SQLite store
- `StubBackend` — fake `llm.LLMBackend` that captures messages
- `make_hit` — build a `retrieve.Hit` with sane defaults
- `make_deps` — assemble a `server.ServerDeps` for handler tests
- `deps_with_rewrite` — `make_deps` with `force_rewrite=True`
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Any

import pytest

from minerva import conversations, llm, retrieve, server, store, translations


def make_chunk(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "chunk_id": "c1",
        "corpus": "plato",
        "author": "Plato",
        "work": "Republic",
        "lang": "eng",
        "section": "509d",
        "book": "6",
        "page": None,
        "speaker": None,
        "source_file": "test.xml",
        "translator": None,
        "edition_year": None,
        "text": "Conceive then divided line into two unequal sections.",
    }
    base.update(overrides)
    return base


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.sqlite"


@pytest.fixture
def conversations_conn(tmp_path: Path) -> sqlite3.Connection:
    return conversations.open_db(tmp_path / "conv.sqlite")


@pytest.fixture
def translations_conn(tmp_path: Path) -> sqlite3.Connection:
    return translations.open_db(tmp_path / "trans.sqlite")


@pytest.fixture
def speaker_db(tmp_path: Path) -> sqlite3.Connection:
    """Small corpus with multiple speakers, for `--speaker` filter tests."""

    chunks = [
        make_chunk(
            chunk_id="th-1",
            work="Theaetetus",
            section="151a",
            speaker="Socrates",
            text="Socrates speaks of midwifery and inquiry into the nature of knowledge and perception at length.",
        ),
        make_chunk(
            chunk_id="th-2",
            work="Theaetetus",
            section="151b",
            speaker="Theaetetus",
            text="Theaetetus replies about knowledge as perception in the dialogue with Socrates at some length.",
        ),
        make_chunk(
            chunk_id="th-3",
            work="Theaetetus",
            section="151c",
            speaker="Socrates",
            text="Socrates pursues the perception thread in the Theaetetus with further argument and detail.",
        ),
        make_chunk(
            chunk_id="th-4",
            work="Theaetetus",
            section="151d",
            speaker=None,
            text="Narrator interlude with no speaker.",
        ),
    ]
    jsonl = tmp_path / "speakers.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    db_path = tmp_path / "speakers.sqlite"
    conn = store.open_db(db_path)
    store.insert_chunks(conn, jsonl)
    return conn


@pytest.fixture
def populated_db(tmp_path: Path, db_path: Path) -> sqlite3.Connection:
    """In-temp-dir SQLite store seeded with a small mixed corpus."""

    chunks = [
        make_chunk(
            chunk_id="rep-509d",
            section="509d",
            text="Conceive then, as we were saying, that there are these two entities, "
            "represented by a line divided into two unequal sections.",
        ),
        make_chunk(
            chunk_id="rep-510a",
            section="510a",
            text="The visible and the intelligible, divided into sections proportional to clarity.",
        ),
        make_chunk(
            chunk_id="rep-514a",
            section="514a",
            text="Imagine men in a cave looking at shadows on the wall.",
        ),
        make_chunk(
            chunk_id="ne-1097b",
            corpus="aristotle",
            author="Aristotle",
            work="Nicomachean Ethics",
            section="1097b",
            book=None,
            text="The good of any thing is found by attending to its function or ergon.",
        ),
        make_chunk(
            chunk_id="phaedo-72e",
            work="Phaedo",
            section="72e",
            book=None,
            text="Recollection: the soul recovers what it knew before birth.",
        ),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(db_path)
    store.insert_chunks(conn, jsonl)
    return conn


def make_hit(
    *,
    chunk_id: str = "rep-509d",
    score: float = 1.0,
    bm25: float = 1.0,
    cosine: float = 0.0,
    text: str = "passage text",
    section: str | None = "509d",
    work: str = "Republic",
    author: str = "Plato",
    corpus: str = "plato",
    lang: str = "eng",
    book: str | None = "6",
) -> retrieve.Hit:
    return retrieve.Hit(
        chunk_id=chunk_id,
        score=score,
        bm25=bm25,
        cosine=cosine,
        meta={
            "chunk_id": chunk_id,
            "corpus": corpus,
            "author": author,
            "work": work,
            "lang": lang,
            "section": section,
            "book": book,
            "page": None,
            "speaker": None,
            "source_file": "x.xml",
            "translator": None,
            "edition_year": None,
            "text": text,
            "ord": 0,
        },
    )


# Paths of every throwaway DB handed out by `_conv_conn` / `_trans_conn`,
# unlinked in one sweep at session end (see `_cleanup_throwaway_dbs`).
# `make_deps` is a plain helper, not a fixture, so there's no per-test
# teardown to hook without changing its API — and before this list the
# suite leaked hundreds of orphaned temp files per run.
_THROWAWAY_DB_PATHS: list[Path] = []


def _throwaway_db_path() -> Path:
    # NamedTemporaryFile must survive its close() so sqlite can open the
    # path; ruff's SIM115 (use a context manager) would delete the file
    # before we hand it to sqlite3.
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)  # noqa: SIM115
    tmp.close()
    path = Path(tmp.name)
    _THROWAWAY_DB_PATHS.append(path)
    return path


@pytest.fixture(autouse=True, scope="session")
def _cleanup_throwaway_dbs():
    yield
    for path in _THROWAWAY_DB_PATHS:
        # Sweep sqlite's sidecar files too, in case a connection was
        # left open in WAL mode when the session ended.
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(f"{path}{suffix}").unlink(missing_ok=True)


def _conv_conn() -> sqlite3.Connection:
    """Throwaway conversations DB for handler tests that don't care about
    cross-test persistence — each call returns a fresh in-temp-dir SQLite."""

    return conversations.open_db(_throwaway_db_path())


def _trans_conn() -> sqlite3.Connection:
    """Throwaway translations DB; same pattern as `_conv_conn`."""

    return translations.open_db(_throwaway_db_path())


@pytest.fixture
def deps_with_rewrite(populated_db: sqlite3.Connection) -> server.ServerDeps:
    """ServerDeps with production-like auto-rewrite enabled."""
    return make_deps(populated_db, StubBackend(), force_rewrite=True)


def make_deps(
    populated_db: sqlite3.Connection,
    backend: StubBackend,
    *,
    speaker: str | None = None,
    corpus: str | None = None,
    force_rewrite: bool = False,
    conversations_conn: sqlite3.Connection | None = None,
    translations_conn: sqlite3.Connection | None = None,
    concept_cache_conn: sqlite3.Connection | None = None,
) -> server.ServerDeps:
    """Build a `ServerDeps` for handler-level tests. Each call gets a
    fresh conversations + translations DB unless caller supplies one.

    ``force_rewrite`` defaults to False here (production default is True)
    so existing tests' StubBackend reply doesn't get smuggled into the
    retrieval query through `rewrite_query`. Tests that specifically
    exercise the auto-rewrite path can opt in by setting it True.

    ``concept_cache_conn`` defaults to None (concept expand off), matching
    ``minerva serve --no-concept-expand``. Pass a real connection when a
    test exercises the cache path.
    """

    return server.ServerDeps(
        conn=populated_db,
        conversations_conn=conversations_conn or _conv_conn(),
        translations_conn=translations_conn or _trans_conn(),
        concept_cache_conn=concept_cache_conn,
        backend=backend,
        embedder=None,
        lang="eng",
        corpus=corpus,
        speaker=speaker,
        top_k=3,
        static_dir=None,  # type: ignore[arg-type]
        force_rewrite=force_rewrite,
        corpus_lock=threading.Lock(),
        conv_lock=threading.Lock(),
        trans_lock=threading.Lock(),
    )


class StubBackend(llm.LLMBackend):
    """Captures messages and returns a fixed reply (or raises)."""

    def __init__(self, reply: str | BaseException = "stubbed reply", name: str = "stub") -> None:
        self.reply = reply
        self.name = name
        self.captured: list[tuple[list[llm.Message], float]] = []

    def complete(self, messages: list[llm.Message], *, temperature: float = 0.2) -> str:
        self.captured.append((messages, temperature))
        if isinstance(self.reply, BaseException):
            raise self.reply
        return self.reply

    def stream_complete(self, messages: list[llm.Message], *, temperature: float = 0.2):
        self.captured.append((messages, temperature))
        if isinstance(self.reply, BaseException):
            raise self.reply
        text = self.reply if isinstance(self.reply, str) else ""
        if not text:
            return iter(())
        parts = text.split(" ")
        for i, word in enumerate(parts):
            yield word if i == 0 else f" {word}"

    def last_user_block(self) -> str:
        return self.captured[-1][0][-1].content

    def last_system(self) -> str:
        return self.captured[-1][0][0].content
