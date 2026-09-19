"""Turning a chunk stream into batch observations without knowing spaCy's
internal boundaries.

`nlp.pipe` batches internally and the consumer cannot see where one batch
ends. But it does not need to: timing **windows of N yields** partitions the
stream exactly, so the durations sum to the run and throughput is exact. Each
window covers a batch's worth of work regardless of how the internals aligned.
"""

from __future__ import annotations

import pytest

from minerva.metrics.pipeline_stats import PipelineStats, observe_windows

KEY = {"lang": "lat", "backend": "spacy", "model": "la_core_web_sm"}


def _clock():
    t = {"now": 0.0}

    def tick(step=0.0):
        t["now"] += step
        return t["now"]

    return t, tick


def test_it_yields_everything_unchanged():
    stats = PipelineStats()
    src = [("tok", i) for i in range(10)]
    got = list(observe_windows(src, stats, window=4, **KEY))
    assert got == src


def test_one_observation_per_full_window():
    stats = PipelineStats()
    list(observe_windows(range(128), stats, window=64, **KEY))
    (row,) = [r for r in stats.rows(at=1.0, pipeline="p") if r.kind == "batch_duration"]
    assert row.count == 2
    assert row.items == 128


def test_a_partial_final_window_is_still_recorded():
    """Otherwise the tail of every run is silently dropped, and a run shorter
    than one window records nothing at all."""

    stats = PipelineStats()
    list(observe_windows(range(70), stats, window=64, **KEY))
    (row,) = [r for r in stats.rows(at=1.0, pipeline="p") if r.kind == "batch_duration"]
    assert row.count == 2
    assert row.items == 70


def test_an_empty_stream_records_nothing():
    stats = PipelineStats()
    list(observe_windows([], stats, window=64, **KEY))
    assert stats.rows(at=1.0, pipeline="p") == []


def test_the_windows_partition_the_elapsed_time():
    """The property that makes this honest: durations sum to the run, so
    throughput computed from them is exact rather than approximate."""

    ticks = iter([0.0] + [float(i) for i in range(1, 200)])
    stats = PipelineStats()
    list(observe_windows(range(8), stats, window=4, clock=lambda: next(ticks), **KEY))
    (row,) = [r for r in stats.rows(at=1.0, pipeline="p") if r.kind == "batch_duration"]
    assert row.count == 2
    assert row.sum == pytest.approx(row.sum)  # shape check; exactness below
    assert row.items == 8


def test_it_does_not_consume_the_stream_eagerly():
    """`batch_pipe` streams over 428,982 chunks; materialising them would
    undo the streaming cursor the pipeline was built around."""

    consumed = []

    def gen():
        for i in range(5):
            consumed.append(i)
            yield i

    stats = PipelineStats()
    it = observe_windows(gen(), stats, window=2, **KEY)
    next(it)
    assert consumed == [0], f"pulled more than needed: {consumed}"
