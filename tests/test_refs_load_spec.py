"""``minerva refs load-spec`` — dry-run accuracy and write semantics.

Pins the 2026-06-10 audit fix: dry-run used to return the dedup-skip
sentinel for every would-insert (the summary always said inserted=0)
and ``ensure_target`` wrote reference_targets rows that survived only
because the connection happened to close without a commit. Dry-run now
counts would-inserts and rolls back explicitly.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("yaml")

from minerva.cli.refs.load_spec_cmd import cmd_refs_load_spec

SPEC = """\
version: 1
references:
  - source:
      chunk_id: "rep-509d"
    target:
      author: Aristotle
      work: "De anima"
    type: cites
    source_form: "as Aristotle says"
  - source:
      chunk_id: "rep-514a"
    target:
      author: Aristotle
      work: "De anima"
    type: alludes
"""


def _args(db_path: Path, spec_path: Path, *, dry_run: bool) -> argparse.Namespace:
    return argparse.Namespace(db=db_path, paths=[str(spec_path)], dry_run=dry_run)


def _counts(db_path: Path) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        targets = conn.execute(
            "SELECT COUNT(*) FROM reference_targets "
            "WHERE canonical_author = 'Aristotle' AND canonical_work = 'De anima'"
        ).fetchone()[0]
        xrefs = conn.execute("SELECT COUNT(*) FROM cross_references").fetchone()[0]
        return targets, xrefs
    finally:
        conn.close()


def test_dry_run_reports_would_inserts_and_writes_nothing(
    populated_db, db_path: Path, tmp_path: Path, capsys
):
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(SPEC, encoding="utf-8")

    rc = cmd_refs_load_spec(_args(db_path, spec_path, dry_run=True))
    assert rc == 0

    captured = capsys.readouterr()
    # Both references would be inserted — the old code reported
    # inserted=0 because dry-run returned the dedup-skip sentinel.
    assert "inserted=2" in captured.err
    assert "skipped=0" in captured.err
    assert "dry-run" in captured.err
    assert captured.out.count("would insert") == 2

    # Nothing persisted: not the cross_references rows AND not the
    # reference_targets row ensure_target created while resolving.
    assert _counts(db_path) == (0, 0)


def test_real_run_inserts_and_rerun_dedups(populated_db, db_path: Path, tmp_path: Path, capsys):
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(SPEC, encoding="utf-8")

    rc = cmd_refs_load_spec(_args(db_path, spec_path, dry_run=False))
    assert rc == 0
    assert "inserted=2" in capsys.readouterr().err
    assert _counts(db_path) == (1, 2)

    # Idempotent reload: everything dedups.
    rc = cmd_refs_load_spec(_args(db_path, spec_path, dry_run=False))
    assert rc == 0
    assert "skipped=2" in capsys.readouterr().err
    assert _counts(db_path) == (1, 2)


def test_dry_run_after_real_run_reports_skips(populated_db, db_path: Path, tmp_path: Path, capsys):
    """Dry-run must still distinguish would-insert from dedup-skip:
    against a DB that already has the rows, it reports skips."""

    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(SPEC, encoding="utf-8")

    cmd_refs_load_spec(_args(db_path, spec_path, dry_run=False))
    capsys.readouterr()

    rc = cmd_refs_load_spec(_args(db_path, spec_path, dry_run=True))
    assert rc == 0
    captured = capsys.readouterr()
    assert "inserted=0" in captured.err
    assert "skipped=2" in captured.err
    assert _counts(db_path) == (1, 2)
