"""The three instrumented hot paths report under the active request."""

from __future__ import annotations

import sqlite3

import pytest

from minerva.metrics import store as m
from minerva.metrics.recorder import Recorder

SPAN_NAMES = ("stanza_parse", "embed_search", "llm_call")


@pytest.fixture
def metrics_conn():
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    yield c
    c.close()


@pytest.mark.parametrize("name", SPAN_NAMES)
def test_span_name_is_instrumented_somewhere(name):
    """Guard the names the frontend drill-down depends on. A rename that
    misses this list would leave the breakdown silently empty.

    Scans from the repo root derived off __file__, not the CWD: a
    CWD-relative grep passes or fails on where pytest was invoked from.
    """

    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "minerva"
    needle = f'sub_span("{name}"'
    found = any(needle in p.read_text(encoding="utf-8") for p in src.rglob("*.py"))
    assert found, f"no {needle}) call found under {src}"


def test_sub_spans_and_the_request_land_in_one_write(metrics_conn):
    from minerva.metrics.recorder import sub_span

    rec = Recorder(metrics_conn, now=lambda: 1_700_000_000.0)
    with rec.record("chunk syntax", "GET") as span:
        with sub_span("stanza_parse"):
            pass
        span.status = 200
    spans = {r[0] for r in metrics_conn.execute("SELECT span FROM request_timings")}
    assert spans == {"", "stanza_parse"}
