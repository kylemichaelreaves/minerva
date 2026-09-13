"""Fixed log-scale latency buckets and the quantile estimate over them.

Counts are stored PER BUCKET, not cumulatively. Cumulative would be the
Prometheus convention and makes the quantile scan marginally simpler, but
recording a request then means incrementing every column at or above the
observed value instead of exactly one. Cumulate at read time; summation
aggregates either form, so nothing downstream cares.
"""

from __future__ import annotations

from collections.abc import Sequence

# Upper bounds in milliseconds, exclusive. Chosen to span a sub-millisecond
# static-asset read through a ~10s Stanza cold start with roughly even
# resolution in log space.
BUCKET_UPPER_MS: tuple[float, ...] = (
    1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0,
    250.0, 500.0, 1000.0, 2500.0, 5000.0, 10000.0,
)

# One more than the finite bounds: the last bucket is the overflow.
BUCKET_COUNT: int = len(BUCKET_UPPER_MS) + 1


def bucket_index(ms: float) -> int:
    """Return the bucket *ms* falls in. Upper bounds are exclusive, so a
    duration of exactly 1.0 ms lands in bucket 1, not bucket 0."""

    for i, upper in enumerate(BUCKET_UPPER_MS):
        if ms < upper:
            return i
    return BUCKET_COUNT - 1


def _bucket_bounds(i: int) -> tuple[float, float]:
    lo = 0.0 if i == 0 else BUCKET_UPPER_MS[i - 1]
    hi = BUCKET_UPPER_MS[i]
    return lo, hi


def quantile(counts: Sequence[int], q: float) -> float:
    """Estimate the *q*th quantile in milliseconds from per-bucket *counts*.

    Linearly interpolates within the bucket the target rank falls into, so
    the result carries up to one bucket-width of error. `sum_ms / count` is
    exact and is the precise trend signal; this is the tail-shape signal.
    """

    if not 0.0 < q <= 1.0:
        raise ValueError(f"quantile q must be in (0, 1], got {q!r}")
    total = sum(counts)
    if total == 0:
        return 0.0
    target = q * total
    cumulative = 0
    for i, count in enumerate(counts):
        if count == 0:
            continue
        previous = cumulative
        cumulative += count
        if cumulative < target:
            continue
        if i == BUCKET_COUNT - 1:
            # Overflow bucket has no upper bound to interpolate toward.
            return BUCKET_UPPER_MS[-1]
        lo, hi = _bucket_bounds(i)
        return lo + (hi - lo) * ((target - previous) / count)
    return BUCKET_UPPER_MS[-1]


__all__ = ["BUCKET_COUNT", "BUCKET_UPPER_MS", "bucket_index", "quantile"]
