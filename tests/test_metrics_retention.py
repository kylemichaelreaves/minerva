"""Retention: off by default, and never on the request path.

Measured before choosing: the live metrics DB shows 751 requests/day, and at
that rate 18 years of complete history is 567 MB with the "last 24h" query flat
at 0.1ms. The queries that DO grow are unindexed ones, and those are fixed by
the indexes shipped with the table — not by deleting data. So the default is to
keep everything, and the cap exists for whoever later decides otherwise.
"""

from __future__ import annotations

import time

from minerva.metrics import store as m


def _seed(conn, ages_days):
    now = time.time()
    for i, age in enumerate(ages_days):
        conn.execute(
            "INSERT INTO request_spans"
            " (id, at, label, method, status, total_ms, accounted_ms, phases)"
            " VALUES (?,?,?,?,?,?,?,?)",  # named, so an added column cannot break this
            (f"id{i}", now - age * 86400, "works list", "GET", 200, 1.0, 0.0, "[]"),
        )
    conn.commit()


def _ids(conn):
    return sorted(r[0] for r in conn.execute("SELECT id FROM request_spans"))


def test_nothing_is_deleted_by_default(tmp_path):
    """The default is the decision: keep history. A cap that defaulted on
    would silently destroy the thing the table exists to provide."""

    path = tmp_path / "metrics.sqlite"
    c = m.open_db(path)
    _seed(c, [0.1, 400, 4000])
    c.close()

    c = m.open_db(path)  # reopen: the prune runs here, if at all
    assert _ids(c) == ["id0", "id1", "id2"]
    c.close()


def test_a_configured_cutoff_prunes_at_open(tmp_path):
    path = tmp_path / "metrics.sqlite"
    c = m.open_db(path)
    _seed(c, [0.1, 45, 400])
    c.close()

    c = m.open_db(path, retain_days=90)
    assert _ids(c) == ["id0", "id1"], "the 400-day-old row should be gone"
    c.close()


def test_pruning_leaves_request_timings_alone(tmp_path):
    """The aggregate is small by construction and is not what grows."""

    path = tmp_path / "metrics.sqlite"
    c = m.open_db(path)
    m.write(c, [m.Sample(time.time() - 400 * 86400, "works list", "GET", "total", "", 2, 5.0)])
    _seed(c, [400])
    c.close()

    c = m.open_db(path, retain_days=90)
    assert _ids(c) == []
    assert c.execute("SELECT count(*) FROM request_timings").fetchone()[0] == 1
    c.close()


def test_the_prune_is_not_on_the_request_path(tmp_path):
    """Recording a request must never trigger a DELETE. The prune belongs to
    connection setup, which happens once per process."""

    path = tmp_path / "metrics.sqlite"
    c = m.open_db(path, retain_days=1)
    _seed(c, [400])

    from minerva.metrics.recorder import Recorder

    rec = Recorder(c)
    with rec.record("works list", "GET") as span:
        span.status = 200

    assert "id0" in _ids(c), "recording a request pruned rows"
    c.close()
