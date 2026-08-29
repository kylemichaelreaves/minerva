"""The whole-corpus invariant audit (#320).

Three corpus-integrity defects — #307, #311, #314 — were found by one
query written from scratch each time and thrown away. What is pinned here
is the pair of properties that made it worth committing, and that the
throwaway versions kept getting wrong:

* **it checks every row, never a sample.** Both wrong numbers in this
  repo's history came from a sample that looked representative — the
  batch 2-ter record put ``grc`` at 99.67% where the population figure
  was 93.09%, and #311 was scoped from the sampled number and understated
  itself by 109×;
* **it reports rather than gates.** ``ara`` violates the lemma-surface
  invariant legitimately, because Stanza's multi-word-token expansion
  gives clitic sub-words their parent's span on purpose. A red/green
  check would have to be silenced, and a silenced check is not run.

The exit code therefore distinguishes "found problems" (0 — that is the
output, not a failure) from "could not look" (non-zero).
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

import audit_invariants as ai  # noqa: E402


def _seed(tmp_path: Path, chunks: list[dict], lemmas: list[tuple]) -> Path:
    """Build a real index, then write ``chunk_lemmas`` rows by hand.

    Rows are ``(chunk_id, token_index, surface_form, start, end)``.
    """

    db = tmp_path / "audit.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False))

    conn = store.open_db(db)
    try:
        conn.executemany(
            "INSERT INTO chunk_lemmas "
            "(chunk_id, token_index, surface_form, surface_start, surface_end, lemma) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(cid, i, surf, s, e, surf.lower()) for cid, i, surf, s, e in lemmas],
        )
        conn.commit()
    finally:
        conn.close()
    return db


# "alpha beta gamma" — alpha at [0:5], beta at [6:10], gamma at [11:16].
_TEXT = "alpha beta gamma"
_GOOD = [("c1", 0, "alpha", 0, 5), ("c1", 1, "beta", 6, 10), ("c1", 2, "gamma", 11, 16)]
# beta's span slid one character left, the shape a length-changing rewrite
# upstream of the offsets produces.
_DRIFTED = [("c1", 0, "alpha", 0, 5), ("c1", 1, "beta", 5, 9), ("c1", 2, "gamma", 11, 16)]


def _audit(db: Path):
    conn = store.open_db(db)
    try:
        return ai.audit_lemma_surface_offsets(conn)
    finally:
        conn.close()


def test_a_clean_corpus_reports_no_violations(tmp_path: Path):
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], _GOOD)
    result = _audit(db)
    assert result.rows_checked == 3
    assert result.violations == 0
    assert result.per_group["grc"] == (3, 0)
    assert result.examples == []


def test_a_drifted_span_is_counted_and_shown(tmp_path: Path):
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], _DRIFTED)
    result = _audit(db)
    assert result.violations == 1
    assert result.per_group["grc"] == (3, 1)
    # The example has to carry both sides. A count alone sends the next
    # reader back to write the query again, which is the thing #320 is
    # about.
    (example,) = result.examples
    assert example.chunk_id == "c1"
    assert "beta" in example.detail
    assert repr(" bet") in example.detail or " bet" in example.detail


def test_every_row_is_checked_rather_than_sampled(tmp_path: Path):
    # 300 rows across 3 languages. `rows_checked` must equal the table.
    chunks, lemmas = [], []
    for lang in ("grc", "deu", "lat"):
        for n in range(100):
            cid = f"{lang}{n:03d}"
            chunks.append(make_chunk(chunk_id=cid, lang=lang, text=_TEXT))
            lemmas.append((cid, 0, "alpha", 0, 5))
    db = _seed(tmp_path, chunks, lemmas)

    result = _audit(db)
    conn = store.open_db(db)
    try:
        total = conn.execute("SELECT count(*) FROM chunk_lemmas").fetchone()[0]
    finally:
        conn.close()
    assert result.rows_checked == total == 300
    assert sum(checked for checked, _ in result.per_group.values()) == 300


def test_violations_are_grouped_by_language(tmp_path: Path):
    chunks = [
        make_chunk(chunk_id="g1", lang="grc", text=_TEXT),
        make_chunk(chunk_id="d1", lang="deu", text=_TEXT),
    ]
    lemmas = [("g1", 0, "beta", 5, 9), ("d1", 0, "alpha", 0, 5)]
    result = _audit(_seed(tmp_path, chunks, lemmas))
    assert result.per_group["grc"] == (1, 1)
    assert result.per_group["deu"] == (1, 0)


def test_finding_violations_is_not_a_failure(tmp_path: Path, capsys, monkeypatch):
    """`ara` violates this invariant on purpose. A gate would be silenced,
    and a silenced gate is not run — so violations exit 0."""

    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], _DRIFTED)
    monkeypatch.setenv("MINERVA_DB", str(db))
    rc = ai.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "grc" in out
    assert "1" in out


def test_being_unable_to_look_is_a_failure(tmp_path: Path, capsys, monkeypatch):
    """The other half of the same decision: 'no problems found' and 'could
    not check' must not both be exit 0."""

    monkeypatch.setenv("MINERVA_DB", str(tmp_path / "nope.sqlite"))
    rc = ai.main([])
    assert rc != 0
    assert "nope.sqlite" in capsys.readouterr().err


