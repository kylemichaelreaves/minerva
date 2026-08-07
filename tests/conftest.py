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
import traceback
from collections.abc import Iterator
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
def conversations_conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    # `yield`, not `return`, so the connection is closed rather than left
    # to `__del__` — see the `_OPEN_THROWAWAY_CONNS` note below (#246).
    conn = conversations.open_db(tmp_path / "conv.sqlite")
    yield conn
    conn.close()


@pytest.fixture
def translations_conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conn = translations.open_db(tmp_path / "trans.sqlite")
    yield conn
    conn.close()


@pytest.fixture
def speaker_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
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
    yield conn
    conn.close()


@pytest.fixture
def populated_db(tmp_path: Path, db_path: Path) -> Iterator[sqlite3.Connection]:
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
        # German, for the syntax tests. The dependency parser is
        # German-only (`syntax/parse.py:_LANG = "de"`) and `load_or_parse`
        # refuses anything else, so a syntax fixture cannot be one of the
        # English Plato chunks above.
        make_chunk(
            chunk_id="hegel-p17",
            corpus="hegel",
            author="Hegel",
            work="Phänomenologie des Geistes",
            lang="deu",
            section="¶17",
            book=None,
            text="Der Geist entwickelt sich nur in der Zeit.",
        ),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(db_path)
    store.insert_chunks(conn, jsonl)
    yield conn
    conn.close()


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

# ─────────────────────────────────────────────────────────────────────
# Connection ownership (#246)
#
# A full run used to emit 900 `ResourceWarning: unclosed database`, which
# is what kept `-W error::ResourceWarning` — a cheap, broad hygiene gate
# — switched off even after #227 fixed the `terms` CLI's share of them.
# The remaining 900 split two ways:
#
#   * 64 from six *production* CLI handlers that opened a store and never
#     closed it (`cmd_index` alone was 54). Those were real bugs of #227's
#     class and are fixed in the handlers themselves; see
#     `test_cli_conn_lifecycle.py`.
#   * the rest from ~95 places in the tests where a connection is opened
#     and nothing ever owns it — `make_deps`'s conversations/translations
#     pair, and a long tail of `store.open_db(...)` / `sqlite3.connect(
#     ":memory:")` inside test bodies.
#
# This registry owns the second group: every connection *test code* opens
# is closed at the end of the test that opened it.
#
# Deliberately NOT everything. A connection opened by production code is
# left alone, so a leak there still trips the gate — which is the whole
# reason the gate is worth having, and how the six handlers above were
# found in the first place. `_owner_is_test_code` draws that line.
_OPEN_THROWAWAY_CONNS: list[sqlite3.Connection] = []

# Frames that only ever open a connection *on behalf of* a caller, so they
# are never the owner. Attribution walks inward past these to whoever
# actually asked for the connection.
_CONN_PLUMBING = (
    "minerva/sqlite_util.py",
    "minerva/store/schema.py",
    "minerva/store/__init__.py",
    "minerva/conversations.py",
    "minerva/translations.py",
    # `terms._io._open` hands its connection to `_with_db` / to the refs
    # handlers, which close it; the owner is one frame further in.
    "minerva/cli/terms/_io.py",
)

_TESTS_DIR = str(Path(__file__).parent)


#: This module's own frames, skipped during attribution. Named rather
#: than counted (`stack[:-2]`) so the walk is correct whether it is
#: reached through `tracking_connect` or called directly.
_ATTRIBUTION_INTERNALS = frozenset({"_owner_is_test_code", "tracking_connect"})


def _owner_is_test_code() -> bool:
    """True when the innermost non-plumbing frame belongs to a test.

    Walks the stack from the inside out for the first frame that isn't
    connection-opening plumbing. For `store.open_db(p)` called from a
    test that frame is the test itself; for `cmd_index`'s open it is
    `index_cmd.py`, and the connection is left for the gate to catch.
    """

    for frame in reversed(traceback.extract_stack()):
        if frame.filename == __file__ and frame.name in _ATTRIBUTION_INTERNALS:
            continue
        if any(part in frame.filename for part in _CONN_PLUMBING):
            continue
        return frame.filename.startswith(_TESTS_DIR)
    return False


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


def _register_throwaway_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    _OPEN_THROWAWAY_CONNS.append(conn)
    return conn


def _close_throwaway_conns() -> None:
    """Close every connection handed out since the last sweep.

    Idempotent: pops as it goes, and `sqlite3.Connection.close()` on an
    already-closed connection is a no-op.
    """

    while _OPEN_THROWAWAY_CONNS:
        _OPEN_THROWAWAY_CONNS.pop().close()


@pytest.fixture(autouse=True, scope="session")
def _track_test_owned_connections():
    """Register every connection test code opens, for per-test closing.

    Patched at `sqlite3.connect` rather than at `store.open_db` because
    the leaking shapes are not all routed through the store: 42 of the
    suite's warnings came from a bare `sqlite3.connect(":memory:")`.
    One patch point covers `store.open_db`, `conversations.open_db`,
    `translations.open_db` and the bare form alike.

    `_owner_is_test_code` keeps this from swallowing production leaks —
    see the note on `_OPEN_THROWAWAY_CONNS`.
    """

    real_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):  # type: ignore[no-untyped-def]
        conn = real_connect(*args, **kwargs)
        if _owner_is_test_code():
            _OPEN_THROWAWAY_CONNS.append(conn)
        return conn

    sqlite3.connect = tracking_connect  # type: ignore[assignment]
    try:
        yield
    finally:
        sqlite3.connect = real_connect  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def _close_throwaway_conns_after_each_test(_track_test_owned_connections):
    """Close test-owned connections at the end of the test that opened them.

    Function-scoped so a connection cannot outlive its test. This is the
    whole reason `-W error::ResourceWarning` can be in `addopts` (#246).
    """

    yield
    _close_throwaway_conns()


def _conv_conn() -> sqlite3.Connection:
    """Throwaway conversations DB for handler tests that don't care about
    cross-test persistence — each call returns a fresh in-temp-dir SQLite.

    Closed at the end of the current test by
    `_close_throwaway_conns_after_each_test`.
    """

    return _register_throwaway_conn(conversations.open_db(_throwaway_db_path()))


def _trans_conn() -> sqlite3.Connection:
    """Throwaway translations DB; same pattern as `_conv_conn`."""

    return _register_throwaway_conn(translations.open_db(_throwaway_db_path()))


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
