"""Who last decided a cross-reference's status (#718).

A curator's rejection used to be indistinguishable from llm-verify's:
both left ``source_method='rule+embed+llm'`` and nothing else. So a bulk
re-judge could overturn a person's call without knowing it.
``curated_by`` / ``curated_at`` record the last verdict's author, and
the bulk verifiers leave a row a human decided alone.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from unittest.mock import patch

import numpy as np
import pytest

from minerva import llm
from minerva.cli.refs.review import cmd_refs_review
from minerva.refs import embed_verify, llm_verify
from minerva.refs import schema as refs_schema
from minerva.refs.update_queries import update_reference


class _AcceptAll(llm.LLMBackend):
    """Keeps every row it is shown, and records which ids it saw."""

    def __init__(self, *, references: bool = True) -> None:
        self.seen: list[int] = []
        self.references = references
        self.name = "accept-all"

    def complete(self, messages: list[llm.Message], *, temperature: float = 0.2) -> str:
        rows = json.loads(messages[-1].content)
        self.seen.extend(r["id"] for r in rows)
        return json.dumps(
            [
                {"id": r["id"], "references": self.references, "type": "cites", "confidence": 0.9}
                for r in rows
            ]
        )


class _ZeroEmbedder:
    """Every phrase encodes to zero, so cosine is 0 and embed-verify rejects."""

    def encode(self, phrases, **_: object) -> np.ndarray:
        return np.zeros((len(list(phrases)), 4), dtype=np.float32)


def _seed(
    conn: sqlite3.Connection,
    *,
    chunk_id: str = "rep-509d",
    curator_status: str = "auto",
    source_method: str = "rule_weak",
    quoted_phrase: str | None = None,
) -> int:
    target = refs_schema.ensure_target(
        conn, canonical_author="Aristotle", canonical_work="Nicomachean Ethics"
    )
    rid = refs_schema.insert_cross_reference(
        conn,
        source_chunk_id=chunk_id,
        target_id=target.id,
        target_chunk_id="ne-1097b",
        reference_type="quotes" if quoted_phrase else "cites",
        source_form_snapshot="Aristoteles",
        quoted_phrase=quoted_phrase,
        confidence=0.6,
        source_method=source_method,
        curator_status=curator_status,
    )
    conn.commit()
    return rid


def _provenance(conn: sqlite3.Connection, rid: int) -> tuple[str | None, str | None]:
    row = conn.execute(
        "SELECT curated_by, curated_at FROM cross_references WHERE id = ?", (rid,)
    ).fetchone()
    return tuple(row)


def _seed_target_embedding(conn: sqlite3.Connection) -> None:
    vec = np.asarray([1, 0, 0, 0], dtype=np.float32)
    conn.execute(
        "INSERT OR REPLACE INTO embeddings(chunk_id, model, dim, vector) VALUES (?, ?, ?, ?)",
        ("ne-1097b", "fake", 4, vec.tobytes()),
    )
    conn.commit()


def _mark_human(conn: sqlite3.Connection, rid: int, status: str) -> None:
    update_reference(conn, rid, status=status, note=None, update_note=False)


class TestColumns:
    def test_a_new_row_has_no_verdict_author(self, populated_db: sqlite3.Connection) -> None:
        assert _provenance(populated_db, _seed(populated_db)) == (None, None)

    def test_curated_by_rejects_an_unknown_actor(self, populated_db: sqlite3.Connection) -> None:
        rid = _seed(populated_db)
        with pytest.raises(sqlite3.IntegrityError):
            populated_db.execute(
                "UPDATE cross_references SET curated_by = 'robot' WHERE id = ?", (rid,)
            )


class TestHumanPathsStampHuman:
    def test_the_patch_path(self, populated_db: sqlite3.Connection) -> None:
        rid = _seed(populated_db)
        _mark_human(populated_db, rid, "rejected")
        by, at = _provenance(populated_db, rid)
        assert by == "human"
        assert at is not None and at.endswith("Z")

    @pytest.mark.parametrize(("key", "status"), [("a", "approved"), ("r", "rejected")])
    def test_the_review_walker(
        self, populated_db: sqlite3.Connection, db_path, key: str, status: str
    ) -> None:
        rid = _seed(populated_db, source_method="rule_strong")
        args = argparse.Namespace(db=db_path, source_author=None, target_author=None, limit=1)
        with patch("minerva.cli.refs.review._prompt", side_effect=[key]):
            assert cmd_refs_review(args) == 0
        row = populated_db.execute(
            "SELECT curator_status, curated_by FROM cross_references WHERE id = ?", (rid,)
        ).fetchone()
        assert tuple(row) == (status, "human")

    def test_a_skipped_row_is_not_stamped(self, populated_db: sqlite3.Connection, db_path) -> None:
        rid = _seed(populated_db, source_method="rule_strong")
        args = argparse.Namespace(db=db_path, source_author=None, target_author=None, limit=1)
        with patch("minerva.cli.refs.review._prompt", side_effect=["s"]):
            cmd_refs_review(args)
        assert _provenance(populated_db, rid) == (None, None)


class TestVerifiersStampThemselves:
    @pytest.mark.parametrize("references", [True, False])
    def test_llm_verify(self, populated_db: sqlite3.Connection, references: bool) -> None:
        rid = _seed(populated_db)
        llm_verify.verify_rows_with_llm(
            populated_db, _AcceptAll(references=references), skip_short_chunks=False
        )
        by, at = _provenance(populated_db, rid)
        assert by == "llm"
        assert at is not None

    def test_embed_verify_reject(self, populated_db: sqlite3.Connection) -> None:
        _seed_target_embedding(populated_db)
        rid = _seed(populated_db, quoted_phrase="the function of the good")
        stats = embed_verify.verify_quoted_references(populated_db, _ZeroEmbedder())
        assert stats.rejected == 1
        assert _provenance(populated_db, rid)[0] == "embed"


class TestVerifiersLeaveHumanDecisionsAlone:
    def test_llm_verify_skips_a_row_a_human_put_back_to_auto(
        self, populated_db: sqlite3.Connection
    ) -> None:
        rid = _seed(populated_db)
        _mark_human(populated_db, rid, "auto")
        backend = _AcceptAll()
        llm_verify.verify_rows_with_llm(populated_db, backend, skip_short_chunks=False)
        assert rid not in backend.seen

    def test_rejudge_blind_skips_a_human_rejection(self, populated_db: sqlite3.Connection) -> None:
        text = ("lorem ipsum dolor " * 70) + "as Aristoteles says " + ("sit amet " * 100)
        populated_db.execute("UPDATE chunks SET text = ? WHERE chunk_id = 'rep-509d'", (text,))
        target = refs_schema.ensure_target(
            populated_db, canonical_author="Aristotle", canonical_work="Nicomachean Ethics"
        )
        start = text.index("Aristoteles")
        rid = refs_schema.insert_cross_reference(
            populated_db,
            source_chunk_id="rep-509d",
            target_id=target.id,
            reference_type="cites",
            source_span_start=start,
            source_span_end=start + len("Aristoteles"),
            source_form_snapshot="Aristoteles",
            confidence=0.6,
            source_method="rule+embed+llm",
            curator_status="auto",
        )
        _mark_human(populated_db, rid, "rejected")
        backend = _AcceptAll()
        llm_verify.verify_rows_with_llm(populated_db, backend, rejudge_blind=True)
        assert rid not in backend.seen

    def test_embed_verify_skips_a_row_a_human_put_back_to_auto(
        self, populated_db: sqlite3.Connection
    ) -> None:
        _seed_target_embedding(populated_db)
        rid = _seed(populated_db, quoted_phrase="the function of the good")
        _mark_human(populated_db, rid, "auto")
        stats = embed_verify.verify_quoted_references(populated_db, _ZeroEmbedder())
        assert stats.examined == 0
        assert (
            populated_db.execute(
                "SELECT curator_status FROM cross_references WHERE id = ?", (rid,)
            ).fetchone()[0]
            == "auto"
        )
