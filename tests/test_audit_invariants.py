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


def test_finding_violations_is_not_a_failure(tmp_path: Path, capsys):
    """`ara` violates this invariant on purpose. A gate would be silenced,
    and a silenced gate is not run — so violations exit 0."""

    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], _DRIFTED)
    rc = ai.main(["--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "grc" in out
    assert "1" in out


def test_being_unable_to_look_is_a_failure(tmp_path: Path, capsys):
    """The other half of the same decision: 'no problems found' and 'could
    not check' must not both be exit 0."""

    rc = ai.main(["--db", str(tmp_path / "nope.sqlite")])
    assert rc != 0
    assert "nope.sqlite" in capsys.readouterr().err


def test_json_output_carries_the_counts(tmp_path: Path, capsys):
    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], _DRIFTED)
    capsys.readouterr()  # drop cmd_index's own output; the JSON must stand alone
    assert ai.main(["--db", str(db), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    (entry,) = payload["invariants"]
    assert entry["name"] == "lemma_surface_offsets"
    assert entry["rows_checked"] == 3
    assert entry["violations"] == 1
    assert entry["per_group"]["grc"] == {"checked": 3, "violations": 1}


def test_a_known_exception_is_reported_beside_the_number(tmp_path: Path, capsys):
    """`ara`'s 17% is explained in `_tokens_from_stanza_doc` and in #314.
    Printing the explanation next to the count is what stops the next
    operator re-investigating it."""

    db = _seed(tmp_path, [make_chunk(chunk_id="c1", lang="grc", text=_TEXT)], _GOOD)
    ai.main(["--db", str(db)])
    assert "multi-word-token" in capsys.readouterr().out


def test_the_invariant_registry_is_not_empty():
    names = [inv.name for inv in ai.INVARIANTS]
    assert "lemma_surface_offsets" in names


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
