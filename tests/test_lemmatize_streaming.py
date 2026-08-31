"""Streaming-cursor regression test for ``minerva terms lemmatize``.

Phase 4a of the 2026-05-30 ingestion-bottleneck remediation II plan:
``cmd_terms_lemmatize`` now reads candidate chunks through a streaming
cursor on a dedicated read connection instead of ``fetchall()`` on the
write connection. This test pins the load-bearing property — the
read cursor survives the commits that ``_flush`` issues every
``_COMMIT_BATCH`` chunks — without dragging in spaCy/Stanza.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index
from minerva.cli.terms import lemmatize as lemmatize_mod
from minerva.lemmatize import Token
from minerva.sqlite_util import text_hash


class _StubLemmatizer:
    """Stand-in for the real Lemmatizer that yields one synthetic
    token per chunk, in input order. Avoids the spaCy/Stanza
    dependency surface while still exercising ``batch_pipe``'s
    contract (consume the items generator, yield ``(tokens, ctx)``)."""

    seen: ClassVar[list[str]] = []

    def __init__(self, lang: str) -> None:
        self.lang = lang

    def batch_pipe(self, items, *, batch_size: int, n_process: int):
        for text, ctx in items:
            type(self).seen.append(ctx)
            yield [Token(surface=text[:5], start=0, end=5, lemma=text[:5])], ctx


def test_streaming_cursor_survives_commit_boundaries(tmp_path: Path):
    db = tmp_path / "stream.sqlite"
    jsonl = tmp_path / "seed.jsonl"

    # 10 chunks; _COMMIT_BATCH patched to 3 below forces three flushes
    # mid-stream (after chunks 3, 6, 9) so we exercise the
    # commit-while-cursor-open path the prior fetchall() form never hit.
    chunks = [
        make_chunk(
            chunk_id=f"c{i:02d}",
            lang="deu",
            text=f"chunk-{i:02d} text body for streaming test.",
        )
        for i in range(10)
    ]
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))

    cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False))

    args = argparse.Namespace(
        db=db,
        lang="deu",
        edition_id=None,
        all=False,
        dry_run=False,
        skip_aggregate=True,
        batch_size=4,
        n_process=1,
    )
    with (
        patch.object(lemmatize_mod, "_COMMIT_BATCH", 3),
        patch.object(lemmatize_mod, "Lemmatizer", _StubLemmatizer),
        patch.object(lemmatize_mod, "is_supported", lambda lang: True),
    ):
        rc = lemmatize_mod.cmd_terms_lemmatize(args)
    assert rc == 0

    conn = store.open_db(db)
    try:
        rows = conn.execute("SELECT chunk_id, lemma FROM chunk_lemmas ORDER BY chunk_id").fetchall()
    finally:
        conn.close()
    # One token per chunk, all 10 chunks reached — i.e. the cursor
    # did not exhaust early when _flush committed mid-iteration.
    assert len(rows) == 10
    assert [r[0] for r in rows] == [f"c{i:02d}" for i in range(10)]


def test_streaming_skips_already_lemmatized_chunks(tmp_path: Path):
    db = tmp_path / "incremental.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    chunks = [
        make_chunk(chunk_id="x", lang="deu", text="text-x for chunk x"),
        make_chunk(chunk_id="y", lang="deu", text="text-y for chunk y"),
    ]
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False))

    # Mark "x" as already lemmatized; the streaming cursor's NOT EXISTS
    # subquery should skip it and only feed "y" to the lemmatizer.
    # The marker is ``chunk_lemma_state``, not the presence of
    # ``chunk_lemmas`` rows — see #263. The hash must match the chunk's
    # current text or the skip does not apply.
    conn = store.open_db(db)
    conn.execute(
        "INSERT INTO chunk_lemmas "
        "(chunk_id, token_index, surface_form, surface_start, surface_end, lemma) "
        "VALUES ('x', 0, 'text-', 0, 5, 'text-')"
    )
    text_x = conn.execute("SELECT text FROM chunks WHERE chunk_id='x'").fetchone()[0]
    conn.execute(
        "INSERT INTO chunk_lemma_state (chunk_id, text_hash, token_count) VALUES ('x', ?, 1)",
        (text_hash(text_x),),
    )
    conn.commit()
    conn.close()

    args = argparse.Namespace(
        db=db,
        lang="deu",
        edition_id=None,
        all=False,
        dry_run=False,
        skip_aggregate=True,
        batch_size=4,
        n_process=1,
    )
    _StubLemmatizer.seen = []
    with (
        patch.object(lemmatize_mod, "Lemmatizer", _StubLemmatizer),
        patch.object(lemmatize_mod, "is_supported", lambda lang: True),
    ):
        rc = lemmatize_mod.cmd_terms_lemmatize(args)
    assert rc == 0

    # "x" was never handed to the lemmatizer — the assertion on the
    # resulting rows alone cannot show that, since "x" already had one.
    assert _StubLemmatizer.seen == ["y"]

    conn = store.open_db(db)
    try:
        ids = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT chunk_id FROM chunk_lemmas ORDER BY chunk_id"
            ).fetchall()
        ]
    finally:
        conn.close()
    assert ids == ["x", "y"]