def test_json_output_carries_the_counts(tmp_path: Path, capsys, monkeypatch):
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], _DRIFTED)
    monkeypatch.setenv("MINERVA_DB", str(db))
    capsys.readouterr()  # drop cmd_index's own output; the JSON must stand alone
    assert ai.main(["--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    # Selected by name rather than unpacked: the script carries more than one
    # invariant, and a positional read makes every addition break this test.
    entry = next(e for e in payload["invariants"] if e["name"] == "lemma_surface_offsets")
    assert entry["rows_checked"] == 3
    assert entry["violations"] == 1
    assert entry["per_group"]["grc"] == {"checked": 3, "violations": 1}


def test_work_id_invariant_is_clean_after_an_ordinary_ingest(tmp_path: Path):
    """`insert_chunks` writes `chunks.work_id`, so a normally-built index
    starts at zero violations — which is what makes a nonzero count later
    mean something."""

    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], _GOOD)
    conn = store.open_db(db)
    try:
        result = ai.audit_chunk_work_id(conn)
    finally:
        conn.close()

    assert result.rows_checked == 1
    assert result.violations == 0


def test_work_id_invariant_catches_a_row_the_view_hides(tmp_path: Path):
    """The failure mode the invariant exists for (#339): `chunks_full`
    inner-joins `works` on `work_id`, so a NULL does not degrade the row, it
    removes it from the view — and therefore from every query that would
    otherwise notice. The audit reads `chunks` directly for that reason.
    """

    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], _GOOD)
    conn = store.open_db(db)
    try:
        conn.execute("UPDATE chunks SET work_id = NULL WHERE chunk_id = 'c1'")
        conn.commit()
        # The view cannot see it, which is the point.
        assert conn.execute("SELECT COUNT(*) FROM chunks_full").fetchone()[0] == 0

        result = ai.audit_chunk_work_id(conn)
    finally:
        conn.close()

    assert result.rows_checked == 1
    assert result.violations == 1
    assert result.examples[0].chunk_id == "c1"
    assert "invisible in chunks_full" in result.examples[0].detail


def test_a_known_exception_is_reported_beside_the_number(
    tmp_path: Path, capsys, monkeypatch
):
    """`ara`'s 17% is explained in `_tokens_from_stanza_doc` and in #314.
    Printing the explanation next to the count is what stops the next
    operator re-investigating it."""

    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], _GOOD)
    monkeypatch.setenv("MINERVA_DB", str(db))
    ai.main([])
    assert "multi-word-token" in capsys.readouterr().out


