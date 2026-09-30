"""#674 — editorial apparatus is not lemmatized, so the concordance never counts it.

Chunks ingest has already typed as apparatus (``note``, ``editorial``,
``cast``) are the translator's or editor's words, not the author's —
``retrieve.format_locator`` already attributes them away from the author for
exactly that reason. The lemmatizer did not know: 348,868 ``chunk_lemmas``
rows came from them, and 4,188 of the 6,234 English ``cf`` in the
leaderboard, all counted under the author of the work.

Decided on #648: apparatus is not lemmatized at all. So a pass must neither
hand such a chunk to the model nor leave behind rows an earlier pass wrote —
lemmatize is incremental, and a chunk re-typed in place (the Kant typing
pass keeps every ``chunk_id``) keeps its old rows unless something removes
them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from conftest import make_chunk

from minerva import store
from minerva.block_types import APPARATUS_TYPES
from minerva.cli.index_cmd import cmd_index
from minerva.cli.terms import lemmatize as lemmatize_mod
from minerva.lemmatize import Token


class _RecordingLemmatizer:
    """One token per chunk, lemma = the chunk's first word, with a ``pos``
    because the aggregate drops rows without one. Records every
    chunk it was handed."""

    backend = "stub"
    model = "stub"
    seen: ClassVar[list[str]] = []

    def __init__(self, lang: str) -> None:
        self.lang = lang

    def batch_pipe(self, items, *, batch_size, n_process):
        for text, ctx in items:
            type(self).seen.append(ctx)
            word = text.split()[0]
            yield [Token(surface=word, start=0, end=len(word), lemma=word, pos="X")], ctx


def _args(db: Path, **over) -> argparse.Namespace:
    base = {
        "db": db,
        "lang": "eng",
        "edition_id": None,
        "all": False,
        "dry_run": False,
        "skip_aggregate": True,
        "batch_size": 4,
        "n_process": 1,
    }
    base.update(over)
    return argparse.Namespace(**base)


def _seed(tmp_path: Path, chunks: list[dict]) -> Path:
    db = tmp_path / "apparatus.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False))
    return db


def _run(db: Path, **over) -> int:
    with (
        patch.object(lemmatize_mod, "Lemmatizer", _RecordingLemmatizer),
        patch.object(lemmatize_mod, "is_supported", lambda lang: True),
    ):
        return lemmatize_mod.cmd_terms_lemmatize(_args(db, **over))


def _query(db: Path, sql: str, params=()) -> list:
    conn = store.open_db(db)
    try:
        return [tuple(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _set_block_type(db: Path, chunk_id: str, block_type: str | None) -> None:
    conn = store.open_db(db)
    try:
        conn.execute("UPDATE chunks SET block_type = ? WHERE chunk_id = ?", (block_type, chunk_id))
        conn.commit()
    finally:
        conn.close()


def _body_and_apparatus() -> list[dict]:
    chunks = [
        make_chunk(chunk_id="body", ord=0, text="virtue is knowledge"),
        # The author's own Anmerkung: typed, but not apparatus, so counted.
        make_chunk(chunk_id="remark", ord=1, block_type="remark", text="remark by the author"),
    ]
    chunks += [
        make_chunk(chunk_id=bt, ord=i + 2, block_type=bt, text=f"cf {bt} by the editor")
        for i, bt in enumerate(APPARATUS_TYPES)
    ]
    return chunks


def test_apparatus_types_are_the_set_retrieval_attributes_away_from_the_author():
    from minerva import retrieve

    # `spurious`: DK's doubtful and forged fragments, attributed to the
    # author by a source but not his in the editor's judgement (#683).
    assert set(APPARATUS_TYPES) == {"note", "editorial", "cast", "spurious"}
    assert retrieve._APPARATUS_TYPES is APPARATUS_TYPES


def test_apparatus_chunks_are_never_handed_to_the_lemmatizer(tmp_path, capsys):
    db = _seed(tmp_path, _body_and_apparatus())

    _RecordingLemmatizer.seen = []
    assert _run(db) == 0

    assert sorted(_RecordingLemmatizer.seen) == ["body", "remark"]
    assert "2 chunks to process" in capsys.readouterr().out
    assert _query(db, "SELECT DISTINCT chunk_id FROM chunk_lemmas ORDER BY 1") == [
        ("body",),
        ("remark",),
    ]


def test_rows_written_before_a_chunk_became_apparatus_are_purged(tmp_path, capsys):
    db = _seed(
        tmp_path,
        [
            make_chunk(chunk_id="body", ord=0, text="virtue is knowledge"),
            make_chunk(chunk_id="retyped", ord=1, text="cf the editor's note"),
            make_chunk(chunk_id="other_lang", ord=2, lang="deu", text="cf eine Anmerkung"),
        ],
    )
    assert _run(db) == 0
    assert _run(db, lang="deu") == 0
    # Re-typed in place, chunk_id and text unchanged — the incremental skip
    # would never revisit it.
    _set_block_type(db, "retyped", "note")
    _set_block_type(db, "other_lang", "note")
    capsys.readouterr()

    _RecordingLemmatizer.seen = []
    assert _run(db) == 0

    assert _RecordingLemmatizer.seen == []
    out = capsys.readouterr().out
    assert "purged 1 rows from 1 apparatus chunks" in out
    assert _query(db, "SELECT DISTINCT chunk_id FROM chunk_lemmas ORDER BY 1") == [
        ("body",),
        ("other_lang",),  # a pass over eng leaves deu's rows to a pass over deu
    ]
    assert _query(db, "SELECT chunk_id FROM chunk_lemma_state ORDER BY 1") == [
        ("body",),
        ("other_lang",),
    ]


def test_a_chunk_retyped_back_to_body_text_is_lemmatized_again(tmp_path):
    db = _seed(tmp_path, [make_chunk(chunk_id="c", ord=0, text="virtue is knowledge")])
    assert _run(db) == 0
    _set_block_type(db, "c", "editorial")
    assert _run(db) == 0
    _set_block_type(db, "c", None)

    _RecordingLemmatizer.seen = []
    assert _run(db) == 0

    # The purge removed the attempt marker along with the rows, so the
    # text-hash skip does not hide the chunk once it is body text again.
    assert _RecordingLemmatizer.seen == ["c"]
    assert _query(db, "SELECT lemma FROM chunk_lemmas WHERE chunk_id = 'c'") == [("virtue",)]


def test_a_purge_with_nothing_left_to_lemmatize_still_rebuilds_the_leaderboard(tmp_path):
    db = _seed(
        tmp_path,
        [
            make_chunk(chunk_id="body", ord=0, text="virtue is knowledge"),
            make_chunk(chunk_id="retyped", ord=1, text="cf the editor's note"),
        ],
    )
    assert _run(db, skip_aggregate=False) == 0
    count_cf = "SELECT count FROM lemma_counts WHERE lemma = 'cf' AND scope_kind = 'corpus'"
    assert _query(db, count_cf) == [(1,)]
    _set_block_type(db, "retyped", "note")

    assert _run(db, skip_aggregate=False) == 0

    assert _query(db, count_cf) == []
    assert _query(db, "SELECT lemma FROM lemma_counts WHERE scope_kind = 'corpus'") == [("virtue",)]


def test_a_dry_run_reports_but_does_not_purge(tmp_path):
    db = _seed(tmp_path, [make_chunk(chunk_id="c", ord=0, text="cf the editor's note")])
    assert _run(db) == 0
    _set_block_type(db, "c", "note")

    assert _run(db, dry_run=True) == 0

    assert _query(db, "SELECT COUNT(*) FROM chunk_lemmas") == [(1,)]
    assert _query(db, "SELECT COUNT(*) FROM chunk_lemma_state") == [(1,)]


def test_a_word_click_inside_apparatus_says_why_there_is_no_lemma(tmp_path):
    """The Reader renders apparatus through the same clickable word runs as
    body text, and shows this error verbatim in the rail. Telling the reader
    to run lemmatize would be wrong: lemmatize now skips the chunk."""
    import pytest

    from minerva.errors import NotFoundError
    from minerva.reader.queries import word_lookup

    db = _seed(
        tmp_path,
        [
            make_chunk(chunk_id="note", ord=0, block_type="note", text="cf the editor"),
            make_chunk(chunk_id="body", ord=1, text="virtue is knowledge"),
        ],
    )
    conn = store.open_db(db)
    try:
        with pytest.raises(NotFoundError, match="editorial note") as note_exc:
            word_lookup(conn, {"chunk_id": "note", "offset": "0"})
        assert "terms lemmatize" not in str(note_exc.value)
        # Body text with no rows yet keeps the actionable hint.
        with pytest.raises(NotFoundError, match="terms lemmatize"):
            word_lookup(conn, {"chunk_id": "body", "offset": "0"})
        with pytest.raises(NotFoundError, match="terms lemmatize"):
            word_lookup(conn, {"chunk_id": "no-such-chunk", "offset": "0"})
    finally:
        conn.close()


def test_a_word_click_inside_a_spurious_fragment_says_why_there_is_no_lemma(tmp_path):
    import pytest

    from minerva.errors import NotFoundError
    from minerva.reader.queries import word_lookup

    db = _seed(tmp_path, [make_chunk(chunk_id="s", ord=0, block_type="spurious", text="cf x")])
    conn = store.open_db(db)
    try:
        with pytest.raises(NotFoundError, match="doubtful or spurious fragment") as exc:
            word_lookup(conn, {"chunk_id": "s", "offset": "0"})
        # Neither the translator's nor the editor's words.
        assert "not the author's own text" in str(exc.value)
        assert "terms lemmatize" not in str(exc.value)
    finally:
        conn.close()


def test_an_edition_scoped_pass_purges_only_its_own_edition(tmp_path):
    db = _seed(
        tmp_path,
        [
            # Greek, because the English Plato is a translation and has no
            # edition_id to scope by.
            make_chunk(chunk_id="rep", ord=0, lang="grc", work="Republic", text="λόγος ἐστί"),
            make_chunk(chunk_id="laws", ord=1, lang="grc", work="Laws", text="νόμος ἐστί"),
        ],
    )
    assert _run(db, lang="grc") == 0
    _set_block_type(db, "rep", "note")
    _set_block_type(db, "laws", "note")
    [(republic,)] = _query(db, "SELECT edition_id FROM chunks_full WHERE chunk_id = 'rep'")
    assert republic is not None

    assert _run(db, lang="grc", edition_id=republic) == 0

    assert _query(db, "SELECT DISTINCT chunk_id FROM chunk_lemmas") == [("laws",)]
