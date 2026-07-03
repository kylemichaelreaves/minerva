"""Tests for ``minerva refs review`` curator walker."""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest

from minerva.cli.refs.review import cmd_refs_review


def _seed_auto_xref(
    conn,
    *,
    source_chunk_id: str,
    xref_id: int = 1,
    target_author: str = "Aristotle",
    target_work: str = "Nicomachean Ethics",
) -> int:
    ed_id = conn.execute(
        "SELECT edition_id FROM chunks WHERE chunk_id = ?", (source_chunk_id,)
    ).fetchone()[0]
    row = conn.execute(
        "SELECT id FROM reference_targets "
        "WHERE canonical_author = ? AND canonical_work = ?",
        (target_author, target_work),
    ).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO reference_targets (canonical_author, canonical_work) "
            "VALUES (?, ?)",
            (target_author, target_work),
        )
        target_id = cur.lastrowid
    else:
        target_id = row[0]
    cur = conn.execute(
        "INSERT INTO cross_references ("
        "  id, source_chunk_id, target_id, target_chunk_id, reference_type, "
        "  confidence, source_method, curator_status, "
        "  source_edition_id, source_sort_key, source_form_snapshot, "
        "  source_instance_index, source_span_start, source_span_end"
        ") VALUES (?, ?, ?, NULL, 'cites', 0.8, 'rule_strong', 'auto', ?, "
        "  '1097b', 'NE 1097b', 1, 0, 12)",
        (xref_id, source_chunk_id, target_id, ed_id),
    )
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def review_db(populated_db):
    _seed_auto_xref(populated_db, source_chunk_id="rep-509d", xref_id=1)
    _seed_auto_xref(
        populated_db,
        source_chunk_id="ne-1097b",
        xref_id=2,
        target_author="Plato",
        target_work="Republic",
    )
    _seed_auto_xref(
        populated_db,
        source_chunk_id="phaedo-72e",
        xref_id=3,
        target_author="Plato",
        target_work="Phaedo",
    )
    return populated_db


def test_refs_review_approve_reject_skip(tmp_path, review_db, db_path):
    args = argparse.Namespace(
        db=db_path,
        source_author=None,
        target_author=None,
        limit=3,
    )

    with patch(
        "minerva.cli.refs.review._prompt",
        side_effect=["a", "r", "s"],
    ):
        rc = cmd_refs_review(args)

    assert rc == 0
    statuses = {
        row[0]
        for row in review_db.execute(
            "SELECT curator_status FROM cross_references ORDER BY id"
        ).fetchall()
    }
    assert statuses == {"approved", "rejected", "auto"}


def test_refs_review_quit_leaves_remaining_auto(tmp_path, review_db, db_path):
    args = argparse.Namespace(
        db=db_path,
        source_author=None,
        target_author=None,
        limit=10,
    )

    with patch("minerva.cli.refs.review._prompt", side_effect=["q"]):
        rc = cmd_refs_review(args)

    assert rc == 0
    assert review_db.execute(
        "SELECT COUNT(*) FROM cross_references WHERE curator_status='auto'"
    ).fetchone()[0] == 3