class TestTheTargetComesFromTheEnvironment:
    """`$MINERVA_DB`, not a `--db` flag — the form
    `corpus-quality-audit.py` and `clean-hegel-lectures-glossary.py`
    already use. SonarCloud's `pythonsecurity:S8706` fails a PR when a CLI
    argument reaches `sqlite3.connect`, and it failed this script's first
    PR on exactly that line. Fixed in code rather than marked Accepted,
    because Accepted does not survive a line move (#167, #179)."""

    def test_the_environment_overrides_the_default(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MINERVA_DB", str(tmp_path / "elsewhere.sqlite"))
        assert ai.resolve_db_path() == tmp_path / "elsewhere.sqlite"

    def test_the_repo_index_is_the_default(self, monkeypatch):
        monkeypatch.delenv("MINERVA_DB", raising=False)
        assert ai.resolve_db_path().name == "index.sqlite"

    def test_there_is_no_db_flag(self, capsys):
        """A regression guard with a specific failure in mind: re-adding
        `--db` for convenience is what would turn the gate red again."""

        import pytest

        with pytest.raises(SystemExit):
            ai.main(["--db", "/tmp/whatever.sqlite"])
        assert "unrecognized arguments" in capsys.readouterr().err


def test_the_invariant_registry_is_not_empty():
    names = [inv.name for inv in ai.INVARIANTS]
    assert "lemma_surface_offsets" in names


def test_the_invariant_registry_includes_407_and_415():
    names = [inv.name for inv in ai.INVARIANTS]
    assert "xref_source_span" in names
    assert "refs_scan_coverage" in names


def _seed_xref(
    conn,
    *,
    source_chunk_id: str,
    span_start: int | None,
    span_end: int | None,
    source_form_snapshot: str | None,
) -> None:
    """Insert one `cross_references` row anchored at a byte span into its
    source chunk. Minimal but schema-valid: `reference_targets` and the
    NOT NULL columns `cross_references` requires get placeholder values."""

    # canonical_work varies by source chunk so repeated calls in one test
    # don't collide on reference_targets' (author, work) uniqueness.
    cur = conn.execute(
        "INSERT INTO reference_targets (canonical_author, canonical_work) "
        "VALUES ('Plato', ?)",
        (f"Republic ({source_chunk_id})",),
    )
    target_id = cur.lastrowid
    conn.execute(
        "INSERT INTO cross_references ("
        "  source_chunk_id, target_id, source_span_start, source_span_end, "
        "  source_form_snapshot, reference_type, source_method, curator_status"
        ") VALUES (?, ?, ?, ?, ?, 'cites', 'rule_strong', 'approved')",
        (source_chunk_id, target_id, span_start, span_end, source_form_snapshot),
    )
    conn.commit()


class TestXrefSourceSpan:
    """#407: 336 of 66,068 `cross_references` no longer point at the text
    they record, and nothing checked. Two distinct failure shapes, both
    caused by #285 (`chunk_id` hashes only `text[:120]`, so a chunk can
    shrink or shift past that point without its derived rows noticing)."""

    def test_a_clean_span_is_not_a_violation(self, tmp_path: Path):
        db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], [])
        conn = store.open_db(db)
        try:
            _seed_xref(
                conn,
                source_chunk_id="c1",
                span_start=0,
                span_end=5,
                source_form_snapshot="alpha",
            )
            result = ai.audit_xref_source_span(conn)
        finally:
            conn.close()
        assert result.rows_checked == 1
        assert result.violations == 0

    def test_a_span_past_the_end_of_the_chunk_is_a_violation(self, tmp_path: Path):
        db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], [])
        conn = store.open_db(db)
        try:
            _seed_xref(
                conn,
                source_chunk_id="c1",
                span_start=0,
                span_end=len(_TEXT) + 50,
                source_form_snapshot="alpha",
            )
            result = ai.audit_xref_source_span(conn)
        finally:
            conn.close()
        assert result.violations == 1
        assert "past end" in result.examples[0].detail

    def test_an_in_range_span_with_a_mismatched_snapshot_is_a_violation(
        self, tmp_path: Path
    ):
        db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], [])
        conn = store.open_db(db)
        try:
            # [0:5] is "alpha" in _TEXT; claiming the snapshot is "gamma"
            # is the shape a text edit before the span leaves behind.
            _seed_xref(
                conn,
                source_chunk_id="c1",
                span_start=0,
                span_end=5,
                source_form_snapshot="gamma",
            )
            result = ai.audit_xref_source_span(conn)
        finally:
            conn.close()
        assert result.violations == 1
        assert "gamma" in result.examples[0].detail

    def test_a_row_with_no_span_at_all_is_not_counted(self, tmp_path: Path):
        """Not every cross_reference is anchored to a byte span — the
        columns are nullable. An unanchored citation is out of scope for
        this invariant, not a violation of it."""

        db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], [])
        conn = store.open_db(db)
        try:
            _seed_xref(
                conn,
                source_chunk_id="c1",
                span_start=None,
                span_end=None,
                source_form_snapshot=None,
            )
            result = ai.audit_xref_source_span(conn)
        finally:
            conn.close()
        assert result.rows_checked == 0
        assert result.violations == 0

    def test_grouped_by_language(self, tmp_path: Path):
        db = _seed(
            tmp_path,
            [
                make_chunk(chunk_id="g1", lang="grc", text=_TEXT),
                make_chunk(chunk_id="d1", lang="deu", text=_TEXT),
            ],
            [],
        )
        conn = store.open_db(db)
        try:
            _seed_xref(
                conn,
                source_chunk_id="g1",
                span_start=0,
                span_end=999,
                source_form_snapshot="alpha",
            )
            _seed_xref(
                conn,
                source_chunk_id="d1",
                span_start=0,
                span_end=5,
                source_form_snapshot="alpha",
            )
            result = ai.audit_xref_source_span(conn)
        finally:
            conn.close()
        assert result.per_group["grc"] == (1, 1)
        assert result.per_group["deu"] == (1, 0)


