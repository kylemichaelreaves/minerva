"""Batch-pipeline timings, folded into distributions.

**Durations are per BATCH; token counts are per chunk.** That asymmetry is
forced by measurement, not chosen for convenience. `Lemmatizer.batch_pipe`
delegates to spaCy's `nlp.pipe(batch_size=64)`, so the time between two
yields is queue drain, not work: over 400 `lat` chunks, 7 iterations carried
96% of the cost and the other 393 read as ~0.1 ms of loop overhead. A p50
built from those reported **0.115 ms** against a true mean of **2.598 ms** —
understating by 22.6x. `len(tokens)` is unaffected, because it does not care
how the work was batched.

`items` is stored beside `count` on a duration row so throughput is
recoverable: a batch duration alone cannot say chunks-per-second.

428,982 chunks become a handful of rows. This is deliberately NOT the request
machinery: `Recorder`, `Span` and `current_span()` are built on a ContextVar,
and neither `ingest` (a `ProcessPoolExecutor`) nor `lemmatize` (spaCy's own
`Language._multiprocessing_pipe`) keeps the work in the calling process. So
this accumulates wherever the work happens and is handed back by value.

It is also not a request: there is no route, no method, no status and no
request id, and none are invented to make it fit the existing table.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable, Iterable, Iterator
from typing import TypeVar

from .histogram import BUCKET_COUNT, bucket_index


@dataclasses.dataclass(frozen=True, slots=True)
class PipelineRow:
    """One (run, lang, backend, model, kind) distribution."""

    at: float
    pipeline: str
    lang: str
    backend: str
    model: str
    kind: str
    # Observations folded in: BATCHES for `batch_duration`, CHUNKS for
    # `tokens`. The two differ by the batch size, and a reader dividing one
    # by the other must not be silently comparing the same number twice.
    count: int
    sum: float
    min: float
    max: float
    buckets: list[int]
    # Chunks covered. Meaningful only on a duration row, where it is what
    # makes throughput derivable; equals `count` for per-chunk kinds.
    items: int = 0


@dataclasses.dataclass(slots=True)
class _Acc:
    count: int = 0
    total: float = 0.0
    lo: float = 0.0
    hi: float = 0.0
    buckets: list[int] = dataclasses.field(default_factory=lambda: [0] * BUCKET_COUNT)

    def add(self, v: float) -> None:
        if self.count == 0:
            self.lo = self.hi = v
        else:
            self.lo = min(self.lo, v)
            self.hi = max(self.hi, v)
        self.count += 1
        self.total += v
        self.buckets[bucket_index(v)] += 1


class PipelineStats:
    """Accumulates pipeline observations, keyed by what actually served them.

    `backend` is in the key on purpose. spaCy falls back to Stanza when a
    model is not installed, so the same language is a different engine on
    different machines — and `lat` timings summed across both would describe
    a population that does not exist.
    """

    __slots__ = ("_dur", "_items", "_tok")

    def __init__(self) -> None:
        self._dur: dict[tuple[str, str, str], _Acc] = {}
        self._tok: dict[tuple[str, str, str], _Acc] = {}
        self._items: dict[tuple[str, str, str], int] = {}

    def record_batch(
        self, *, lang: str, backend: str, model: str, ms: float, size: int
    ) -> None:
        """One batch's wall time, and how many chunks it covered."""

        key = (lang, backend, model)
        self._dur.setdefault(key, _Acc()).add(ms)
        self._items[key] = self._items.get(key, 0) + size

    def record_tokens(
        self, *, lang: str, backend: str, model: str, tokens: int
    ) -> None:
        """One chunk's token count. Exact — batching does not affect it."""

        self._tok.setdefault((lang, backend, model), _Acc()).add(float(tokens))

    def rows(self, *, at: float, pipeline: str) -> list[PipelineRow]:
        """Materialise the distributions. Empty when nothing was recorded —
        a run that processed nothing must not write a row claiming it did."""

        out: list[PipelineRow] = []
        for kind, table in (("batch_duration", self._dur), ("tokens", self._tok)):
            for key, acc in sorted(table.items()):
                lang, backend, model = key
                out.append(
                    PipelineRow(
                        at=at,
                        pipeline=pipeline,
                        lang=lang,
                        backend=backend,
                        model=model,
                        kind=kind,
                        count=acc.count,
                        sum=acc.total,
                        min=acc.lo,
                        max=acc.hi,
                        buckets=list(acc.buckets),
                        items=self._items.get(key, 0) if kind == "batch_duration" else acc.count,
                    )
                )
        return out


_T = TypeVar("_T")


def observe_windows(
    items: Iterable[_T],
    stats: PipelineStats,
    *,
    lang: str,
    backend: str,
    model: str,
    window: int = 64,
    clock: Callable[[], float] = time.perf_counter,
) -> Iterator[_T]:
    """Yield *items* through, recording one duration per *window* of them.

    `nlp.pipe` batches internally and the consumer cannot see where one batch
    ends — but it does not need to. Timing windows of N yields **partitions**
    the stream, so the durations sum to the run and throughput is exact. Each
    window covers a batch's worth of work however the internals aligned.

    This is what makes the number honest. Timing each individual yield does
    not work: over 400 `lat` chunks, 7 iterations carried 96% of the cost and
    the rest were loop overhead, so a per-chunk p50 read 0.115 ms against a
    true mean of 2.598 ms.

    Lazy on purpose — `batch_pipe` streams 428,982 chunks and materialising
    them would undo the streaming cursor the pipeline is built around.
    """

    n = 0
    start = clock()
    for item in items:
        yield item
        n += 1
        if n == window:
            stats.record_batch(
                lang=lang, backend=backend, model=model, ms=(clock() - start) * 1000.0, size=n
            )
            n = 0
            start = clock()
    if n:
        # The tail. Without this a run shorter than one window records
        # nothing at all, and every run silently loses its remainder.
        stats.record_batch(
            lang=lang, backend=backend, model=model, ms=(clock() - start) * 1000.0, size=n
        )


__all__ = ["PipelineRow", "PipelineStats", "observe_windows"]
