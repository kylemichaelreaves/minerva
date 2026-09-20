"""The `/*request_id='...'*/` prefix on statements.

Built ONCE per request and cached on the Span, never interpolated per query.
Measured in the audit: a distinct comment per query defeats Python's
prepared-statement cache and costs 5.88x on a point lookup (0.59 -> 3.49 us);
a per-request constant costs +0.1-0.2 us because repeated shapes within one
request still hit.

Stated plainly: in SQLite this comment has no automatic reader. There is no
server and no slow-query log. Its value is EXPLAIN output and a future trace
log; the timing does not need it.
"""

from __future__ import annotations

import pytest

from minerva.metrics.recorder import Recorder
from minerva.sqlite_util import open_sqlite

SCHEMA = "CREATE TABLE IF NOT EXISTS t (a INTEGER PRIMARY KEY, b TEXT);"


@pytest.fixture
def conn(tmp_path):
    return open_sqlite(tmp_path / "x.sqlite", SCHEMA)


def _seen(conn):
    out: list[str] = []
    conn.set_trace_callback(out.append)
    return out


def test_the_statement_the_database_receives_carries_the_request_id(conn):
    seen = _seen(conn)
    rec = Recorder(None)
    with rec.record("works list", "GET") as span:
        conn.execute("SELECT 1").fetchone()
    conn.set_trace_callback(None)
    assert any(f"request_id='{span.id}'" in s for s in seen), seen


def test_the_prefix_is_identical_for_every_query_in_one_request(conn):
    """The whole cost question. A per-QUERY id makes every statement a fresh
    prepare; a per-REQUEST id lets repeated shapes hit the cache."""

    seen = _seen(conn)
    rec = Recorder(None)
    with rec.record("works list", "GET"):
        for _ in range(5):
            conn.execute("SELECT 1").fetchone()
    conn.set_trace_callback(None)
    prefixes = {s.split("*/")[0] for s in seen if s.startswith("/*")}
    assert len(prefixes) == 1, f"prefix varied within one request: {prefixes}"


def test_two_requests_get_different_ids(conn):
    seen = _seen(conn)
    rec = Recorder(None)
    for _ in range(2):
        with rec.record("works list", "GET"):
            conn.execute("SELECT 1").fetchone()
    conn.set_trace_callback(None)
    prefixes = {s.split("*/")[0] for s in seen if s.startswith("/*")}
    assert len(prefixes) == 2


def test_no_prefix_outside_a_request(conn):
    """The CLI runs the same code. An unconditional prefix would make every
    ingest statement a cache miss for an id that does not exist."""

    seen = _seen(conn)
    conn.execute("SELECT 1").fetchone()
    conn.set_trace_callback(None)
    assert not any(s.startswith("/*request_id") for s in seen), seen


def test_the_prefix_does_not_change_results(conn):
    rec = Recorder(None)
    conn.execute("INSERT INTO t VALUES (1, 'x')")
    with rec.record("works list", "GET"):
        assert conn.execute("SELECT b FROM t WHERE a = ?", (1,)).fetchone()[0] == "x"


def test_executescript_is_not_prefixed(conn):
    """`executescript` takes a whole script and is used for schema work, not
    request work. Prefixing it risks changing how the script parses for no
    benefit."""

    seen = _seen(conn)
    rec = Recorder(None)
    with rec.record("migrate", "POST"):
        conn.executescript("INSERT INTO t VALUES (7, 'q');")
    conn.set_trace_callback(None)
    assert not any(s.strip().startswith("/*request_id") for s in seen), seen
