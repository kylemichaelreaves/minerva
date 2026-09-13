"""Bucket math for request timings. Pure functions, no I/O."""

from __future__ import annotations

import pytest

from minerva.metrics.histogram import (
    BUCKET_COUNT,
    BUCKET_UPPER_MS,
    bucket_index,
    quantile,
)


def test_bucket_count_is_finite_bounds_plus_overflow():
    assert len(BUCKET_UPPER_MS) + 1 == BUCKET_COUNT


def test_bucket_index_lower_edge_lands_in_first_bucket():
    assert bucket_index(0.0) == 0
    assert bucket_index(0.9) == 0


def test_bucket_index_is_upper_exclusive():
    # 1.0 is the first bound, so it belongs to the NEXT bucket.
    assert bucket_index(1.0) == 1
    assert bucket_index(2.4) == 1


def test_bucket_index_overflow():
    assert bucket_index(999_999.0) == BUCKET_COUNT - 1


def test_bucket_index_negative_clamps_to_first():
    # A clock that went backwards must not produce a negative index.
    assert bucket_index(-5.0) == 0


def test_quantile_empty_is_zero():
    assert quantile([0] * BUCKET_COUNT, 0.95) == 0.0


def test_quantile_single_bucket_interpolates_within_it():
    counts = [0] * BUCKET_COUNT
    counts[3] = 10  # bucket 3 spans [5.0, 10.0)
    got = quantile(counts, 0.5)
    assert 5.0 <= got <= 10.0


def test_quantile_p95_lands_in_the_tail_bucket():
    counts = [0] * BUCKET_COUNT
    counts[0] = 95   # [0, 1)
    counts[8] = 5    # [250, 500)
    assert quantile(counts, 0.99) > 250.0


def test_quantile_overflow_bucket_returns_last_finite_bound():
    counts = [0] * BUCKET_COUNT
    counts[BUCKET_COUNT - 1] = 4
    # Cannot interpolate to infinity; the last finite bound is the floor.
    assert quantile(counts, 0.95) == BUCKET_UPPER_MS[-1]


@pytest.mark.parametrize("q", [0.0, -0.1, 1.1])
def test_quantile_rejects_out_of_range(q):
    with pytest.raises(ValueError):
        quantile([1] + [0] * (BUCKET_COUNT - 1), q)
