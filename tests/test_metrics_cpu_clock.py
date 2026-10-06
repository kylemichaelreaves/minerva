"""Clock resolution for CPU timing (#Phase 2).

Two things are being fixed at once, and they are related:

* `sub_span`'s `clock` default was bound at IMPORT, so patching
  `time.perf_counter` afterwards never reached it. The audit flagged this and
  Phase 1's brief deferred it here explicitly.
* CPU time must come from `time.thread_time`, NOT `time.process_time`.
  `process_time` is process-wide, and this server runs one thread per request,
  so a span would absorb every concurrent request's CPU — measured at 4.5x
  overattribution with three neighbours, in the direction that turns a WAITING
  phase into a CPU-bound one.
"""

from __future__ import annotations

import time

import pytest

from minerva.metrics import recorder as R
from minerva.metrics.recorder import Recorder, sub_span


class FakeClock:
    def __init__(self, step=0.0):
        self.t = 0.0
        self.step = step

    def __call__(self):
        self.t += self.step
        return self.t


def test_the_wall_clock_default_is_resolved_at_call_time_not_import(monkeypatch):
    """The whole point of the fix: a patched `time.perf_counter` must reach it."""

    ticks = iter([0.0, 2.0])
    monkeypatch.setattr(R.time, "perf_counter", lambda: next(ticks))
    rec = Recorder(None)
    with rec.record("chat", "POST") as span, sub_span("llm_call"):
        pass
    assert [n for n, _ in span._subs] == ["llm_call"]
    assert span._subs[0][1] == pytest.approx(2000.0)


def test_an_explicit_clock_still_wins_over_the_default(monkeypatch):
    monkeypatch.setattr(R.time, "perf_counter", lambda: 999.0)
    rec = Recorder(None)
    with rec.record("chat", "POST") as span, sub_span("llm_call", clock=FakeClock(step=0.5)):
        pass
    assert span._subs[0][1] == pytest.approx(500.0)


def test_cpu_comes_from_thread_time_not_process_time():
    """Named explicitly, because the two differ only under concurrency — and
    a test that never runs a second thread cannot tell them apart."""

    assert R._THREAD_TIME is time.thread_time


def test_cpu_capture_disables_cleanly_when_thread_time_is_unavailable(monkeypatch):
    """`time.thread_time` is not on every platform. Absent, CPU capture turns
    off — it does NOT fall back to `process_time`, because a wrong number here
    is worse than no number."""

    monkeypatch.setattr(R, "_THREAD_TIME", None)
    rec = Recorder(None)
    with rec.record("chat", "POST") as span, sub_span("llm_call"):
        pass
    assert span.cpu_ms is None
    assert span._subs_cpu == {}


def test_thread_time_is_never_silently_swapped_for_process_time():
    """Guards the specific mistake the brief made.

    Checked over the AST, not the source text: the module deliberately explains
    in a comment why `process_time` is wrong, and a substring scan would trip
    on the explanation. Comments are absent from the AST, so this asserts the
    name is never actually *referenced* — which is the thing that would hurt.
    """

    import ast
    import inspect

    tree = ast.parse(inspect.getsource(R))
    referenced = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)} | {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    assert "process_time" not in referenced, (
        "process_time is process-wide; under ThreadingHTTPServer it attributes "
        "concurrent requests' CPU to whichever span is open (4.5x overattribution "
        "measured with three neighbours)."
    )
    assert "thread_time" in inspect.getsource(R)
