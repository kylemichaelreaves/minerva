"""Tests for the Phase 0 instrumentation helpers — Timer, timed,
fmt_elapsed, record_timing. These power the ``--timing`` flag on
``minerva ingest`` (and other CLI commands as they're wired in).
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from minerva.cli._shared import Timer, fmt_elapsed, record_timing, timed


def test_timer_reports_nonneg_elapsed():
    with Timer() as t:
        # No-op block; just verify the timer doesn't return negative.
        pass
    assert t.elapsed >= 0


def test_timer_measures_real_work():
    with Timer() as t:
        time.sleep(0.05)
    # Loose lower bound — sleep is precise on most platforms; the
    # upper bound is generous to avoid CI flakes.
    assert 0.04 <= t.elapsed < 1.0


def test_fmt_elapsed_sub_minute():
    assert fmt_elapsed(0.1) == "0.10s"
    assert fmt_elapsed(12.345) == "12.35s"
    assert fmt_elapsed(59.99) == "59.99s"


def test_fmt_elapsed_over_minute():
    assert fmt_elapsed(60.0) == "1m 0.0s"
    assert fmt_elapsed(125.5) == "2m 5.5s"
    assert fmt_elapsed(3601.0) == "60m 1.0s"


def test_timed_prints_label_to_stream(tmp_path: Path, capsys):
    with timed("test:work") as t:
        time.sleep(0.01)
    captured = capsys.readouterr()
    assert "timing: test:work" in captured.err
    assert t.elapsed > 0


def test_record_timing_writes_meta(tmp_path: Path):
    """record_timing persists into the meta table."""

    db = tmp_path / "timing.sqlite"
    # Bootstrap a DB with just the meta table — the helper guards
    # against a missing meta table.
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()
    conn.close()

    record_timing(db, "ingest", 3.14)

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT value FROM meta WHERE key = 'timing.ingest'").fetchone()
    assert row is not None
    # Stored to millisecond precision as a string.
    assert row[0] == "3.140"


def test_record_timing_noop_when_db_missing(tmp_path: Path):
    """A fresh ingest (no DB yet) shouldn't crash on record_timing."""

    record_timing(tmp_path / "doesnotexist.sqlite", "ingest", 1.0)
    # No exception = pass.


def test_record_timing_noop_without_meta_table(tmp_path: Path):
    """A half-built DB without meta shouldn't crash either."""

    db = tmp_path / "no-meta.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE other (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    record_timing(db, "ingest", 1.0)
    # No exception = pass.
