"""End-to-end test for cross_references survival across ``index --reset``.

This is the headline recovery path: LLM-verified xrefs take hours to
regenerate, and a bug anywhere in the snapshot → restore → rebind →
orphan-sweep chain silently loses them (21,751 rows were wiped on the
2026-05-29 Hegel-Preface re-ingest before the machinery existed). The
lemma/embedding halves are covered by test_index_lemma_preservation;
until now nothing exercised the xref half end-to-end.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index


def _run_index(db: Path, jsonl: Path, *, reset: bool) -> None:
    args = argparse.Namespace(db=db, input=jsonl, reset=reset)
    rc = cmd_index(args)
    assert rc == 0


def _seed_xref(conn, *, source_chunk_id: str, target_chunk_id: str | None) -> int:
    """Insert a reference_target + one cross_reference the way the refs
    builder would, returning the xref id. Uses the source chunk's live
    edition_id so the shadow address is realistic."""

    ed_id = conn.execute(
        "SELECT edition_id FROM chunks WHERE chunk_id = ?", (source_chunk_id,)
    ).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO reference_targets (canonical_author, canonical_work) "
        "VALUES ('Plato', 'Republic')"
    )
    target_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO cross_references ("
        "  source_chunk_id, target_id, target_chunk_id, reference_type, "
        "  confidence, source_method, curator_status, "
        "  source_edition_id, source_sort_key, source_form_snapshot, "
        "  source_instance_index"
        ") VALUES (?, ?, ?, 'cites', 0.9, 'rule_strong', 'approved', ?, "
        "  'S001', 'Rep. 509d', 1)",
        (source_chunk_id, target_id, target_chunk_id, ed_id),
    )
    conn.commit()
    return cur.lastrowid


def test_cross_references_survive_index_reset(tmp_path: Path):
    """Content-stable re-index with --reset: the xref row must survive
    the snapshot/restore round-trip, be rebound to the fresh edition
    id, and pass FK checks."""

    db = tmp_path / "xrefs.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(chunk_id="src", lang="grc", text="cites the Republic 509d"),
                make_chunk(chunk_id="tgt", lang="grc", text="the sun analogy passage"),
            ]
        )
    )
    _run_index(db, jsonl, reset=False)

    conn = store.open_db(db)
    _seed_xref(conn, source_chunk_id="src", target_chunk_id="tgt")
    old_edition_id = conn.execute(
        "SELECT source_edition_id FROM cross_references"
    ).fetchone()[0]
    assert old_edition_id is not None
    conn.close()

    # The destructive path under test.
    _run_index(db, jsonl, reset=True)

    conn = store.open_db(db)
    rows = conn.execute(
        "SELECT source_chunk_id, target_chunk_id, source_edition_id, "
        "       curator_status "
        "FROM cross_references"
    ).fetchall()
    assert len(rows) == 1, f"xref lost across --reset: {rows!r}"
    src, tgt, new_edition_id, status = rows[0]
    assert src == "src"
    assert tgt == "tgt"
    assert status == "approved"  # curation survives
    # Rebound to a LIVE edition id (the surrogate may or may not have
    # the same integer value; what matters is that it resolves).
    live = conn.execute(
        "SELECT edition_id FROM chunks WHERE chunk_id = 'src'"
    ).fetchone()[0]
    assert new_edition_id == live
    # reference_targets came back too (alongside the ~20 out-of-corpus
    # targets a fresh open_db seeds via migrations).
    assert conn.execute(
        "SELECT COUNT(*) FROM reference_targets "
        "WHERE canonical_author = 'Plato' AND canonical_work = 'Republic'"
    ).fetchone()[0] == 1
    bad = conn.execute("PRAGMA foreign_key_check(cross_references)").fetchall()
    assert bad == [], f"FK violations after reset: {bad}"


def test_xref_source_orphans_dropped_target_orphans_nulled(tmp_path: Path):
    """When the SOURCE chunk's text changes (new content-hashed id),
    the xref is genuinely stale → deleted. When only the TARGET chunk
    changes, the row survives with target_chunk_id NULL'd (target_id
    still anchors it)."""

    db = tmp_path / "xrefs-churn.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(chunk_id="src-stays", lang="grc", text="stable source text"),
                make_chunk(chunk_id="src-goes", lang="grc", text="source that WILL change"),
                make_chunk(chunk_id="tgt-goes", lang="grc", text="target that WILL change"),
            ]
        )
    )
    _run_index(db, jsonl, reset=False)

    conn = store.open_db(db)
    _seed_xref(conn, source_chunk_id="src-stays", target_chunk_id="tgt-goes")
    # Second xref whose source chunk will vanish. Vary the shadow key
    # so the UNIQUE constraint doesn't collide.
    ed_id = conn.execute(
        "SELECT edition_id FROM chunks WHERE chunk_id = 'src-goes'"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO cross_references ("
        "  source_chunk_id, target_id, reference_type, source_edition_id, "
        "  source_sort_key, source_form_snapshot, source_instance_index"
        ") VALUES ('src-goes', 1, 'cites', ?, 'S002', 'Rep. 510a', 1)",
        (ed_id,),
    )
    conn.commit()
    conn.close()

    # Re-ingest: src-goes and tgt-goes get new content-hashed ids.
    jsonl2 = tmp_path / "seed2.jsonl"
    jsonl2.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(chunk_id="src-stays", lang="grc", text="stable source text"),
                make_chunk(chunk_id="src-new", lang="grc", text="source that DID change"),
                make_chunk(chunk_id="tgt-new", lang="grc", text="target that DID change"),
            ]
        )
    )
    _run_index(db, jsonl2, reset=True)

    conn = store.open_db(db)
    rows = conn.execute(
        "SELECT source_chunk_id, target_chunk_id FROM cross_references"
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [("src-stays", None)], (
        f"expected src-goes dropped and tgt-goes NULL'd, got {rows!r}"
    )
    bad = conn.execute("PRAGMA foreign_key_check(cross_references)").fetchall()
    assert bad == [], f"FK violations: {bad}"


def test_from_ingest_only_scopes_incremental_index(tmp_path: Path):
    """``meta.ingest.only`` written by ``ingest --only`` must be picked
    up by ``index --incremental --from-ingest-only`` and scope the
    delete/reinsert to those corpora — previously never exercised."""

    db = tmp_path / "scope.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(chunk_id="p1", corpus="plato", author="Plato", text="one"),
                make_chunk(chunk_id="h1", corpus="hegel", author="Hegel", text="zwei"),
            ]
        )
    )
    _run_index(db, jsonl, reset=False)

    # Simulate `minerva ingest --only plato` having recorded its scope.
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('ingest.only', 'plato')"
    )
    conn.commit()
    conn.close()

    # New JSONL: plato chunk changed id (text churn), hegel unchanged.
    jsonl2 = tmp_path / "seed2.jsonl"
    jsonl2.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(chunk_id="p2", corpus="plato", author="Plato", text="uno"),
                make_chunk(chunk_id="h1", corpus="hegel", author="Hegel", text="zwei"),
            ]
        )
    )
    args = argparse.Namespace(
        db=db,
        input=jsonl2,
        reset=False,
        incremental=True,
        from_ingest_only=True,
        corpora="",
    )
    rc = cmd_index(args)
    assert rc == 0

    conn = store.open_db(db)
    ids = sorted(
        r[0] for r in conn.execute("SELECT chunk_id FROM chunks").fetchall()
    )
    assert ids == ["h1", "p2"], f"incremental scope wrong: {ids!r}"
