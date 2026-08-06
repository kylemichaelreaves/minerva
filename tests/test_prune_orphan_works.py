"""The orphan-works GC in ``insert_chunks`` (``_prune_orphan_works``).

A chunk delete + re-insert under a different work title (the Plato
Latinized-Greek canonicalization) re-homes chunks but strands the old
works/editions/translations. The sweep drops rows with no chunks so the
works count stays honest, while never touching a work that still has any.
"""

from __future__ import annotations

from pathlib import Path

from minerva import store
from minerva.store.chunks import _prune_orphan_works, _resolve_work_refs


def _insert_chunk(conn, chunk_id: str, *, edition_id=None, translation_id=None) -> None:
    conn.execute(
        "INSERT INTO chunks (chunk_id, edition_id, translation_id, lang, "
        "source_file, text, ord, text_norm) VALUES (?,?,?,?,?,?,?,?)",
        (chunk_id, edition_id, translation_id, "grc", "x.xml", "text", 0, "text"),
    )


def test_prune_removes_empty_works_but_keeps_populated(tmp_path: Path):
    conn = store.open_db(tmp_path / "prune.sqlite")

    # Work A: a Greek edition WITH a chunk, plus an English translation with
    # NO chunk (a stranded translation on an otherwise-live work).
    ed_a, _ = _resolve_work_refs(
        conn,
        corpus="plato",
        author="Plato",
        work="Politeia",
        lang="grc",
        translator="Burnet",
        edition_year="1903",
    )
    _, tr_a = _resolve_work_refs(
        conn,
        corpus="plato",
        author="Plato",
        work="Politeia",
        lang="eng",
        translator="Shorey",
        edition_year="1969",
    )
    _insert_chunk(conn, "a1", edition_id=ed_a)

    # Work B: a Greek edition with NO chunk at all — a fully orphaned work
    # (the pre-canonicalization shell).
    ed_b, _ = _resolve_work_refs(
        conn,
        corpus="plato",
        author="Plato",
        work="Republic",
        lang="grc",
        translator="Burnet",
        edition_year="1903",
    )
    conn.commit()

    def work_id(title: str):
        row = conn.execute(
            "SELECT id FROM works WHERE author='Plato' AND title=?", (title,)
        ).fetchone()
        return row[0] if row else None

    wid_a, wid_b = work_id("Politeia"), work_id("Republic")
    assert wid_a is not None and wid_b is not None

    _prune_orphan_works(conn)
    conn.commit()

    # Orphan work B and its chunk-less edition are gone.
    assert work_id("Republic") is None
    assert conn.execute("SELECT 1 FROM editions WHERE id=?", (ed_b,)).fetchone() is None

    # Work A survives (it has a chunk), its edition survives, but its
    # chunk-less translation is pruned.
    assert work_id("Politeia") == wid_a
    assert conn.execute("SELECT 1 FROM editions WHERE id=?", (ed_a,)).fetchone() is not None
    assert conn.execute("SELECT 1 FROM translations WHERE id=?", (tr_a,)).fetchone() is None


def test_prune_is_idempotent(tmp_path: Path):
    conn = store.open_db(tmp_path / "prune2.sqlite")
    ed, _ = _resolve_work_refs(
        conn,
        corpus="plato",
        author="Plato",
        work="Kriton",
        lang="grc",
        translator="Burnet",
        edition_year="1903",
    )
    _insert_chunk(conn, "k1", edition_id=ed)
    conn.commit()
    _prune_orphan_works(conn)
    _prune_orphan_works(conn)  # second pass is a no-op
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 1
