"""Tests for ``minerva index --incremental`` (Phase 3 of the 2026-05-30
ingestion-bottleneck remediation II plan).

The incremental path replaces the destructive ``DELETE FROM
translations/editions/works/chunks + FTS rebuild`` sequence with a
corpus-scoped delete that leaves out-of-scope rows untouched. The
relevant invariants:

* Out-of-scope chunks survive (their text + edition_id + lemmas +
  embeddings + xrefs all stay).
* In-scope chunks are deleted then re-inserted from JSONL.
* Cross-references whose source_chunk_id survives the re-insert
  (content-stable chunks) keep their edition rebind.
* FTS index stays consistent via the schema triggers — no manual
  rebuild needed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index


def _index(
    db: Path,
    jsonl: Path,
    *,
    reset: bool = False,
    incremental: bool = False,
    corpora: str = "",
    from_ingest_only: bool = False,
) -> int:
    args = argparse.Namespace(
        db=db,
        input=jsonl,
        reset=reset,
        incremental=incremental,
        corpora=corpora,
        from_ingest_only=from_ingest_only,
    )
    return cmd_index(args)


def _write_jsonl(path: Path, *chunks: dict) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for ch in chunks:
            fh.write(json.dumps(ch, ensure_ascii=False) + "\n")


def test_incremental_preserves_out_of_scope_corpus(tmp_path: Path):
    """Re-indexing one corpus must leave every other corpus's chunks +
    lemmas + embeddings + xrefs in place.

    Seed two corpora (plato + hegel), do a full --reset to load both,
    then run --incremental --corpora plato with a single replacement
    chunk: hegel should keep its original chunk count unchanged.
    """
    db = tmp_path / "incr.sqlite"
    jsonl = tmp_path / "chunks.jsonl"

    plato_chunk = make_chunk(
        chunk_id="plato1",
        corpus="plato",
        author="Plato",
        work="Republic",
        text="The first Plato passage.",
    )
    hegel_chunk = make_chunk(
        chunk_id="hegel1",
        corpus="hegel",
        author="Hegel",
        work="Phenomenology of Spirit",
        lang="eng",
        section="¶1",
        text="The first Hegel passage.",
    )
    _write_jsonl(jsonl, plato_chunk, hegel_chunk)
    assert _index(db, jsonl, reset=True) == 0

    conn = store.open_db(db)
    assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 2

    # Replace plato chunk with a different one; hegel chunk stays in
    # the JSONL but the incremental run shouldn't touch it.
    new_plato = make_chunk(
        chunk_id="plato2",
        corpus="plato",
        author="Plato",
        work="Republic",
        text="A different Plato passage.",
    )
    _write_jsonl(jsonl, new_plato, hegel_chunk)
    assert _index(db, jsonl, incremental=True, corpora="plato") == 0

    chunks = dict(conn.execute("SELECT chunk_id, text FROM chunks ORDER BY chunk_id"))
    # Old plato chunk replaced; new plato chunk loaded.
    assert "plato1" not in chunks
    assert chunks.get("plato2") == "A different Plato passage."
    # Hegel chunk unchanged — proves out-of-scope preservation.
    assert chunks.get("hegel1") == "The first Hegel passage."


def test_incremental_without_scope_returns_error(tmp_path: Path):
    """``--incremental`` with neither --corpora nor --from-ingest-only
    is a usage error — refuse to silently no-op."""
    db = tmp_path / "noscope.sqlite"
    jsonl = tmp_path / "chunks.jsonl"
    _write_jsonl(jsonl, make_chunk(chunk_id="c1", corpus="plato"))
    _index(db, jsonl, reset=True)

    rc = _index(db, jsonl, incremental=True)  # no corpora, no --from-ingest-only
    assert rc == 2


def test_incremental_rejects_reset(tmp_path: Path):
    """``--incremental`` is incompatible with --reset; the operator
    presumably meant one or the other, not both. Refuse rather than
    silently picking one."""
    db = tmp_path / "both.sqlite"
    jsonl = tmp_path / "chunks.jsonl"
    _write_jsonl(jsonl, make_chunk(chunk_id="c1", corpus="plato"))
    _index(db, jsonl, reset=True)

    rc = _index(db, jsonl, incremental=True, corpora="plato", reset=True)
    assert rc == 2


def test_incremental_fts_updates_via_triggers(tmp_path: Path):
    """The FTS5 schema has automatic ``chunks → chunks_fts`` triggers
    (schema.py L49–59). Incremental mode skips the manual rebuild and
    relies on the triggers to keep FTS in sync. Verify that a new
    chunk text is findable through FTS after an incremental run."""
    db = tmp_path / "fts.sqlite"
    jsonl = tmp_path / "chunks.jsonl"
    _write_jsonl(
        jsonl,
        make_chunk(
            chunk_id="p1",
            corpus="plato",
            text="The original Republic passage.",
        ),
    )
    _index(db, jsonl, reset=True)

    new_text = "Reincarnation hippopotamus."
    _write_jsonl(
        jsonl,
        make_chunk(
            chunk_id="p2",
            corpus="plato",
            text=new_text,
        ),
    )
    _index(db, jsonl, incremental=True, corpora="plato")

    conn = store.open_db(db)
    # FTS5 should find the unique distinguishing word from the new
    # text. If the trigger fired during the incremental delete +
    # re-insert, this query returns 1 row.
    rows = conn.execute(
        "SELECT chunks.chunk_id FROM chunks_fts "
        "JOIN chunks ON chunks.rowid = chunks_fts.rowid "
        "WHERE chunks_fts MATCH 'hippopotamus'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "p2"


def test_incremental_multi_corpus_scope(tmp_path: Path):
    """``--corpora a,b`` should refresh both corpora and leave any
    third one alone."""
    db = tmp_path / "multi.sqlite"
    jsonl = tmp_path / "chunks.jsonl"

    chunks = [
        make_chunk(chunk_id="plato1", corpus="plato", text="Plato old"),
        make_chunk(
            chunk_id="hegel1",
            corpus="hegel",
            author="Hegel",
            work="W",
            lang="eng",
            section="¶1",
            text="Hegel old",
        ),
        make_chunk(
            chunk_id="kant1",
            corpus="kant",
            author="Kant",
            work="K",
            lang="eng",
            section="¶1",
            text="Kant unchanged",
        ),
    ]
    _write_jsonl(jsonl, *chunks)
    _index(db, jsonl, reset=True)

    # Refresh plato + hegel; kant must stay.
    chunks[0] = make_chunk(chunk_id="plato2", corpus="plato", text="Plato new")
    chunks[1] = make_chunk(
        chunk_id="hegel2",
        corpus="hegel",
        author="Hegel",
        work="W",
        lang="eng",
        section="¶1",
        text="Hegel new",
    )
    _write_jsonl(jsonl, *chunks)
    _index(db, jsonl, incremental=True, corpora="plato,hegel")

    conn = store.open_db(db)
    ids = {cid for (cid,) in conn.execute("SELECT chunk_id FROM chunks").fetchall()}
    assert ids == {"plato2", "hegel2", "kant1"}


def test_incremental_scope_matches_slug_not_just_author_label(tmp_path: Path):
    """Regression: the incremental DELETE used to key on
    ``chunks_full.corpus`` — which is ``LOWER(works.author)`` — while
    the insert filter keys on the JSONL corpus *slug*. For corpora
    where they differ (hebrew_mt → "Hebrew Bible", new_testament,
    kjv, luther_1545/1912, marcus_aurelius, presocratic), the delete
    matched nothing and every changed chunk was re-inserted BESIDE
    its stale predecessor (2026-07-01: 3,373 duplicated MT verses)."""
    db = tmp_path / "slug.sqlite"
    jsonl = tmp_path / "chunks.jsonl"

    old = make_chunk(
        chunk_id="mt1",
        corpus="hebrew_mt",
        author="Hebrew Bible",
        work="Genesis",
        lang="heb",
        section="Gen 1:12",
        text="Old polluted verse text.",
    )
    _write_jsonl(jsonl, old)
    assert _index(db, jsonl, reset=True) == 0

    new = make_chunk(
        chunk_id="mt2",
        corpus="hebrew_mt",
        author="Hebrew Bible",
        work="Genesis",
        lang="heb",
        section="Gen 1:12",
        text="Clean verse text.",
    )
    _write_jsonl(jsonl, new)
    assert _index(db, jsonl, incremental=True, corpora="hebrew_mt") == 0

    conn = store.open_db(db)
    ids = {cid for (cid,) in conn.execute("SELECT chunk_id FROM chunks").fetchall()}
    # The stale chunk must be REPLACED, not duplicated.
    assert ids == {"mt2"}


def test_incremental_scope_fans_out_to_all_author_labels(tmp_path: Path):
    """One corpus slug can carry many author labels (presocratic →
    each named philosopher). All of them are in scope for the delete."""
    db = tmp_path / "fanout.sqlite"
    jsonl = tmp_path / "chunks.jsonl"

    heraclitus = make_chunk(
        chunk_id="her1",
        corpus="presocratic",
        author="Heraclitus",
        work="Fragments",
        lang="grc",
        section="DK B1",
        text="Old Heraclitus fragment.",
    )
    empedocles = make_chunk(
        chunk_id="emp1",
        corpus="presocratic",
        author="Empedocles",
        work="Fragments",
        lang="grc",
        section="DK B17",
        text="Old Empedocles fragment.",
    )
    _write_jsonl(jsonl, heraclitus, empedocles)
    assert _index(db, jsonl, reset=True) == 0

    heraclitus_new = make_chunk(
        chunk_id="her2",
        corpus="presocratic",
        author="Heraclitus",
        work="Fragments",
        lang="grc",
        section="DK B1",
        text="New Heraclitus fragment.",
    )
    empedocles_new = make_chunk(
        chunk_id="emp2",
        corpus="presocratic",
        author="Empedocles",
        work="Fragments",
        lang="grc",
        section="DK B17",
        text="New Empedocles fragment.",
    )
    _write_jsonl(jsonl, heraclitus_new, empedocles_new)
    assert _index(db, jsonl, incremental=True, corpora="presocratic") == 0

    conn = store.open_db(db)
    ids = {cid for (cid,) in conn.execute("SELECT chunk_id FROM chunks").fetchall()}
    assert ids == {"her2", "emp2"}
