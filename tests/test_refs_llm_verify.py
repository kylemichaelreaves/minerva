"""Unit tests for `minerva.refs.llm_verify`.

Covers:
* `_parse_verdicts` robustness — plain JSON, fenced JSON, prose-prefixed
  JSON, salvage failure.
* `verify_rows_with_llm` end-to-end — promote / reject / unchanged /
  missing-verdict paths, the eligibility SQL filter (skip_strong,
  skip_short_chunks), the `max_llm_calls` budget cap, and LLM-error
  handling.

Uses a small `SequenceStubBackend` that pops canned replies per call so
we can exercise multi-batch sequences without touching a real LLM.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from minerva import llm
from minerva.refs import llm_verify
from minerva.refs import schema as refs_schema
from minerva.refs.llm_verify import _parse_verdicts

# ════════════════════════════════════════════════════════════════════
# Backend helpers
# ════════════════════════════════════════════════════════════════════


class SequenceStubBackend(llm.LLMBackend):
    """Returns a different reply per `complete` call. Mix str (success
    reply) and `llm.LLMError` (raises) entries to simulate transient
    backend failures."""

    def __init__(self, replies: Sequence[str | llm.LLMError]) -> None:
        self._replies = list(replies)
        self.call_count = 0
        self.name = "seq-stub"

    def complete(
        self, messages: list[llm.Message], *, temperature: float = 0.2
    ) -> str:
        self.call_count += 1
        if not self._replies:
            raise RuntimeError("SequenceStubBackend ran out of replies")
        nxt = self._replies.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


def _verdict_json(*, row_id: int, references: bool, **extra: object) -> str:
    body = {
        "id": row_id,
        "references": references,
        "type": "cites",
        "confidence": 0.9,
        "notes": "stub note",
    }
    body.update(extra)
    return json.dumps([body])


def _verdicts_json(row_ids: Sequence[int], *, references: bool = True) -> str:
    """One verdict object per id — the multi-row reply shape."""
    return json.dumps(
        [
            {
                "id": rid,
                "references": references,
                "type": "cites",
                "confidence": 0.9,
                "notes": "stub note",
            }
            for rid in row_ids
        ]
    )


# ════════════════════════════════════════════════════════════════════
# Helpers to seed cross-references
# ════════════════════════════════════════════════════════════════════


def _seed_auto_row(
    conn: sqlite3.Connection,
    *,
    source_chunk_id: str = "rep-509d",
    target_chunk_id: str | None = "ne-1097b",
    source_method: str = "rule_weak",
    confidence: float = 0.6,
    reference_type: str = "cites",
) -> int:
    target = refs_schema.ensure_target(
        conn,
        canonical_author="Aristotle",
        canonical_work="Nicomachean Ethics",
    )
    rid = refs_schema.insert_cross_reference(
        conn,
        source_chunk_id=source_chunk_id,
        target_id=target.id,
        target_chunk_id=target_chunk_id,
        reference_type=reference_type,
        source_form_snapshot="Aristoteles",
        confidence=confidence,
        source_method=source_method,
        curator_status="auto",
    )
    conn.commit()
    return rid


def _seed_rows(conn: sqlite3.Connection, n: int) -> list[int]:
    """Seed `n` eligible auto rows, each on a distinct source chunk so
    the UNIQUE (source, target, form) dedup doesn't collapse them."""
    sources = ("rep-509d", "rep-510a", "rep-514a", "phaedo-72e", "ne-1097b", "hegel-p17")
    assert n <= len(sources), "populated_db has only 6 chunks"
    target = refs_schema.ensure_target(
        conn,
        canonical_author="Aristotle",
        canonical_work="Nicomachean Ethics",
    )
    ids = [
        refs_schema.insert_cross_reference(
            conn,
            source_chunk_id=src,
            target_id=target.id,
            reference_type="cites",
            source_form_snapshot=f"surface_{i}",
            confidence=0.6,
            source_method="rule_weak",
            curator_status="auto",
        )
        for i, src in enumerate(sources[:n])
    ]
    conn.commit()
    return ids


# ════════════════════════════════════════════════════════════════════
# _parse_verdicts robustness
# ════════════════════════════════════════════════════════════════════


