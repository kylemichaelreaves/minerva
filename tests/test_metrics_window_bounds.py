"""A window must include the bucket that `until` falls in (#598).

`bucket_start` is floored to `BUCKET_SECONDS`, so a row written at `now`
carries `floor(now/300)*300`, which is <= `int(now)`. With a strictly
exclusive upper bound the two coincide during the first second of every
bucket, and the row written a moment ago vanishes from a window that ends
"now" — `window=all` included, which is meant to mean everything.

That is a 1-in-300 event, which is why #598 was filed as a flaky test
rather than as the clock-dependent off-by-one it is.
"""

from __future__ import annotations

import sqlite3

import pytest

from minerva.metrics import store as m

BOUNDARY = 1_700_000_100.0  # int(BOUNDARY) % 300 == 0
assert int(BOUNDARY) % m.BUCKET_SECONDS == 0, "fixture must sit on a bucket edge"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    return c


def _write(c: sqlite3.Connection, at: float) -> None:
    m.write(c, [m.Sample(at, "works list", "GET", "total", "", 2, 12.0)])


@pytest.mark.parametrize(
    "offset",
    [0.0, 0.5, 0.99, 1.0, 150.0, 299.0],
    ids=["edge", "edge+0.5s", "edge+0.99s", "edge+1s", "mid-bucket", "bucket-end"],
)
def test_summary_includes_a_request_recorded_at_until(conn, offset):
    now = BOUNDARY + offset
    _write(conn, now)
    rows = m.summary(conn, since=0.0, until=now)
    assert [r["label"] for r in rows] == ["works list"], (
        f"a request recorded at {now} is missing from a window ending at {now} "
        f"(int(now) % {m.BUCKET_SECONDS} == {int(now) % m.BUCKET_SECONDS})"
    )


@pytest.mark.parametrize("offset", [0.0, 0.5, 150.0], ids=["edge", "edge+0.5s", "mid-bucket"])
def test_series_includes_a_request_recorded_at_until(conn, offset):
    now = BOUNDARY + offset
    _write(conn, now)
    points = m.series(
        conn,
        label="works list",
        kind="total",
        span="",
        since=0.0,
        until=now,
        bucket_seconds=m.BUCKET_SECONDS,
    )
    assert [p["count"] for p in points] == [1], (
        f"a request recorded at {now} is missing from a series ending at {now}"
    )
