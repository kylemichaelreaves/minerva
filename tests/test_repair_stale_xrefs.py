"""#407: 336 `cross_references` rows no longer point at the text they
record. `find_stale_xrefs` picks out the ones worth repairing — every
out-of-range span, and every in-range mismatch that isn't #414's
accepted wide-snapshot population (Aquinas/Augustine scripture quotes
where the snapshot deliberately records the citation formula plus the
quote, and only the quote is spanned).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import repair_stale_xrefs as rx  # noqa: E402

_TEXT = "alpha beta gamma"


def _seed(tmp_path: Path, chunks: list[dict]) -> Path:
    db = tmp_path / "repair.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False))
    return db


def _seed_xref(
    conn,
    *,
    source_chunk_id: str,
    span_start: int | None,
    span_end: int | None,
    source_form_snapshot: str | None,
) -> int:
    cur = conn.execute(
        "INSERT INTO reference_targets (canonical_author, canonical_work) "
        "VALUES ('Plato', ?)",
        (f"Republic ({source_chunk_id}-{span_start}-{span_end}-{source_form_snapshot})",),
    )
    target_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO cross_references ("
        "  source_chunk_id, target_id, source_span_start, source_span_end, "
        "  source_form_snapshot, reference_type, source_method, curator_status"
        ") VALUES (?, ?, ?, ?, ?, 'cites', 'rule_strong', 'approved')",
        (source_chunk_id, target_id, span_start, span_end, source_form_snapshot),
    )
    conn.commit()
    return cur.lastrowid


def test_a_clean_span_is_not_stale(tmp_path: Path):
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)])
    conn = store.open_db(db)
    try:
        _seed_xref(conn, source_chunk_id="c1", span_start=0, span_end=5, source_form_snapshot="alpha")
        stale = rx.find_stale_xrefs(conn)
    finally:
        conn.close()
    assert stale == []


def test_a_span_past_the_end_of_the_chunk_is_stale(tmp_path: Path):
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)])
    conn = store.open_db(db)
    try:
        xid = _seed_xref(
            conn, source_chunk_id="c1", span_start=0, span_end=len(_TEXT) + 50,
            source_form_snapshot="alpha",
        )
        stale = rx.find_stale_xrefs(conn)
    finally:
        conn.close()
    assert [s.id for s in stale] == [xid]
    assert stale[0].reason == "span past end of chunk"


def test_a_genuine_in_range_mismatch_is_stale(tmp_path: Path):
    """[0:5] is 'alpha'; recording 'gamma' is the shape a text edit
    before the span leaves behind — no relation to the actual slice."""

    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)])
    conn = store.open_db(db)
    try:
        xid = _seed_xref(
            conn, source_chunk_id="c1", span_start=0, span_end=5,
            source_form_snapshot="gamma",
        )
        stale = rx.find_stale_xrefs(conn)
    finally:
        conn.close()
    assert [s.id for s in stale] == [xid]
    assert stale[0].reason == "snapshot mismatch"


def test_414s_accepted_wide_snapshot_is_not_stale(tmp_path: Path):
    """#414: 'in Psalmo: cor meum et caro mea' at a span covering only
    'cor meum et caro mea' — the span is right, the snapshot is a
    deliberately wider citation-formula-plus-quote. Not a bug."""

    text = "he writes cor meum et caro mea exultaverunt"
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="lat", text=text)])
    conn = store.open_db(db)
    try:
        span_start = text.index("cor meum")
        span_end = span_start + len("cor meum et caro mea")
        _seed_xref(
            conn,
            source_chunk_id="c1",
            span_start=span_start,
            span_end=span_end,
            source_form_snapshot="in Psalmo: cor meum et caro mea",
        )
        stale = rx.find_stale_xrefs(conn)
    finally:
        conn.close()
    assert stale == []


def test_a_row_with_no_span_is_not_a_candidate(tmp_path: Path):
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)])
    conn = store.open_db(db)
    try:
        _seed_xref(conn, source_chunk_id="c1", span_start=None, span_end=None, source_form_snapshot=None)
        stale = rx.find_stale_xrefs(conn)
    finally:
        conn.close()
    assert stale == []


def test_dry_run_does_not_delete(tmp_path: Path, monkeypatch, capsys):
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)])
    conn = store.open_db(db)
    try:
        _seed_xref(conn, source_chunk_id="c1", span_start=0, span_end=5, source_form_snapshot="gamma")
    finally:
        conn.close()

    monkeypatch.setenv("MINERVA_DB", str(db))
    rc = rx.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dry run" in out

    conn = store.open_db(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM cross_references").fetchone()[0] == 1
    finally:
        conn.close()


def test_execute_deletes_only_the_stale_rows(tmp_path: Path, monkeypatch):
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)])
    conn = store.open_db(db)
    try:
        clean_id = _seed_xref(conn, source_chunk_id="c1", span_start=0, span_end=5, source_form_snapshot="alpha")
        stale_id = _seed_xref(conn, source_chunk_id="c1", span_start=0, span_end=5, source_form_snapshot="gamma")
    finally:
        conn.close()

    monkeypatch.setenv("MINERVA_DB", str(db))
    rc = rx.main(["--execute"])
    assert rc == 0

    conn = store.open_db(db)
    try:
        remaining = {row[0] for row in conn.execute("SELECT id FROM cross_references")}
    finally:
        conn.close()
    assert remaining == {clean_id}
    assert stale_id not in remaining


def test_no_database_is_a_failure(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("MINERVA_DB", str(tmp_path / "nope.sqlite"))
    rc = rx.main([])
    assert rc != 0
    assert "nope.sqlite" in capsys.readouterr().err
