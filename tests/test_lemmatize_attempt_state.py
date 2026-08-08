"""#263 — ``terms lemmatize`` records attempts, not just output.

``chunk_lemmas`` was doing double duty as the output table and the
"already processed" marker. A chunk that yields no valid lemma writes no
row, so nothing recorded that it was ever tried: 419 eng / 299 fra / 126
deu / 15 grc chunks were re-tokenized on every incremental pass, forever,
while the completion line counted them as done.

``chunk_lemma_state`` is the attempt marker. It follows the
``chunk_syntax_state`` precedent (migration 0024) rather than
``refs_scan_state``, whose missing foreign key is the subject of #264.
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


class _CountingLemmatizer:
    """Yields one token per chunk, except for chunks whose text starts
    with ``EMPTY`` — those come back with no tokens at all, which is the
    zero-lemma population #263 is about. Records every chunk it was
    handed so a test can assert the *second* pass was handed nothing."""

    seen: ClassVar[list[str]] = []

    def __init__(self, lang: str) -> None:
        self.lang = lang

    def batch_pipe(self, items, *, batch_size, n_process):
        for text, ctx in items:
            type(self).seen.append(ctx)
            if text.startswith("EMPTY"):
                yield [], ctx
            else:
                yield [Token(surface=text[:5], start=0, end=5, lemma=text[:5])], ctx


def _args(db: Path, **over) -> argparse.Namespace:
    base = {
        "db": db,
        "lang": "deu",
        "edition_id": None,
        "all": False,
        "dry_run": False,
        "skip_aggregate": True,
        "batch_size": 4,
        "n_process": 1,
    }
    base.update(over)
    return argparse.Namespace(**base)


def _seed(tmp_path: Path, texts: dict[str, str]) -> Path:
    db = tmp_path / "lemma_state.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    chunks = [
        make_chunk(chunk_id=cid, lang="deu", text=text) for cid, text in texts.items()
    ]
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False))
    return db


def _run(db: Path, **over) -> int:
    with patch.object(lemmatize_mod, "Lemmatizer", _CountingLemmatizer), \
         patch.object(lemmatize_mod, "is_supported", lambda lang: True):
        return lemmatize_mod.cmd_terms_lemmatize(_args(db, **over))


def test_zero_lemma_chunk_is_not_reprocessed_on_the_next_pass(tmp_path, capsys):
    db = _seed(
        tmp_path,
        {
            "productive": "gutes Deutsch mit Lemmata darin",
            "barren": "EMPTY nothing lemmatizable in here at all",
        },
    )

    _CountingLemmatizer.seen = []
    assert _run(db) == 0
    assert sorted(_CountingLemmatizer.seen) == ["barren", "productive"]

    # Second pass: both chunks were attempted, so neither is a candidate
    # — including the one that produced no rows in chunk_lemmas.
    _CountingLemmatizer.seen = []
    assert _run(db) == 0
    assert _CountingLemmatizer.seen == []
    assert "0 chunks to process" in capsys.readouterr().out


def test_attempt_state_records_the_token_count_it_produced(tmp_path):
    db = _seed(
        tmp_path,
        {
            "productive": "gutes Deutsch mit Lemmata darin",
            "barren": "EMPTY nothing lemmatizable in here at all",
        },
    )
    assert _run(db) == 0

    conn = store.open_db(db)
    try:
        rows = dict(
            conn.execute(
                "SELECT chunk_id, token_count FROM chunk_lemma_state "
                "ORDER BY chunk_id"
            ).fetchall()
        )
        hashes = dict(
            conn.execute("SELECT chunk_id, text_hash FROM chunk_lemma_state").fetchall()
        )
        texts = dict(conn.execute("SELECT chunk_id, text FROM chunks").fetchall())
    finally:
        conn.close()

    # Attempted-and-empty is now distinguishable from never-reached,
    # which is the state the German Plato residue was stuck in.
    assert rows == {"barren": 0, "productive": 1}
    assert hashes["barren"] == text_hash(texts["barren"])


def test_completion_line_separates_productive_from_attempted(tmp_path, capsys):
    db = _seed(
        tmp_path,
        {
            "a": "gutes Deutsch mit Lemmata darin",
            "b": "EMPTY nothing lemmatizable here",
            "c": "EMPTY nor anything lemmatizable here",
        },
    )
    assert _run(db) == 0
    out = capsys.readouterr().out
    # "done · 3 chunks" alone read as three chunks lemmatized; it meant
    # three chunks tried.
    assert "done · 3 chunks (1 productive)" in out


def test_a_chunk_whose_text_changed_is_reprocessed(tmp_path):
    """``chunk_id`` hashes only ``text[:120]``, so a chunk edited past
    that point keeps its id and would inherit its stale attempt marker.
    ``text_hash`` is what closes that: it is compared against the
    chunk's current text, not its id."""

    db = _seed(tmp_path, {"drifter": "A" * 130 + " erste Fassung"})
    _CountingLemmatizer.seen = []
    assert _run(db) == 0
    assert _CountingLemmatizer.seen == ["drifter"]

    conn = store.open_db(db)
    try:
        conn.execute(
            "UPDATE chunks SET text = ? WHERE chunk_id = 'drifter'",
            ("A" * 130 + " zweite Fassung",),
        )
        conn.commit()
    finally:
        conn.close()

    _CountingLemmatizer.seen = []
    assert _run(db) == 0
    assert _CountingLemmatizer.seen == ["drifter"]


def test_all_flag_reprocesses_every_chunk_regardless_of_state(tmp_path):
    db = _seed(tmp_path, {"a": "gutes Deutsch", "b": "EMPTY nothing here"})
    assert _run(db) == 0

    _CountingLemmatizer.seen = []
    assert _run(db, all=True) == 0
    assert sorted(_CountingLemmatizer.seen) == ["a", "b"]


def test_flush_writes_attempt_markers_for_a_wholly_barren_batch(tmp_path):
    """A commit batch in which every chunk was barren has markers and no
    lemma rows. That combination never arises in the tests above (each
    has at least one productive chunk in the same flush) but it is the
    normal case for an OCR-damaged corpus, and it is the whole point of
    the table."""

    db = _seed(tmp_path, {"a": "gutes Deutsch"})
    conn = store.open_db(db)
    try:
        lemmatize_mod._flush(conn, [], [("a", "hash-a", 0)])
        rows = [
            tuple(r)
            for r in conn.execute(
                "SELECT chunk_id, token_count FROM chunk_lemma_state"
            )
        ]
        lemmas = conn.execute("SELECT COUNT(*) FROM chunk_lemmas").fetchone()[0]
    finally:
        conn.close()
    assert rows == [("a", 0)]
    assert lemmas == 0


def test_flush_with_nothing_to_write_is_a_no_op(tmp_path):
    """The tail ``_flush`` after the loop runs on every pass, usually
    with both lists already emptied by the last commit boundary."""

    db = _seed(tmp_path, {"a": "gutes Deutsch"})
    conn = store.open_db(db)
    try:
        lemmatize_mod._flush(conn, [], [])
        assert conn.execute("SELECT COUNT(*) FROM chunk_lemma_state").fetchone()[0] == 0
    finally:
        conn.close()