class TestRefsScanCoverage:
    """#415: chunks that have never been scanned for cross-references in
    either direction, and nothing reported it — four ingest fixes each said
    in their own PR body that a refs pass was outstanding, and nothing reads
    a PR body after the merge."""

    def test_a_scanned_chunk_is_not_a_violation(self, tmp_path: Path):
        db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], [])
        conn = store.open_db(db)
        try:
            conn.execute(
                "INSERT INTO refs_scan_state (chunk_id, text_hash) VALUES ('c1', 'h')"
            )
            conn.commit()
            result = ai.audit_refs_scan_coverage(conn)
        finally:
            conn.close()
        assert result.rows_checked == 1
        assert result.violations == 0

    def test_an_unscanned_chunk_is_a_violation(self, tmp_path: Path):
        db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], [])
        conn = store.open_db(db)
        try:
            result = ai.audit_refs_scan_coverage(conn)
        finally:
            conn.close()
        assert result.violations == 1
        assert result.examples[0].chunk_id == "c1"

    def test_grouped_by_author(self, tmp_path: Path):
        db = _seed(
            tmp_path,
            [
                make_chunk(chunk_id="a1", author="Aesop", work="Fables", lang="eng", text=_TEXT),
                make_chunk(chunk_id="h1", author="Hegel", work="Enzyklopädie", lang="deu", text=_TEXT),
            ],
            [],
        )
        conn = store.open_db(db)
        try:
            conn.execute(
                "INSERT INTO refs_scan_state (chunk_id, text_hash) VALUES ('h1', 'h')"
            )
            conn.commit()
            result = ai.audit_refs_scan_coverage(conn)
        finally:
            conn.close()
        assert result.per_group["Aesop"] == (1, 1)
        assert result.per_group["Hegel"] == (1, 0)


def test_chunks_without_lemma_rows_are_not_counted(tmp_path: Path):
    """A chunk nothing has lemmatized is not a violation — the invariant
    is about rows that exist, not rows that should."""

    chunks = [
        make_chunk(chunk_id="c1", lang="grc", text=_TEXT),
        make_chunk(chunk_id="c2", lang="grc", text=_TEXT),
    ]
    result = _audit(_seed(tmp_path, chunks, [("c1", 0, "alpha", 0, 5)]))
    assert result.rows_checked == 1
    assert result.violations == 0
