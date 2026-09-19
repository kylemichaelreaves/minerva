"""Every request carries an id, and it rides the Span already in the ContextVar.

The id exists so a durable per-request row can be keyed on something, and so a
SQL comment can carry it later (Phase 3). It is deliberately NOT written to
`request_timings`, which stays aggregated and id-free.
"""

from __future__ import annotations

import re

from minerva.metrics.recorder import Recorder, current_span

HEX16 = re.compile(r"\A[0-9a-f]{16}\Z")


def test_each_request_gets_its_own_id():
    rec = Recorder()
    seen = []
    for _ in range(50):
        with rec.record("works list", "GET") as span:
            seen.append(span.id)
    assert len(set(seen)) == 50, "ids collided"
    assert all(HEX16.match(i) for i in seen), f"not 16 hex chars: {seen[:3]}"


def test_the_id_is_reachable_from_inside_the_request():
    """No new ContextVar: `_CURRENT` already holds the Span, so anything that
    can call `current_span()` can read the id — which is how a sub-span or a
    cursor wrapper will reach it without a signature change."""

    rec = Recorder()
    with rec.record("chat", "POST") as span:
        inside = current_span()
        assert inside is span
        assert inside.id == span.id


def test_the_id_is_random_not_sequential():
    """A counter would restart at the same value in the next process and
    collide across restarts. Two independently constructed Recorders must not
    produce a shared sequence."""

    a = [s.id for s in _ids(Recorder(), 10)]
    b = [s.id for s in _ids(Recorder(), 10)]
    assert not set(a) & set(b)
    ints = [int(i, 16) for i in a]
    deltas = {ints[i + 1] - ints[i] for i in range(len(ints) - 1)}
    assert len(deltas) > 1, f"ids advance by a constant step: {deltas}"


def _ids(rec, n):
    out = []
    for _ in range(n):
        with rec.record("health", "GET") as span:
            out.append(span)
    return out
