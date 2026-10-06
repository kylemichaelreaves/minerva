"""Folding pipeline timings into a distribution (#Phase 5).

**Durations are per BATCH, not per chunk, and that is forced by measurement.**
`batch_pipe` delegates to spaCy's `nlp.pipe(batch_size=64)`, so
time-since-last-yield measures queue drain rather than work: over 400 `lat`
chunks, 7 iterations carried 96% of the cost and the rest read as ~0.1 ms of
loop overhead. A naive per-chunk p50 reported 0.115 ms against a true mean of
2.598 ms — understating by 22.6x. Token counts are exact per chunk, because
`len(tokens)` does not care how the work was batched.

428,982 chunks become a handful of rows. The point is a distribution across
the corpus, not a log of runs — so the accumulator is pure and holds only
histograms, and the caller decides when to write.

The key carries `backend` because spaCy falls back to Stanza when a model is
missing: the same language is a different engine on different machines, and a
row that silently mixed the two would be worse than no row.
"""

from __future__ import annotations

import pytest

from minerva.metrics.histogram import BUCKET_COUNT, quantile
from minerva.metrics.pipeline_stats import PipelineStats


def test_one_duration_row_per_key_not_per_batch():
    s = PipelineStats()
    for _ in range(100):
        s.record_batch(lang="lat", backend="spacy", model="la_core_web_sm", ms=160.0, size=64)
    rows = [r for r in s.rows(at=1.0, pipeline="lemmatize") if r.kind == "batch_duration"]
    assert len(rows) == 1
    assert rows[0].count == 100  # batches observed
    assert rows[0].items == 6400  # chunks they covered


def test_throughput_is_derivable():
    """The reason `items` is stored beside `count`: a batch duration alone
    cannot say chunks-per-second, and that is the number an operator wants."""

    s = PipelineStats()
    s.record_batch(lang="lat", backend="spacy", model="la_core_web_sm", ms=1000.0, size=64)
    (row,) = [r for r in s.rows(at=1.0, pipeline="lemmatize") if r.kind == "batch_duration"]
    assert row.items / (row.sum / 1000.0) == pytest.approx(64.0)


def test_tokens_are_counted_per_chunk_not_per_batch():
    s = PipelineStats()
    for n in (10, 20, 30):
        s.record_tokens(lang="lat", backend="spacy", model="la_core_web_sm", tokens=n)
    (row,) = [r for r in s.rows(at=1.0, pipeline="lemmatize") if r.kind == "tokens"]
    assert row.count == 3
    assert row.max == pytest.approx(30.0)


def test_the_two_kinds_have_different_counts():
    """The distinction the design turns on: batches observed vs chunks seen.
    A reader dividing one by the other must not be silently comparing the
    same number twice."""

    s = PipelineStats()
    s.record_batch(lang="lat", backend="spacy", model="la_core_web_sm", ms=160.0, size=64)
    for _ in range(64):
        s.record_tokens(lang="lat", backend="spacy", model="la_core_web_sm", tokens=15)
    by_kind = {r.kind: r for r in s.rows(at=1.0, pipeline="lemmatize")}
    assert by_kind["batch_duration"].count == 1
    assert by_kind["tokens"].count == 64


def test_the_backend_is_part_of_the_key():
    """The fallback case. `lat` served by spaCy and `lat` served by Stanza are
    different populations and must not be summed into one distribution."""

    s = PipelineStats()
    s.record_batch(lang="lat", backend="spacy", model="la_core_web_sm", ms=10.0, size=1)
    s.record_batch(lang="lat", backend="stanza", model="la", ms=50.0, size=1)
    rows = [r for r in s.rows(at=1.0, pipeline="lemmatize") if r.kind == "batch_duration"]
    assert {(r.backend, r.model) for r in rows} == {
        ("spacy", "la_core_web_sm"),
        ("stanza", "la"),
    }


def test_quantiles_survive_the_fold():
    # 980/20, not 990/10: at exactly 99% the p99 lands ON the boundary, which
    # tests the tie-break rather than the fold.
    s = PipelineStats()
    for _ in range(980):
        s.record_batch(lang="grc", backend="spacy", model="grc_dep_web_sm", ms=10.0, size=64)
    for _ in range(20):
        s.record_batch(lang="grc", backend="spacy", model="grc_dep_web_sm", ms=3000.0, size=64)
    (row,) = [r for r in s.rows(at=1.0, pipeline="lemmatize") if r.kind == "batch_duration"]
    assert len(row.buckets) == BUCKET_COUNT
    assert quantile(row.buckets, 0.50) < 30
    assert quantile(row.buckets, 0.99) > 1000


def test_min_and_max_are_exact_not_bucketed():
    s = PipelineStats()
    for ms in (3.5, 900.25, 41.0):
        s.record_batch(lang="deu", backend="spacy", model="de_core_news_sm", ms=ms, size=1)
    (row,) = [r for r in s.rows(at=1.0, pipeline="lemmatize") if r.kind == "batch_duration"]
    assert row.min == pytest.approx(3.5)
    assert row.max == pytest.approx(900.25)


def test_an_empty_run_produces_no_rows():
    """A run that processed nothing must not write a row claiming it did."""

    assert PipelineStats().rows(at=1.0, pipeline="lemmatize") == []
