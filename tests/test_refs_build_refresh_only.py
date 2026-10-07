"""`refs build --refresh-only` (#518, #715): the live backfill.

The next ordinary `refs build` would not apply the refresh — `rules_hash`
fingerprints the rules, not `insert_candidate`, so every affected chunk is
"current" — and `--rescan-all` would also insert #801's duplicates. This
mode rescans the scope, refreshes matched rows, and inserts nothing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from minerva.cli import build_parser
from minerva.cli.refs.build import cmd_refs_build
from minerva.refs import rules as refs_rules


def _cand(chunk_id: str, *, conf: float, method: str) -> refs_rules.Candidate:
    return refs_rules.Candidate(
        source_chunk_id=chunk_id,
        source_span_start=None,
        source_span_end=None,
        source_form_snapshot="Aristoteles",
        target_author="Aristotle",
        target_work="Nicomachean Ethics",
        target_locator=None,
        reference_type="cites",
        confidence=conf,
        source_method=method,
    )


@pytest.fixture
def stubbed(populated_db: sqlite3.Connection, monkeypatch) -> sqlite3.Connection:
    # Seed the drifted row, then make "today's rule" emit it at a new tier
    # for rep-509d and a brand-new candidate for rep-510a.
    refs_rules.insert_candidate(populated_db, _cand("rep-509d", conf=0.9, method="rule_strong"))
    populated_db.commit()
    monkeypatch.setattr(refs_rules, "_rules_for_author", lambda author: ("stub",))
    monkeypatch.setattr(
        refs_rules,
        "apply_rules_to_chunk",
        lambda chunk: {
            "rep-509d": [_cand("rep-509d", conf=0.65, method="rule_weak")],
            "rep-510a": [_cand("rep-510a", conf=0.65, method="rule_weak")],
        }.get(chunk.chunk_id, []),
    )
    return populated_db


def _run(db_path: Path, *extra: str) -> int:
    args = build_parser().parse_args(
        ["refs", "build", "--db", str(db_path), "--source-author", "Plato", *extra]
    )
    return cmd_refs_build(args)


def test_refresh_only_refreshes_and_inserts_nothing(stubbed, db_path, capsys) -> None:
    assert _run(db_path, "--refresh-only") == 0
    rows = stubbed.execute(
        "SELECT source_chunk_id, confidence, source_method FROM cross_references"
    ).fetchall()
    assert [tuple(r) for r in rows] == [("rep-509d", 0.65, "rule_weak")]
    out = capsys.readouterr().out
    assert "1 refreshed" in out and "0 new rows" in out


def test_refresh_only_ignores_the_scan_state_cache_and_leaves_it_alone(stubbed, db_path) -> None:
    # An ordinary build records every chunk as current; a refresh-only run
    # after it must still visit them, and must not write scan state.
    assert _run(db_path) == 0
    stubbed.execute("UPDATE cross_references SET confidence = 0.9, source_method = 'rule_strong'")
    stubbed.commit()
    before = [tuple(r) for r in stubbed.execute("SELECT * FROM refs_scan_state ORDER BY chunk_id")]
    assert _run(db_path, "--refresh-only") == 0
    assert {
        r[0]: tuple(r[1:])
        for r in stubbed.execute(
            "SELECT source_chunk_id, confidence, source_method FROM cross_references"
        )
    } == {"rep-509d": (0.65, "rule_weak"), "rep-510a": (0.65, "rule_weak")}
    assert [
        tuple(r) for r in stubbed.execute("SELECT * FROM refs_scan_state ORDER BY chunk_id")
    ] == before


def test_refresh_only_is_a_rules_flag(db_path, capsys) -> None:
    args = build_parser().parse_args(
        ["refs", "build", "--db", str(db_path), "--strategy", "llm-verify", "--refresh-only"]
    )
    assert cmd_refs_build(args) == 2
    assert "--refresh-only" in capsys.readouterr().err
