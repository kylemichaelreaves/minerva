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
        "INSERT INTO reference_targets (canonical_author, canonical_work) VALUES ('Plato', ?)",
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
        _seed_xref(
            conn, source_chunk_id="c1", span_start=0, span_end=5, source_form_snapshot="alpha"
        )
        stale = rx.find_stale_xrefs(conn)
    finally:
        conn.close()
    assert stale == []


def test_a_span_past_the_end_of_the_chunk_is_stale(tmp_path: Path):
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)])
    conn = store.open_db(db)
    try:
        xid = _seed_xref(
            conn,
            source_chunk_id="c1",
            span_start=0,
            span_end=len(_TEXT) + 50,
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
            conn,
            source_chunk_id="c1",
            span_start=0,
            span_end=5,
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
        _seed_xref(
            conn, source_chunk_id="c1", span_start=None, span_end=None, source_form_snapshot=None
        )
        stale = rx.find_stale_xrefs(conn)
    finally:
        conn.close()
    assert stale == []


def test_dry_run_does_not_delete(tmp_path: Path, monkeypatch, capsys):
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)])
    conn = store.open_db(db)
    try:
        _seed_xref(
            conn, source_chunk_id="c1", span_start=0, span_end=5, source_form_snapshot="gamma"
        )
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
        clean_id = _seed_xref(
            conn, source_chunk_id="c1", span_start=0, span_end=5, source_form_snapshot="alpha"
        )
        stale_id = _seed_xref(
            conn, source_chunk_id="c1", span_start=0, span_end=5, source_form_snapshot="gamma"
        )
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


def test_execute_invalidates_refs_scan_state_for_touched_chunks(tmp_path: Path, monkeypatch):
    """#459: the script's own docstring assumes deleting a stale xref
    means `refs_scan_state.text_hash` already mismatches the chunk's
    current text, so the existing skip cache re-scans it unprompted.
    That's false whenever the row was stale for a reason other than the
    chunk's own text changing (e.g. an in-range snapshot mismatch on a
    chunk nobody edited) — in that case `refs_scan_state` still reads as
    current and `refs build` skips the chunk forever, silently
    withholding whatever a rescan would rediscover. Deleting the
    chunk's `refs_scan_state` row alongside the stale xref removes that
    reliance: the next `refs build` treats the chunk as unscanned."""

    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)])
    conn = store.open_db(db)
    try:
        _seed_xref(
            conn, source_chunk_id="c1", span_start=0, span_end=5, source_form_snapshot="gamma"
        )
        # A scan_state row whose hash matches c1's *current* text — the
        # "nothing has changed since we scanned" case #459 measured on
        # the live Aristotle rows, not a chunk whose text actually moved.
        conn.execute(
            "INSERT INTO refs_scan_state (chunk_id, text_hash) VALUES ('c1', text_hash(?))",
            (_TEXT,),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("MINERVA_DB", str(db))
    rc = rx.main(["--execute"])
    assert rc == 0

    conn = store.open_db(db)
    try:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM refs_scan_state WHERE chunk_id = 'c1'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert remaining == 0


def test_no_database_is_a_failure(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("MINERVA_DB", str(tmp_path / "nope.sqlite"))
    rc = rx.main([])
    assert rc != 0
    assert "nope.sqlite" in capsys.readouterr().err


def test_a_span_shifted_inside_the_chunk_is_stale(tmp_path: Path):
    """#545: text removed from the *front* of a chunk whose `chunk_id`
    survived slides every span in it. The snapshot and the slice then
    overlap heavily — difflib ratio 0.857 for this pair — but the
    dropped prefix is two letters of a word, not a citation formula.
    The ratio alone cannot tell this from #414's accepted population,
    whose ratios straddle it (0.887)."""

    text = "omas Aquinas, writing later"
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="eng", text=text)])
    conn = store.open_db(db)
    try:
        xid = _seed_xref(
            conn,
            source_chunk_id="c1",
            span_start=0,
            span_end=len("omas Aquinas, "),
            source_form_snapshot="Thomas Aquinas",
        )
        stale = rx.find_stale_xrefs(conn)
    finally:
        conn.close()
    assert [s.id for s in stale] == [xid]
    assert stale[0].reason == "snapshot mismatch"


def test_a_span_shifted_by_a_leading_character_is_stale(tmp_path: Path):
    """#545's second live row: the span slid one character left, so the
    slice picks up a leading space and loses the final letter. Nothing
    aligns in either direction, but difflib still scores it 0.889."""

    text = " Schellin and the others"
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="deu", text=text)])
    conn = store.open_db(db)
    try:
        xid = _seed_xref(
            conn,
            source_chunk_id="c1",
            span_start=0,
            span_end=len(" Schellin"),
            source_form_snapshot="Schelling",
        )
        stale = rx.find_stale_xrefs(conn)
    finally:
        conn.close()
    assert [s.id for s in stale] == [xid]
    assert stale[0].reason == "snapshot mismatch"


def test_414s_wide_snapshot_truncated_at_120_chars_is_not_stale(tmp_path: Path):
    """`source_form_snapshot` is capped at 120 characters, so a long
    accepted row's snapshot stops mid-quote while the span runs on past
    it. 9 of the 212 live accepted rows have this shape, and neither
    string then contains the other — which is why a containment test
    cannot stand in for the ratio here. Measured 2026-09-11."""

    quote = (
        "Neque nocebo, inquit, in ueritate mea, neque profanabo testamentum meum, "
        "et quae procedunt de labiis meis non reprobabo"
    )
    snapshot = ("psalmi: " + quote)[:120]
    assert len(snapshot) == 120
    assert quote not in snapshot and snapshot not in quote

    text = "ut ait " + quote + " dicit enim"
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="lat", text=text)])
    conn = store.open_db(db)
    try:
        span_start = text.index(quote)
        _seed_xref(
            conn,
            source_chunk_id="c1",
            span_start=span_start,
            span_end=span_start + len(quote),
            source_form_snapshot=snapshot,
        )
        stale = rx.find_stale_xrefs(conn)
    finally:
        conn.close()
    assert stale == []
