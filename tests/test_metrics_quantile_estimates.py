"""Quantiles are ESTIMATES from 14 log-scale buckets; min/max are exact.

The two disagree, and on live data p99 exceeds max on 8 of 24 routes. That is
arithmetic, not a defect: a 116 ms request lands in the (100, 250] bucket, and
with few samples the p99 estimate resolves toward that bucket's top — a number
the corpus never contained.

Nothing displays both today, which is why it is latent. These tests pin the
property so that CLAMPING it (`min(quantile, max_ms)`) becomes a deliberate
choice with a failing test attached, rather than a silent change of meaning.
Clamping would bias the tail DOWNWARD, which is the direction that hides slow
routes — on a surface whose job is to find them.
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from minerva.metrics import store as m


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    return c


def _summary(conn):
    rows = m.summary(conn, since=0.0, until=time.time() + 1000)
    return next(r for r in rows if r["kind"] == "total" and r["span"] == "")


def test_a_quantile_can_exceed_the_exact_max(conn):
    """Eight live routes do this. Reproduced deterministically: eight samples
    whose slowest is 116 ms, reported with a p99 above it."""

    now = time.time()
    for ms in (5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 116.0):
        m.write(conn, [m.Sample(now, "chunk syntax", "GET", "total", "", 2, ms)])
    row = _summary(conn)
    assert row["max_ms"] == pytest.approx(116.0)
    assert row["p99_ms"] > row["max_ms"], (
        "the estimate no longer exceeds the max — if that was deliberate "
        "(clamping), note that it biases the tail DOWNWARD and hides slow "
        "routes on a surface built to find them (#616)"
    )


def test_min_and_max_are_exact(conn):
    """They come from the samples, not the buckets — which is precisely why
    they can contradict a quantile."""

    now = time.time()
    for ms in (3.5, 900.25, 41.0):
        m.write(conn, [m.Sample(now, "works list", "GET", "total", "", 2, ms)])
    row = _summary(conn)
    assert row["min_ms"] == pytest.approx(3.5)
    assert row["max_ms"] == pytest.approx(900.25)


def test_the_estimate_is_bounded_by_its_bucket(conn):
    """The mechanism, so the failure above reads as arithmetic rather than a
    bug: the estimate cannot exceed the top of the bucket the sample fell in."""

    now = time.time()
    m.write(conn, [m.Sample(now, "one", "GET", "total", "", 2, 116.0)])
    row = _summary(conn)
    # 116 ms falls in (100, 250]; the estimate lands inside that bucket.
    assert 100.0 < row["p99_ms"] <= 250.0


def test_summary_documents_the_disagreement():
    """A consumer meets this in the docstring before they meet it in a chart."""

    doc = m.summary.__doc__ or ""
    assert "estimate" in doc.lower()
    assert "max" in doc.lower()
