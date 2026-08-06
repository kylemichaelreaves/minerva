"""HTTP-handler tests for cross-reference endpoints.

The refs stack went un-tested in the original audit — these tests
exercise the four GET surfaces plus the PATCH curator update so a
regression in the refs API doesn't slip past CI silently.

We build the queue directly via ``refs.schema.insert_cross_reference``
rather than going through the rules pipeline; that keeps these tests
independent of the LLM verifier and the embed-only sweep.
"""

from __future__ import annotations

import sqlite3

import pytest
from conftest import StubBackend, make_deps

from minerva.http.handlers.references import (
    _handle_chunk_references,
    _handle_reference_update,
    _handle_references_list,
    _handle_review_queue,
    _handle_work_references_map,
)
from minerva.http.server_core import _HTTPError
from minerva.refs import schema as refs_schema

# ════════════════════════════════════════════════════════════════════
# Seed: a Plato chunk that "cites" an Aristotle chunk + the symmetric
# in-corpus row to exercise the joined target metadata.
# ════════════════════════════════════════════════════════════════════


def _seed_two_refs(conn: sqlite3.Connection) -> dict[str, int]:
    """Insert one Plato→Aristotle ref (auto, conf 0.85) and one
    Aristotle→Cicero ref (manual). Returns the new row ids keyed by
    a short label.
    """

    target_plato_to_aristotle = refs_schema.ensure_target(
        conn,
        canonical_author="Aristotle",
        canonical_work="Nicomachean Ethics",
    )
    target_aristotle_to_cicero = refs_schema.ensure_target(
        conn,
        canonical_author="Cicero",
        canonical_work="*",
    )

    pa_id = refs_schema.insert_cross_reference(
        conn,
        source_chunk_id="rep-509d",
        target_id=target_plato_to_aristotle.id,
        target_chunk_id="ne-1097b",
        target_locator="1097b",
        reference_type="cites",
        source_form_snapshot="Aristoteles",
        confidence=0.85,
        source_method="rule+embed+llm",
        curator_status="auto",
    )
    ac_id = refs_schema.insert_cross_reference(
        conn,
        source_chunk_id="ne-1097b",
        target_id=target_aristotle_to_cicero.id,
        target_locator=None,
        reference_type="cites",
        source_form_snapshot="Cicero",
        confidence=0.95,
        source_method="manual",
        curator_status="manual",
    )
    conn.commit()
    return {"plato_to_aristotle": pa_id, "aristotle_to_cicero": ac_id}


# ════════════════════════════════════════════════════════════════════
# GET /api/chunks/:id/references
# ════════════════════════════════════════════════════════════════════


class TestChunkReferences:
    def test_outgoing_and_incoming(self, populated_db: sqlite3.Connection) -> None:
        ids = _seed_two_refs(populated_db)
        deps = make_deps(populated_db, StubBackend())

        # Plato chunk has 1 outgoing (→ Aristotle), 0 incoming
        out = _handle_chunk_references(deps, "rep-509d", {})
        assert out["chunk_id"] == "rep-509d"
        assert len(out["outgoing"]) == 1
        assert len(out["incoming"]) == 0
        assert out["outgoing"][0]["id"] == ids["plato_to_aristotle"]
        assert out["outgoing"][0]["target"]["author"] == "Aristotle"
        assert out["outgoing"][0]["reference_type"] == "cites"

        # Aristotle chunk has 1 outgoing (→ Cicero) and 1 incoming
        # (from Plato).
        ne = _handle_chunk_references(deps, "ne-1097b", {})
        assert len(ne["outgoing"]) == 1
        assert ne["outgoing"][0]["target"]["author"] == "Cicero"
        assert len(ne["incoming"]) == 1
        assert ne["incoming"][0]["source_chunk_id"] == "rep-509d"

    def test_min_confidence_filter(self, populated_db: sqlite3.Connection) -> None:
        _seed_two_refs(populated_db)
        deps = make_deps(populated_db, StubBackend())
        # min_confidence=0.9 should drop the 0.85 Plato→Aristotle row
        out = _handle_chunk_references(deps, "rep-509d", {"min_confidence": "0.9"})
        assert out["outgoing"] == []

    def test_unknown_chunk_returns_empty(self, populated_db: sqlite3.Connection) -> None:
        deps = make_deps(populated_db, StubBackend())
        out = _handle_chunk_references(deps, "nonexistent", {})
        assert out["outgoing"] == []
        assert out["incoming"] == []


# ════════════════════════════════════════════════════════════════════
# GET /api/works/:id/references_map
# ════════════════════════════════════════════════════════════════════


class TestWorkReferencesMap:
    def test_returns_chunk_summary(self, populated_db: sqlite3.Connection) -> None:
        _seed_two_refs(populated_db)
        deps = make_deps(populated_db, StubBackend())
        # Look up Plato Republic's work_id from the DB
        work_id = populated_db.execute("SELECT id FROM works WHERE title='Republic'").fetchone()[0]
        # populated_db seeds Plato chunks with lang='eng'; the
        # endpoint defaults to 'grc' for the production reader.
        out = _handle_work_references_map(deps, work_id, {"lang": "eng"})
        assert "by_chunk" in out
        # rep-509d should have 1 outgoing ref summary
        by = out["by_chunk"]
        assert "rep-509d" in by
        assert by["rep-509d"]["count"] >= 1


# ════════════════════════════════════════════════════════════════════
# GET /api/references/by-author
# ════════════════════════════════════════════════════════════════════


