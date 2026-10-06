"""Database time, measured at the connection layer (#Phase 3).

Measured on the real corpus before building: `works list` spends 240.5 ms of
its 241.3 ms inside ONE statement — 99.7%. The audit called database time the
largest known component of the unaccounted gap; on that route it is the whole
of it. Measuring here rather than at call sites is what makes that visible
without a `sub_span` in every handler.
"""

from __future__ import annotations

from contextlib import closing

import pytest

from minerva.metrics.recorder import Recorder, current_span
from minerva.sqlite_util import open_sqlite

SCHEMA = "CREATE TABLE IF NOT EXISTS t (a INTEGER PRIMARY KEY, b TEXT);"


@pytest.fixture
def conn(tmp_path):
    return open_sqlite(tmp_path / "x.sqlite", SCHEMA)


def test_execute_is_attributed_to_the_active_request(conn):
    rec = Recorder(None)
    with rec.record("works list", "GET") as span:
        conn.execute("INSERT INTO t VALUES (1, 'x')")
        conn.execute("SELECT * FROM t").fetchall()
    assert span.sqlite_queries == 2
    assert span.sqlite_ms is not None and span.sqlite_ms > 0


def test_executemany_is_attributed_too(conn):
    """`conn.execute` is the shortcut most of the codebase uses, but bulk
    writes go through `executemany` and would otherwise be invisible."""

    rec = Recorder(None)
    with rec.record("ingest", "POST") as span:
        conn.executemany("INSERT INTO t VALUES (?,?)", [(i, "y") for i in range(50)])
    assert span.sqlite_queries == 1
    assert span.sqlite_ms is not None


def test_executescript_is_attributed_too(conn):
    rec = Recorder(None)
    with rec.record("migrate", "POST") as span:
        conn.executescript("INSERT INTO t VALUES (99, 'z');")
    assert span.sqlite_queries == 1


def test_a_query_outside_a_request_is_a_no_op(conn):
    """The CLI and ingest run the same code paths with no request in flight."""

    assert current_span() is None
    conn.execute("SELECT 1").fetchone()  # must not raise


def test_nothing_escapes_through_an_explicit_cursor():
    """A `Connection` override does NOT intercept `conn.cursor().execute(...)`
    — CPython creates that cursor in C.

    There are zero such call sites today, which is why the instrumentation
    lives on the Connection rather than in two layers. This fails if one
    appears, so the gap is caught by a test rather than by silence.
    """

    import ast
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "minerva"
    offenders = []
    for path in src.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # A CALL to `.cursor()`, not a mention of it — this module's own
            # docstring explains the gap, and a text scan trips on the
            # explanation.
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "cursor"
            ):
                offenders.append(f"{path.relative_to(src)}:{node.lineno}")
    assert not offenders, (
        f"explicit .cursor() bypasses connection-layer timing: {offenders}. "
        f"Either route it through conn.execute(), or extend the instrumentation "
        f"to the cursor layer."
    )


def test_the_metrics_write_is_not_attributed_to_the_request_that_caused_it(tmp_path):
    """Otherwise every request records the cost of recording the previous one.

    This holds because `record()` resets the ContextVar BEFORE `_finish` runs
    the INSERT. That ordering is load-bearing, so it is pinned here rather
    than left as a happy accident.
    """

    from minerva.metrics import store as m

    with closing(m.open_db(tmp_path / "metrics.sqlite")) as metrics_conn:
        rec = Recorder(metrics_conn, now=lambda: 1_700_000_000.0)
        with rec.record("works list", "GET") as span:
            span.status = 200
        written = metrics_conn.execute("SELECT sqlite_queries FROM request_spans").fetchone()[0]
    # The request itself issued no queries; the metrics INSERT must not appear.
    assert written == 0