class TestParseVerdicts:
    def test_plain_json_array(self) -> None:
        out = _parse_verdicts('[{"id": 1, "references": true}]')
        assert out == [{"id": 1, "references": True}]

    def test_fenced_json_block(self) -> None:
        raw = "```json\n[{\"id\": 1, \"references\": false}]\n```"
        out = _parse_verdicts(raw)
        assert out == [{"id": 1, "references": False}]

    def test_prose_prefixed_json_salvage(self) -> None:
        # Some models prepend "Here is the JSON:" before the actual array.
        raw = 'Sure! Here you go:\n[{"id": 7, "references": true, "type": "cites"}]'
        out = _parse_verdicts(raw)
        assert out is not None
        assert out[0]["id"] == 7

    def test_unparseable_returns_none(self) -> None:
        assert _parse_verdicts("not json at all") is None

    def test_non_array_root_returns_none(self) -> None:
        # A bare object isn't the spec; we want None so the caller
        # counts it as a parse_error and skips the batch.
        assert _parse_verdicts('{"id": 1, "references": true}') is None


# ════════════════════════════════════════════════════════════════════
# verify_rows_with_llm — end-to-end paths
# ════════════════════════════════════════════════════════════════════


class TestVerifyRowsPromote:
    def test_promote_path_updates_confidence_type_and_method(
        self, populated_db: sqlite3.Connection
    ) -> None:
        rid = _seed_auto_row(populated_db, confidence=0.6)
        backend = SequenceStubBackend(
            [
                _verdict_json(
                    row_id=rid,
                    references=True,
                    type="paraphrases",
                    confidence=0.9,
                    notes="strong paraphrase",
                )
            ]
        )

        stats = llm_verify.verify_rows_with_llm(
            populated_db, backend, batch_size=10, max_llm_calls=5, skip_short_chunks=False
        )

        assert stats.examined == 1
        assert stats.promoted == 1
        assert stats.rejected == 0
        row = populated_db.execute(
            "SELECT confidence, reference_type, source_method, curator_status, "
            "       curator_note "
            "FROM cross_references WHERE id = ?",
            (rid,),
        ).fetchone()
        assert row[0] == pytest.approx(0.9)
        assert row[1] == "paraphrases"
        assert row[2] == "rule+embed+llm"
        assert row[3] == "auto"  # curator still decides
        assert row[4] == "strong paraphrase"

    def test_invalid_type_falls_back_to_existing(
        self, populated_db: sqlite3.Connection
    ) -> None:
        rid = _seed_auto_row(populated_db, reference_type="quotes")
        # LLM returns a type that's not in the allowed enum — coerce
        # back to the row's existing type to keep the CHECK happy.
        backend = SequenceStubBackend(
            [_verdict_json(row_id=rid, references=True, type="bogus_type")]
        )

        llm_verify.verify_rows_with_llm(
            populated_db, backend, max_llm_calls=5, skip_short_chunks=False
        )
        row = populated_db.execute(
            "SELECT reference_type FROM cross_references WHERE id = ?", (rid,)
        ).fetchone()
        assert row[0] == "quotes"

    def test_confidence_never_decreases(
        self, populated_db: sqlite3.Connection
    ) -> None:
        rid = _seed_auto_row(populated_db, confidence=0.95)
        # LLM returns a lower confidence — promote should preserve the
        # higher of (current, llm).
        backend = SequenceStubBackend(
            [_verdict_json(row_id=rid, references=True, confidence=0.7)]
        )
        llm_verify.verify_rows_with_llm(
            populated_db, backend, max_llm_calls=5, skip_short_chunks=False
        )
        row = populated_db.execute(
            "SELECT confidence FROM cross_references WHERE id = ?", (rid,)
        ).fetchone()
        assert row[0] == pytest.approx(0.95)


    def test_non_numeric_confidence_keeps_the_row_value(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # The model occasionally answers with a word instead of a
        # number. That must not abort the batch — the verdict still
        # counts, the row just keeps its own confidence.
        rid = _seed_auto_row(populated_db, confidence=0.6)
        backend = SequenceStubBackend(
            [_verdict_json(row_id=rid, references=True, confidence="high")]
        )

        stats = llm_verify.verify_rows_with_llm(
            populated_db, backend, max_llm_calls=5, skip_short_chunks=False
        )

        assert stats.promoted == 1
        row = populated_db.execute(
            "SELECT confidence FROM cross_references WHERE id = ?", (rid,)
        ).fetchone()
        assert row[0] == pytest.approx(0.6)


class TestVerifyRowsReject:
    def test_reject_path_marks_status_and_writes_note(
        self, populated_db: sqlite3.Connection
    ) -> None:
        rid = _seed_auto_row(populated_db)
        backend = SequenceStubBackend(
            [
                _verdict_json(
                    row_id=rid, references=False, notes="false positive — name match only"
                )
            ]
        )
        stats = llm_verify.verify_rows_with_llm(
            populated_db, backend, max_llm_calls=5, skip_short_chunks=False
        )
        assert stats.rejected == 1
        row = populated_db.execute(
            "SELECT curator_status, source_method, curator_note "
            "FROM cross_references WHERE id = ?",
            (rid,),
        ).fetchone()
        assert row[0] == "rejected"
        assert row[1] == "rule+embed+llm"
        assert row[2] == "false positive — name match only"


class TestEligibilityFilter:
    def test_rule_strong_rows_skipped_by_default(
        self, populated_db: sqlite3.Connection
    ) -> None:
        _seed_auto_row(populated_db, source_method="rule_strong")
        # No backend calls expected.
        backend = SequenceStubBackend([])
        stats = llm_verify.verify_rows_with_llm(
            populated_db, backend, max_llm_calls=5, skip_short_chunks=False
        )
        assert stats.examined == 0
        assert backend.call_count == 0

    def test_rule_strong_can_be_opted_in(
        self, populated_db: sqlite3.Connection
    ) -> None:
        rid = _seed_auto_row(populated_db, source_method="rule_strong")
        backend = SequenceStubBackend(
            [_verdict_json(row_id=rid, references=True)]
        )
        stats = llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            max_llm_calls=5,
            skip_strong=False,
            skip_short_chunks=False,
        )
        assert stats.examined == 1
        assert stats.promoted == 1

    def test_already_llm_verified_rows_skipped(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # Re-running the verifier shouldn't re-process rows already
        # tagged with `rule+embed+llm`.
        _seed_auto_row(populated_db, source_method="rule+embed+llm")
        backend = SequenceStubBackend([])
        stats = llm_verify.verify_rows_with_llm(
            populated_db, backend, max_llm_calls=5, skip_short_chunks=False
        )
        assert stats.examined == 0


class TestBudgetAndErrorHandling:
    def test_max_llm_calls_caps_examined(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # Seed 3 rows; cap budget to 1 call with batch_size=1 → only 1 examined.
        # Each row needs a distinct (source, target, form) so the dedup
        # in insert_cross_reference doesn't collide via UNIQUE constraints.
        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="Nicomachean Ethics",
        )
        ids: list[int] = []
        for i, src in enumerate(("rep-509d", "rep-510a", "phaedo-72e")):
            ids.append(
                refs_schema.insert_cross_reference(
                    populated_db,
                    source_chunk_id=src,
                    target_id=target.id,
                    reference_type="cites",
                    source_form_snapshot=f"surface_{i}",
                    confidence=0.6,
                    source_method="rule_weak",
                    curator_status="auto",
                )
            )
        populated_db.commit()

        # Budget = 1 call → only the first row examined.
        backend = SequenceStubBackend(
            [_verdict_json(row_id=ids[0], references=True)]
        )
        stats = llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            batch_size=1,
            max_llm_calls=1,
            skip_short_chunks=False,
        )
        assert stats.llm_calls == 1
        assert stats.examined == 1

    def test_llm_error_counted_and_processing_continues(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # Two rows in two batches; first call raises LLMError, second
        # promotes. Stats should record one parse_error + one promote.
        # Distinct surface forms so the inserts don't collide.
        target = refs_schema.ensure_target(
            populated_db,
            canonical_author="Aristotle",
            canonical_work="Nicomachean Ethics",
        )
        ids: list[int] = []
        for i, src in enumerate(("rep-509d", "rep-510a")):
            ids.append(
                refs_schema.insert_cross_reference(
                    populated_db,
                    source_chunk_id=src,
                    target_id=target.id,
                    reference_type="cites",
                    source_form_snapshot=f"surface_{i}",
                    confidence=0.6,
                    source_method="rule_weak",
                    curator_status="auto",
                )
            )
        populated_db.commit()

        backend = SequenceStubBackend(
            [
                llm.LLMError("transient 503"),
                _verdict_json(row_id=ids[1], references=True),
            ]
        )
        stats = llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            batch_size=1,
            max_llm_calls=5,
            skip_short_chunks=False,
            max_backend_retries=0,
        )
        # A transport failure is not a malformed response (#272). The two
        # call for opposite operator responses, so they cannot share a
        # counter — this used to assert `parse_errors == 1`.
        assert stats.backend_errors == 1
        assert stats.parse_errors == 0
        assert stats.promoted == 1
        # Checkpoint must not leap past the first (failed) row — resume
        # would otherwise skip ids[0] forever.
        assert llm_verify._read_checkpoint(populated_db) is None

    def test_unparseable_response_is_not_counted_as_a_backend_error(
        self, populated_db: sqlite3.Connection
    ) -> None:
        """The other half of the split: a reply that arrived and would
        not parse must not inflate `backend_errors`."""

        _seed_auto_row(populated_db)
        backend = SequenceStubBackend(["garbage from the model"])
        stats = llm_verify.verify_rows_with_llm(
            populated_db, backend, max_llm_calls=5, skip_short_chunks=False
        )
        assert stats.parse_errors == 1
        assert stats.backend_errors == 0

    def test_backend_error_is_retried_with_the_same_payload(
        self, populated_db: sqlite3.Connection
    ) -> None:
        """A 503 says nothing about the payload, so the unit is re-sent
        unchanged — unlike a parse failure, which is halved (#270)."""

        rid = _seed_auto_row(populated_db)
        backend = SequenceStubBackend(
            [
                llm.LLMError("transient 503"),
                _verdict_json(row_id=rid, references=True),
            ]
        )
        stats = llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            max_llm_calls=5,
            skip_short_chunks=False,
            backend_retry_backoff=0.0,
        )
        assert stats.promoted == 1
        assert stats.lost_rows == 0, "the retry should have saved the row"
        assert stats.backend_errors == 1
        assert stats.llm_calls == 2

    def test_backend_retries_are_bounded_and_the_unit_is_then_lost(
        self, populated_db: sqlite3.Connection
    ) -> None:
        """An outage must not spin. After the bound, the unit is given up
        on and held back from the checkpoint so a re-run finds it."""

        _seed_auto_row(populated_db)
        backend = SequenceStubBackend([llm.LLMError("down") for _ in range(10)])
        stats = llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            max_llm_calls=20,
            skip_short_chunks=False,
            max_backend_retries=2,
            backend_retry_backoff=0.0,
        )
        # One initial attempt plus two retries.
        assert stats.llm_calls == 3
        assert stats.backend_errors == 3
        assert stats.lost_rows == 1
        assert llm_verify._read_checkpoint(populated_db) is None

    def test_backend_retries_back_off_between_attempts(
        self, populated_db: sqlite3.Connection
    ) -> None:
        """`sleep_between_calls` is fixed pacing, not backoff. Re-sending
        into a rate limit at the same cadence is what backoff exists to
        avoid, so the pause has to widen."""

        _seed_auto_row(populated_db)
        backend = SequenceStubBackend([llm.LLMError("down") for _ in range(10)])
        base = 0.02

        started = time.monotonic()
        llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            max_llm_calls=20,
            skip_short_chunks=False,
            max_backend_retries=2,
            backend_retry_backoff=base,
        )
        elapsed = time.monotonic() - started

        # Doubling: base before retry 1, 2*base before retry 2.
        assert elapsed >= 3 * base

    def test_verbose_names_the_backend_error_and_the_attempt(
        self, populated_db: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A retry that is silent looks like a stall. The operator needs
        to see the reason and how many attempts remain."""

        _seed_auto_row(populated_db)
        backend = SequenceStubBackend([llm.LLMError("transient 503") for _ in range(3)])
        llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            max_llm_calls=10,
            skip_short_chunks=False,
            max_backend_retries=1,
            backend_retry_backoff=0.0,
            verbose=True,
        )

        out = capsys.readouterr().out
        assert "[backend_error]" in out
        assert "transient 503" in out
        assert "attempt 1 of 2" in out

    def test_retries_respect_the_call_budget(
        self, populated_db: sqlite3.Connection
    ) -> None:
        """Retries are ordinary API calls and are billed as such, or
        `--max-llm-calls` stops bounding what a run costs."""

        _seed_auto_row(populated_db)
        backend = SequenceStubBackend([llm.LLMError("down") for _ in range(10)])
        stats = llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            max_llm_calls=2,
            skip_short_chunks=False,
            max_backend_retries=5,
            backend_retry_backoff=0.0,
        )
        assert stats.llm_calls == 2

    def test_unparseable_response_counted_as_parse_error(
        self, populated_db: sqlite3.Connection
    ) -> None:
        rid = _seed_auto_row(populated_db)
        backend = SequenceStubBackend(["garbage from the model"])
        stats = llm_verify.verify_rows_with_llm(
            populated_db, backend, max_llm_calls=5, skip_short_chunks=False
        )
        assert stats.parse_errors == 1
        # Row left untouched.
        row = populated_db.execute(
            "SELECT source_method FROM cross_references WHERE id = ?", (rid,)
        ).fetchone()
        assert row[0] == "rule_weak"

    def test_missing_verdict_for_row_counts_missing(
        self, populated_db: sqlite3.Connection
    ) -> None:
        rid = _seed_auto_row(populated_db)
        # Response omits the row's id entirely.
        backend = SequenceStubBackend(['[{"id": 99999, "references": true}]'])
        stats = llm_verify.verify_rows_with_llm(
            populated_db, backend, max_llm_calls=5, skip_short_chunks=False
        )
        assert stats.missing_verdicts == 1
        row = populated_db.execute(
            "SELECT source_method FROM cross_references WHERE id = ?", (rid,)
        ).fetchone()
        assert row[0] == "rule_weak"


# ════════════════════════════════════════════════════════════════════
# skip_short_chunks — source-only floor (#265)
# ════════════════════════════════════════════════════════════════════


class TestShortChunkFilter:
    """The 80-char floor exists to drop section banners, whose
    embeddings collide at cosine≈1. That reasoning applies to the
    *source* chunk — the side the verifier reads context from. It does
    not apply to the *target*: a short cited passage is normal (42.6%
    of Quran verses and 26% of the Hebrew Bible are under 80 chars),
    and excluding them meant the most-cited corpora could never be
    verified as citation targets. See issue #265.
    """

    def test_short_target_is_eligible(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # ne-1097b is 69 chars — a plausible verse-length target.
        assert (
            populated_db.execute(
                "SELECT length(text) FROM chunks WHERE chunk_id = 'ne-1097b'"
            ).fetchone()[0]
            < 80
        )
        rid = _seed_auto_row(populated_db, target_chunk_id="ne-1097b")
        backend = SequenceStubBackend([_verdict_json(row_id=rid, references=True)])

        stats = llm_verify.verify_rows_with_llm(
            populated_db, backend, max_llm_calls=5, skip_short_chunks=True
        )

        assert stats.examined == 1

    def test_short_source_is_still_skipped(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # hegel-p17 is 41 chars — too little context to judge a citation.
        assert (
            populated_db.execute(
                "SELECT length(text) FROM chunks WHERE chunk_id = 'hegel-p17'"
            ).fetchone()[0]
            < 80
        )
        _seed_auto_row(populated_db, source_chunk_id="hegel-p17")
        backend = SequenceStubBackend([])

        stats = llm_verify.verify_rows_with_llm(
            populated_db, backend, max_llm_calls=5, skip_short_chunks=True
        )

        assert stats.examined == 0
        assert backend.call_count == 0

    def test_short_source_included_with_flag_off(
        self, populated_db: sqlite3.Connection
    ) -> None:
        rid = _seed_auto_row(populated_db, source_chunk_id="hegel-p17")
        backend = SequenceStubBackend([_verdict_json(row_id=rid, references=True)])

        stats = llm_verify.verify_rows_with_llm(
            populated_db, backend, max_llm_calls=5, skip_short_chunks=False
        )

        assert stats.examined == 1

    def test_sql_carries_no_target_length_clause(self) -> None:
        sql, _params = llm_verify._eligible_rows_sql(skip_short_chunks=True)
        assert "length(c.text) >= 80" in sql
        assert "tc.text" not in sql.split("WHERE", 1)[1]


# ════════════════════════════════════════════════════════════════════
# Parse-failure recovery — split-and-retry (#270)
# ════════════════════════════════════════════════════════════════════


class TestParseFailureRetry:
    """An unparseable response used to cost the whole batch: no retry,
    and the only record was a 200-char excerpt behind --verbose. A bad
    response is a property of the response, not of the rows — the #270
    batch re-ran clean at a smaller batch size — so a failed batch is
    re-issued as halves, and whatever still fails is named by row id.
    """

    def test_failed_batch_is_re_issued_as_halves(
        self, populated_db: sqlite3.Connection
    ) -> None:
        ids = _seed_rows(populated_db, 4)
        backend = SequenceStubBackend(
            [
                "unparseable slop",
                _verdicts_json(ids[:2]),
                _verdicts_json(ids[2:]),
            ]
        )

        stats = llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            batch_size=4,
            max_llm_calls=10,
            skip_short_chunks=False,
        )

        # All four rows recovered by the two half-batch calls.
        assert stats.examined == 4
        assert stats.promoted == 4
        assert stats.lost_rows == 0
        assert backend.call_count == 3

    def test_halves_split_again_until_single_rows(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # Depth-first, left to right: [a,b,c,d] → [a,b] → [a], [b] → [c,d].
        ids = _seed_rows(populated_db, 4)
        backend = SequenceStubBackend(
            [
                "slop",  # [a,b,c,d]
                "slop",  # [a,b]
                _verdicts_json([ids[0]]),  # [a]
                _verdicts_json([ids[1]]),  # [b]
                _verdicts_json(ids[2:]),  # [c,d]
            ]
        )

        stats = llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            batch_size=4,
            max_llm_calls=10,
            skip_short_chunks=False,
        )

        assert stats.examined == 4
        assert stats.lost_rows == 0
        assert backend.call_count == 5

    def test_single_row_that_cannot_parse_is_lost_and_named(
        self, populated_db: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ids = _seed_rows(populated_db, 2)
        # Every attempt fails: [a,b] → [a] → [b]. Nothing left to split.
        backend = SequenceStubBackend(["slop", "slop", "slop"])

        stats = llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            batch_size=2,
            max_llm_calls=10,
            skip_short_chunks=False,
        )

        assert stats.examined == 0
        assert stats.lost_rows == 2
        out = capsys.readouterr().out
        # The ids must be recoverable from the log without --verbose;
        # otherwise re-running the lost rows means re-deriving the
        # eligible set by hand.
        assert str(ids[0]) in out
        assert str(ids[1]) in out

    def test_recovered_batch_leaves_no_rows_lost_but_records_the_error(
        self, populated_db: sqlite3.Connection
    ) -> None:
        ids = _seed_rows(populated_db, 2)
        backend = SequenceStubBackend(
            ["slop", _verdicts_json([ids[0]]), _verdicts_json([ids[1]])]
        )

        stats = llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            batch_size=2,
            max_llm_calls=10,
            skip_short_chunks=False,
        )

        # The bad response still shows in parse_errors — the run saw one
        # — but it cost nothing.
        assert stats.parse_errors == 1
        assert stats.lost_rows == 0
        assert stats.examined == 2

    def test_retries_consume_the_call_budget(
        self, populated_db: sqlite3.Connection
    ) -> None:
        ids = _seed_rows(populated_db, 4)
        # Budget of 2: the failed full batch, then one half. The second
        # half never gets a call.
        backend = SequenceStubBackend(["slop", _verdicts_json(ids[:2])])

        stats = llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            batch_size=4,
            max_llm_calls=2,
            skip_short_chunks=False,
        )

        assert stats.llm_calls == 2
        assert backend.call_count == 2
        assert stats.examined == 2
        # Budget-stopped rows are not lost — the checkpoint stays behind
        # the failed batch so a --resume run re-reads them.
        assert llm_verify._read_checkpoint(populated_db) is None

    def test_checkpoint_advances_when_a_split_recovers_the_batch(
        self, populated_db: sqlite3.Connection
    ) -> None:
        ids = _seed_rows(populated_db, 2)
        backend = SequenceStubBackend(
            ["slop", _verdicts_json([ids[0]]), _verdicts_json([ids[1]])]
        )

        llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            batch_size=2,
            max_llm_calls=10,
            skip_short_chunks=False,
        )

        # Every row was examined, so resume may skip past them.
        assert llm_verify._read_checkpoint(populated_db) == ids[-1]

    def test_verbose_logs_the_whole_response_not_a_200_char_prefix(
        self, populated_db: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _seed_rows(populated_db, 1)
        # The part that explains the failure is past the old 200-char
        # cutoff — that is exactly what made the #270 response
        # undiagnosable after the run.
        response = "[" + ("x" * 400) + "TAIL_MARKER"
        backend = SequenceStubBackend([response])

        llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            batch_size=1,
            max_llm_calls=10,
            skip_short_chunks=False,
            verbose=True,
        )

        assert "TAIL_MARKER" in capsys.readouterr().out


class TestCallPacing:
    def test_sleep_between_calls_paces_every_call_including_retries(
        self, populated_db: sqlite3.Connection
    ) -> None:
        # The pacing knob is what keeps long runs under the provider's
        # rate limit, so it has to count retry calls too — they are
        # ordinary API calls. Three calls here: the failed batch, the
        # first half (backend error), the second half (verdict).
        # Backend retries are off so the subject stays the split retry;
        # their own backoff is paced separately (#272).
        ids = _seed_rows(populated_db, 2)
        backend = SequenceStubBackend(
            ["slop", llm.LLMError("transient 503"), _verdicts_json([ids[1]])]
        )
        pause = 0.02

        started = time.monotonic()
        stats = llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            batch_size=2,
            max_llm_calls=10,
            skip_short_chunks=False,
            sleep_between_calls=pause,
            max_backend_retries=0,
        )
        elapsed = time.monotonic() - started

        assert stats.llm_calls == 3
        assert elapsed >= 3 * pause


class TestVerdictDurability:
    """The per-batch `conn.commit()` used to live inside the checkpoint
    guard, so one failed batch stopped every *later* batch from
    committing. Since the CLI never commits after the run, the tail of
    a run that hit a single parse error was rolled back at process
    exit — verdicts reported as promoted, then silently discarded.
    Durability of the verdicts and the resume checkpoint are separate
    concerns; only the checkpoint may be held back.
    """

    def test_verdicts_after_a_failed_batch_are_committed(
        self, populated_db: sqlite3.Connection, db_path: Path
    ) -> None:
        ids = _seed_rows(populated_db, 2)
        backend = SequenceStubBackend(
            [llm.LLMError("transient 503"), _verdict_json(row_id=ids[1], references=True)]
        )

        stats = llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            batch_size=1,
            max_llm_calls=5,
            skip_short_chunks=False,
            max_backend_retries=0,
        )
        assert stats.promoted == 1

        # Read through a second connection: only committed rows are
        # visible there.
        other = sqlite3.connect(db_path)
        try:
            method = other.execute(
                "SELECT source_method FROM cross_references WHERE id = ?", (ids[1],)
            ).fetchone()[0]
        finally:
            other.close()
        assert method == "rule+embed+llm"

    def test_checkpoint_still_held_back_by_the_failed_batch(
        self, populated_db: sqlite3.Connection
    ) -> None:
        ids = _seed_rows(populated_db, 2)
        backend = SequenceStubBackend(
            [llm.LLMError("transient 503"), _verdict_json(row_id=ids[1], references=True)]
        )

        llm_verify.verify_rows_with_llm(
            populated_db,
            backend,
            batch_size=1,
            max_llm_calls=5,
            skip_short_chunks=False,
            max_backend_retries=0,
        )

        # Committing the verdicts must not advance resume past the row
        # the failed batch never examined.
        assert llm_verify._read_checkpoint(populated_db) is None