class TestReferencesByAuthor:
    def test_filter_by_source_author(self, populated_db: sqlite3.Connection) -> None:
        _seed_two_refs(populated_db)
        deps = make_deps(populated_db, StubBackend())
        out = _handle_references_list(deps, {"source_author": "Plato"})
        ids = {r["source_chunk_id"] for r in out["references"]}
        assert ids == {"rep-509d"}

    def test_filter_by_target_author(self, populated_db: sqlite3.Connection) -> None:
        _seed_two_refs(populated_db)
        deps = make_deps(populated_db, StubBackend())
        out = _handle_references_list(deps, {"target_author": "Cicero"})
        assert len(out["references"]) == 1
        assert out["references"][0]["target"]["author"] == "Cicero"

    def test_paging_limit(self, populated_db: sqlite3.Connection) -> None:
        _seed_two_refs(populated_db)
        deps = make_deps(populated_db, StubBackend())
        out = _handle_references_list(deps, {"limit": "1"})
        assert len(out["references"]) == 1

    def test_filter_by_reference_type(self, populated_db: sqlite3.Connection) -> None:
        # Seed two "cites" rows, then add one "quotes" row so the filter
        # is selective (not just matching everything).
        _seed_two_refs(populated_db)
        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="Metaphysics",
        )
        refs_schema.insert_cross_reference(
            populated_db,
            source_chunk_id="rep-509d",
            target_id=target.id,
            target_chunk_id=None,
            target_locator="980a",
            reference_type="quotes",
            source_form_snapshot="Aristoteles",
            confidence=0.9,
            source_method="manual",
            curator_status="manual",
        )
        populated_db.commit()
        deps = make_deps(populated_db, StubBackend())

        cites = _handle_references_list(deps, {"reference_type": "cites"})
        assert {r["reference_type"] for r in cites["references"]} == {"cites"}
        assert len(cites["references"]) == 2
        assert cites["filters"]["reference_type"] == "cites"

        quotes = _handle_references_list(deps, {"reference_type": "quotes"})
        assert len(quotes["references"]) == 1
        assert quotes["references"][0]["reference_type"] == "quotes"


# ════════════════════════════════════════════════════════════════════
# GET /api/references/review_queue
# ════════════════════════════════════════════════════════════════════


class TestReviewQueue:
    def test_returns_only_auto_rows(self, populated_db: sqlite3.Connection) -> None:
        _seed_two_refs(populated_db)
        deps = make_deps(populated_db, StubBackend())
        out = _handle_review_queue(deps, {})
        # Only the auto row (Plato→Aristotle) should appear; the
        # Cicero one is curator_status='manual'.
        assert all(r["curator_status"] == "auto" for r in out["references"])
        assert len(out["references"]) == 1

    def test_source_author_filter(self, populated_db: sqlite3.Connection) -> None:
        _seed_two_refs(populated_db)
        deps = make_deps(populated_db, StubBackend())
        out = _handle_review_queue(deps, {"source_author": "Aristotle"})
        # Aristotle's only outgoing ref is the manual Cicero one;
        # nothing matches in the auto queue.
        assert out["references"] == []


# ════════════════════════════════════════════════════════════════════
# PATCH /api/references/:id  (curator update)
# ════════════════════════════════════════════════════════════════════


class TestReferenceUpdate:
    def test_approve(self, populated_db: sqlite3.Connection) -> None:
        ids = _seed_two_refs(populated_db)
        deps = make_deps(populated_db, StubBackend())
        out = _handle_reference_update(
            deps,
            ids["plato_to_aristotle"],
            {"curator_status": "approved"},
        )
        assert out["id"] == ids["plato_to_aristotle"]
        assert out["curator_status"] == "approved"
        # Confirm persisted
        row = populated_db.execute(
            "SELECT curator_status FROM cross_references WHERE id=?",
            (ids["plato_to_aristotle"],),
        ).fetchone()
        assert row[0] == "approved"

    def test_reject_with_note(self, populated_db: sqlite3.Connection) -> None:
        ids = _seed_two_refs(populated_db)
        deps = make_deps(populated_db, StubBackend())
        out = _handle_reference_update(
            deps,
            ids["plato_to_aristotle"],
            {"curator_status": "rejected", "curator_note": "  false positive  "},
        )
        assert out["curator_status"] == "rejected"
        # The handler trims whitespace and persists the note
        row = populated_db.execute(
            "SELECT curator_note FROM cross_references WHERE id=?",
            (ids["plato_to_aristotle"],),
        ).fetchone()
        assert row[0] == "false positive"

    def test_invalid_status_rejected(self, populated_db: sqlite3.Connection) -> None:
        ids = _seed_two_refs(populated_db)
        deps = make_deps(populated_db, StubBackend())
        with pytest.raises(_HTTPError) as exc_info:
            _handle_reference_update(
                deps,
                ids["plato_to_aristotle"],
                {"curator_status": "haunted"},
            )
        assert exc_info.value.status == 400

    def test_missing_status_rejected(self, populated_db: sqlite3.Connection) -> None:
        ids = _seed_two_refs(populated_db)
        deps = make_deps(populated_db, StubBackend())
        with pytest.raises(_HTTPError) as exc_info:
            _handle_reference_update(deps, ids["plato_to_aristotle"], {})
        assert exc_info.value.status == 400

    def test_unknown_id_returns_404(self, populated_db: sqlite3.Connection) -> None:
        deps = make_deps(populated_db, StubBackend())
        with pytest.raises(_HTTPError) as exc_info:
            _handle_reference_update(
                deps,
                999_999,
                {"curator_status": "approved"},
            )
        assert exc_info.value.status == 404
