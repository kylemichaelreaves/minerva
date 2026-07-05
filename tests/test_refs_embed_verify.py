"""Unit tests for `minerva.refs.embed_verify`.

PASS A (`verify_quoted_references`):
    promote / reject / mid-band-unchanged paths, plus the
    skipped-no-target and skipped-no-embedding bookkeeping.

PASS B (`find_cross_author_allusions`):
    matrix-product sweep emits cross-author candidates above the
    cosine threshold; orthogonal vectors yield nothing.

Both paths run against `populated_db` (Plato + Aristotle chunks) with
hand-seeded embeddings, so cosine outcomes are deterministic.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

import numpy as np
import pytest

from minerva.refs import embed_verify
from minerva.refs import rules as refs_rules
from minerva.refs import schema as refs_schema

# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════


class FakeEmbedder:
    """Tiny stand-in for `embed.Embedder`. Maps each phrase to a
    pre-registered vector; unknown phrases return a zero vector so the
    cosine product is 0 (which lands in the reject band).

    Vectors must be L2-normalized — embed_verify assumes the same
    invariant the real Embedder produces.
    """

    def __init__(self, table: dict[str, np.ndarray]) -> None:
        self._table = {k: v.astype(np.float32) for k, v in table.items()}

    def encode(self, phrases: Iterable[str], **_: object) -> np.ndarray:
        phrases = list(phrases)
        if not phrases:
            return np.zeros((0, 4), dtype=np.float32)
        out = np.stack(
            [self._table.get(p, np.zeros(4, dtype=np.float32)) for p in phrases]
        )
        return out.astype(np.float32)


def _norm(v: list[float]) -> np.ndarray:
    arr = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(arr))
    return arr / n if n else arr


def _seed_embeddings(
    conn: sqlite3.Connection, chunk_vectors: dict[str, np.ndarray]
) -> None:
    """Write embeddings directly to the embeddings table. Bypasses
    `store.upsert_embeddings` because we want bespoke vectors and the
    upsert helper would coerce the dim through model metadata."""

    conn.executemany(
        "INSERT OR REPLACE INTO embeddings(chunk_id, model, dim, vector) "
        "VALUES (?, ?, ?, ?)",
        [
            (cid, "fake", int(v.shape[0]), v.astype(np.float32).tobytes())
            for cid, v in chunk_vectors.items()
        ],
    )
    conn.commit()


# Lock in convenient vectors. All L2-normalized.
V_X = _norm([1, 0, 0, 0])
V_Y = _norm([0, 1, 0, 0])
V_Z = _norm([0, 0, 1, 0])
V_MID = _norm([0.7, 0.7, 0, 0])  # cosine 0.7 with V_X — sits in mid band


# ════════════════════════════════════════════════════════════════════
# Pass A — verify_quoted_references
# ════════════════════════════════════════════════════════════════════


class TestVerifyQuotedReferences:
    def test_promote_when_cosine_above_threshold(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # Seed: target chunk ne-1097b's embedding == V_X; phrase
        # embedding also V_X → cosine 1.0 → promote.
        _seed_embeddings(populated_db, {"ne-1097b": V_X})
        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="Nicomachean Ethics",
        )
        xref_id = refs_schema.insert_cross_reference(
            populated_db,
            source_chunk_id="rep-509d",
            target_id=target.id,
            target_chunk_id="ne-1097b",
            reference_type="quotes",
            source_form_snapshot="Aristoteles",
            quoted_phrase="the function of the good",
            confidence=0.55,
            source_method="rule_weak",
            curator_status="auto",
        )
        populated_db.commit()

        embedder = FakeEmbedder({"the function of the good": V_X})
        stats = embed_verify.verify_quoted_references(populated_db, embedder)

        assert stats.examined == 1
        assert stats.promoted == 1
        assert stats.rejected == 0

        row = populated_db.execute(
            "SELECT confidence, source_method, target_chunk_id, curator_status "
            "FROM cross_references WHERE id = ?",
            (xref_id,),
        ).fetchone()
        assert row[0] == pytest.approx(1.0)
        assert row[1] == "rule+embed"
        assert row[2] == "ne-1097b"  # already set; preserved
        assert row[3] == "auto"  # promote does NOT touch curator_status

    def test_reject_when_cosine_below_threshold(
        self, populated_db: sqlite3.Connection
    ) -> None:
        _seed_embeddings(populated_db, {"ne-1097b": V_X})
        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="Nicomachean Ethics",
        )
        xref_id = refs_schema.insert_cross_reference(
            populated_db,
            source_chunk_id="rep-509d",
            target_id=target.id,
            target_chunk_id="ne-1097b",
            reference_type="quotes",
            source_form_snapshot="Aristoteles",
            quoted_phrase="something entirely unrelated",
            confidence=0.55,
            source_method="rule_weak",
            curator_status="auto",
        )
        populated_db.commit()

        # Phrase encodes orthogonal to target → cosine 0 → reject.
        embedder = FakeEmbedder({"something entirely unrelated": V_Z})
        stats = embed_verify.verify_quoted_references(populated_db, embedder)

        assert stats.rejected == 1
        row = populated_db.execute(
            "SELECT curator_status, source_method FROM cross_references WHERE id = ?",
            (xref_id,),
        ).fetchone()
        assert row[0] == "rejected"
        assert row[1] == "rule+embed"

    def test_mid_band_left_untouched(
        self, populated_db: sqlite3.Connection
    ) -> None:
        _seed_embeddings(populated_db, {"ne-1097b": V_X})
        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="Nicomachean Ethics",
        )
        xref_id = refs_schema.insert_cross_reference(
            populated_db,
            source_chunk_id="rep-509d",
            target_id=target.id,
            target_chunk_id="ne-1097b",
            reference_type="quotes",
            source_form_snapshot="Aristoteles",
            quoted_phrase="midband phrase",
            confidence=0.55,
            source_method="rule_weak",
            curator_status="auto",
        )
        populated_db.commit()

        # Cosine of V_MID @ V_X = 0.7 — between reject (0.5) and promote (0.8).
        embedder = FakeEmbedder({"midband phrase": V_MID})
        stats = embed_verify.verify_quoted_references(populated_db, embedder)

        assert stats.examined == 1
        assert stats.promoted == 0
        assert stats.rejected == 0
        row = populated_db.execute(
            "SELECT confidence, source_method, curator_status "
            "FROM cross_references WHERE id = ?",
            (xref_id,),
        ).fetchone()
        assert row[1] == "rule_weak"  # unchanged
        assert row[2] == "auto"

    def test_skip_no_target_when_out_of_corpus(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # Out-of-corpus target: ensure_target with an author/work that
        # doesn't match a `works` row leaves in_corpus_work_id NULL.
        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Cicero",  # not in populated_db's works
            canonical_work="De Officiis",
        )
        assert target.in_corpus_work_id is None
        refs_schema.insert_cross_reference(
            populated_db,
            source_chunk_id="rep-509d",
            target_id=target.id,
            target_chunk_id=None,
            reference_type="quotes",
            source_form_snapshot=None,
            quoted_phrase="orphan phrase",
            confidence=0.55,
            source_method="rule_weak",
            curator_status="auto",
        )
        populated_db.commit()

        embedder = FakeEmbedder({"orphan phrase": V_X})
        stats = embed_verify.verify_quoted_references(populated_db, embedder)

        assert stats.skipped_no_target == 1
        assert stats.promoted == 0
        assert stats.rejected == 0

    def test_skip_no_embedding_for_pinned_target(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # target_chunk_id is set but the target has no embedding row.
        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="Nicomachean Ethics",
        )
        refs_schema.insert_cross_reference(
            populated_db,
            source_chunk_id="rep-509d",
            target_id=target.id,
            target_chunk_id="ne-1097b",
            reference_type="quotes",
            source_form_snapshot=None,
            quoted_phrase="no embedding for target",
            confidence=0.55,
            source_method="rule_weak",
            curator_status="auto",
        )
        populated_db.commit()

        # Note: no _seed_embeddings call.
        embedder = FakeEmbedder({"no embedding for target": V_X})
        stats = embed_verify.verify_quoted_references(populated_db, embedder)

        assert stats.skipped_no_embedding == 1
        assert stats.promoted == 0

    def test_manual_rows_not_examined(
        self, populated_db: sqlite3.Connection
    ) -> None:
        _seed_embeddings(populated_db, {"ne-1097b": V_X})
        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="Nicomachean Ethics",
        )
        # curator_status='manual' should be skipped — embed verify
        # filters to curator_status='auto' only.
        refs_schema.insert_cross_reference(
            populated_db,
            source_chunk_id="rep-509d",
            target_id=target.id,
            target_chunk_id="ne-1097b",
            reference_type="quotes",
            source_form_snapshot=None,
            quoted_phrase="manual row",
            confidence=1.0,
            source_method="manual",
            curator_status="manual",
        )
        populated_db.commit()

        embedder = FakeEmbedder({"manual row": V_X})
        stats = embed_verify.verify_quoted_references(populated_db, embedder)
        assert stats.examined == 0


# ════════════════════════════════════════════════════════════════════
# Pass B — find_cross_author_allusions
# ════════════════════════════════════════════════════════════════════


class TestFindCrossAuthorAllusions:
    def test_emits_alludes_when_pair_above_threshold(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # Plato chunk rep-509d ≈ Aristotle chunk ne-1097b (both V_X).
        # Other chunks orthogonal so only the one near-pair survives.
        _seed_embeddings(
            populated_db,
            {
                "rep-509d": V_X,
                "rep-510a": V_Y,
                "rep-514a": V_Z,
                "phaedo-72e": V_Y,
                "ne-1097b": V_X,
            },
        )

        stats = embed_verify.find_cross_author_allusions(
            populated_db,
            pairs=(("Plato", "Aristotle"),),
            min_cosine=0.85,
            top_k=1,
            min_chunk_chars=0,
        )

        assert stats.pairs_examined == 1
        assert stats.candidates_inserted == 1
        # The new row has reference_type='alludes', source_method='embed_only',
        # and the high-cosine target_chunk_id pinned.
        rows = populated_db.execute(
            "SELECT source_chunk_id, target_chunk_id, reference_type, "
            "       source_method, curator_status "
            "FROM cross_references "
            "WHERE source_method = 'embed_only'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "rep-509d"
        assert rows[0][1] == "ne-1097b"
        assert rows[0][2] == "alludes"
        assert rows[0][4] == "auto"

    def test_no_emit_when_all_below_threshold(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # All Plato chunks orthogonal to the Aristotle chunk → no emits.
        _seed_embeddings(
            populated_db,
            {
                "rep-509d": V_Y,
                "rep-510a": V_Y,
                "rep-514a": V_Z,
                "phaedo-72e": V_Z,
                "ne-1097b": V_X,
            },
        )

        stats = embed_verify.find_cross_author_allusions(
            populated_db,
            pairs=(("Plato", "Aristotle"),),
            min_cosine=0.85,
            top_k=1,
            min_chunk_chars=0,
        )
        assert stats.candidates_inserted == 0
        assert stats.candidates_emitted == 0

    def test_missing_embeddings_skips_pair_silently(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # No embeddings at all → both author matrices are empty → pair
        # silently skipped (pairs_examined still ticks).
        stats = embed_verify.find_cross_author_allusions(
            populated_db,
            pairs=(("Plato", "Aristotle"),),
            min_cosine=0.85,
            top_k=1,
            min_chunk_chars=0,
        )
        assert stats.pairs_examined == 1
        assert stats.candidates_emitted == 0
        assert stats.candidates_inserted == 0


# ════════════════════════════════════════════════════════════════════
# Regression: Pass A must not re-process already-verified rows (#43)
# ════════════════════════════════════════════════════════════════════


class TestPassASkipsAlreadyProcessedRows:
    """An earlier ``source_method LIKE 'rule_%'`` filter also matched
    ``rule+embed`` and ``rule+embed+llm`` (SQLite ``_`` is a single-char
    wildcard), so re-runs re-processed promoted / LLM-verified rows and
    clobbered the ``+llm`` provenance. The filter must select only the
    exact rules-stamped methods."""

    def test_rule_embed_and_llm_rows_are_not_examined(
        self, populated_db: sqlite3.Connection
    ) -> None:
        _seed_embeddings(populated_db, {"ne-1097b": V_X})
        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="Nicomachean Ethics",
        )
        # Two auto rows that a prior verification pass already produced,
        # each with a quoted_phrase and a high-cosine target — the only
        # thing keeping them out of Pass A is the source_method filter.
        for method, phrase in (
            ("rule+embed", "already promoted phrase"),
            ("rule+embed+llm", "already llm-verified phrase"),
        ):
            refs_schema.insert_cross_reference(
                populated_db,
                source_chunk_id="rep-509d",
                target_id=target.id,
                target_chunk_id="ne-1097b",
                reference_type="quotes",
                source_form_snapshot=None,
                quoted_phrase=phrase,
                confidence=0.9,
                source_method=method,
                curator_status="auto",
            )
        populated_db.commit()

        embedder = FakeEmbedder(
            {
                "already promoted phrase": V_X,
                "already llm-verified phrase": V_X,
            }
        )
        stats = embed_verify.verify_quoted_references(populated_db, embedder)

        # Neither row is a candidate → nothing examined, nothing changed.
        assert stats.examined == 0
        methods = {
            r[0]
            for r in populated_db.execute(
                "SELECT source_method FROM cross_references"
            ).fetchall()
        }
        assert "rule+embed+llm" in methods  # provenance preserved
        assert "rule+embed" in methods


# ════════════════════════════════════════════════════════════════════
# Regression: allusion dedup keeps distinct target chunks (#44)
# ════════════════════════════════════════════════════════════════════


class TestInsertCandidateAllusionDedup:
    """Author-level allusion candidates share target_id / reference_type
    / NULL form / NULL phrase and differ only by ``target_chunk_id``.
    The dedup key must include ``target_chunk_id`` or the top-k matches
    for one source chunk collapse to a single row."""

    def _allusion(self, target_chunk_id: str) -> refs_rules.Candidate:
        return refs_rules.Candidate(
            source_chunk_id="rep-509d",
            source_span_start=None,
            source_span_end=None,
            source_form_snapshot=None,
            target_author="Aristotle",
            target_work="",
            target_locator=None,
            reference_type="alludes",
            confidence=0.9,
            source_method="embed_only",
            quoted_phrase=None,
            target_chunk_id=target_chunk_id,
        )

    def test_distinct_target_chunks_each_insert(
        self, populated_db: sqlite3.Connection
    ) -> None:
        id1 = refs_rules.insert_candidate(populated_db, self._allusion("ne-1097b"))
        id2 = refs_rules.insert_candidate(populated_db, self._allusion("phaedo-72e"))
        assert id1 is not None
        assert id2 is not None
        assert id1 != id2

        # Re-inserting an identical candidate (same target_chunk_id) still dedups.
        dup = refs_rules.insert_candidate(populated_db, self._allusion("ne-1097b"))
        assert dup is None

        n = populated_db.execute(
            "SELECT COUNT(*) FROM cross_references WHERE reference_type = 'alludes'"
        ).fetchone()[0]
        assert n == 2
