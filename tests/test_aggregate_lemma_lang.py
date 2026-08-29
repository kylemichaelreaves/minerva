"""aggregate.build groups by chunk_lemmas.lang when set (#430).

A cross-script row (an embedded Latin phrase inside a `grc` chunk, tagged
`lang='lat'` by the lemmatize pass) must land in `lemma_counts` under its
OWN language, not the chunk's — otherwise the fix in the lemmatizer never
reaches the concordance the issue was filed about.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index
from minerva.concordance import aggregate


def _seed_lemma(
    conn: sqlite3.Connection,
    *,
    chunk_id: str,
    token_index: int,
    surface: str,
    lemma: str,
    lang: str | None,
) -> None:
    conn.execute(
        "INSERT INTO chunk_lemmas "
        "(chunk_id, token_index, surface_form, surface_start, surface_end, "
        " lemma, lemma_fold, pos, feats, lang) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'NOUN', NULL, ?)",
        (
            chunk_id, token_index, surface,
            token_index * 10, token_index * 10 + len(surface),
            lemma, lemma.lower(), lang,
        ),
    )


def _build_index(tmp_path: Path, chunks: list[dict]) -> Path:
    db = tmp_path / "aggregate.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False))
    return db


def _corpus_lang_lemma(conn: sqlite3.Connection, lang: str, lemma: str):
    row = conn.execute(
        "SELECT count FROM lemma_counts "
        "WHERE lang = ? AND scope_kind = 'corpus' AND scope_value IS NULL AND lemma = ?",
        (lang, lemma),
    ).fetchone()
    return tuple(row) if row is not None else None


def test_a_null_lang_row_aggregates_under_its_chunks_language(tmp_path: Path):
    db = _build_index(tmp_path, [make_chunk(chunk_id="g1", lang="grc", text="λόγος")])
    conn = store.open_db(db)
    try:
        _seed_lemma(conn, chunk_id="g1", token_index=0, surface="λόγος", lemma="λόγος", lang=None)
        conn.commit()
        aggregate.build(conn)
        assert _corpus_lang_lemma(conn, "grc", "λόγος") == (1,)
        assert _corpus_lang_lemma(conn, "lat", "λόγος") is None
    finally:
        conn.close()


def test_an_explicit_lang_row_aggregates_under_that_language_not_the_chunks(tmp_path: Path):
    """The whole point of #430's fix: a Latin phrase found inside a
    `grc` chunk must count as `lat` vocabulary in the leaderboard, not
    as Greek."""

    db = _build_index(tmp_path, [make_chunk(chunk_id="g1", lang="grc", text="λόγος PLUT")])
    conn = store.open_db(db)
    try:
        _seed_lemma(conn, chunk_id="g1", token_index=0, surface="λόγος", lemma="λόγος", lang=None)
        _seed_lemma(conn, chunk_id="g1", token_index=1, surface="PLUT", lemma="plut", lang="lat")
        conn.commit()
        aggregate.build(conn)
        assert _corpus_lang_lemma(conn, "grc", "λόγος") == (1,)
        assert _corpus_lang_lemma(conn, "grc", "plut") is None
        assert _corpus_lang_lemma(conn, "lat", "plut") == (1,)
    finally:
        conn.close()


def test_author_and_work_scopes_also_follow_the_row_lang(tmp_path: Path):
    db = _build_index(
        tmp_path,
        [make_chunk(chunk_id="g1", lang="grc", text="λόγος PLUT", author="Aristotle", work="Economics")],
    )
    conn = store.open_db(db)
    try:
        _seed_lemma(conn, chunk_id="g1", token_index=0, surface="PLUT", lemma="plut", lang="lat")
        conn.commit()
        aggregate.build(conn)
        row = conn.execute(
            "SELECT count FROM lemma_counts "
            "WHERE lang='lat' AND scope_kind='author' AND scope_value='Aristotle' AND lemma='plut'"
        ).fetchone()
        assert tuple(row) == (1,)
        row = conn.execute(
            "SELECT count FROM lemma_counts "
            "WHERE lang='lat' AND scope_kind='work' AND scope_value='Economics' AND lemma='plut'"
        ).fetchone()
        assert tuple(row) == (1,)
    finally:
        conn.close()
