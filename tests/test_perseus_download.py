"""Tests for ``perseus/_download.py`` — RateLimiter + fetch_parallel.

End-to-end ``fetch_with_retry`` against a live server is out of scope
(every CI run would be at the mercy of zeno.org). These tests pin
the load-bearing logic — per-host rate limiting and parallel-fetch
result ordering — using monkeypatched callables. The full retry path
was exercised against zeno during the migration smoke test.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest


@pytest.fixture
def download_mod():
    """Import ``perseus._download`` despite perseus/ lacking
    __init__.py. Inject the perseus directory onto sys.path the
    same way Python does when you run a script from there."""

    perseus_dir = Path(__file__).resolve().parents[1] / "perseus"
    sys.path.insert(0, str(perseus_dir))
    try:
        import _download  # type: ignore

        yield _download
    finally:
        sys.path.remove(str(perseus_dir))
        sys.modules.pop("_download", None)


def test_rate_limiter_separates_same_host_calls(download_mod):
    """Two acquires for the same host must be separated by at least
    ``min_interval`` seconds. Different hosts are independent."""

    rl = download_mod.RateLimiter(min_interval=0.05)
    t0 = time.monotonic()
    rl.acquire("a.example")
    rl.acquire("a.example")  # second call should sleep ~0.05s
    elapsed_same = time.monotonic() - t0

    t1 = time.monotonic()
    rl.acquire("b.example")  # different host — no wait
    elapsed_other = time.monotonic() - t1

    assert elapsed_same >= 0.045, (
        f"second same-host acquire returned in {elapsed_same:.3f}s; expected at least min_interval"
    )
    assert elapsed_other < 0.02, (
        f"different-host acquire blocked for {elapsed_other:.3f}s; limiters should be per-host"
    )


def test_fetch_parallel_preserves_input_order(monkeypatch, download_mod):
    """Results must zip 1:1 against input order regardless of which
    worker finishes when. Stub ``fetch_with_retry`` to a sleep-
    ordered identity so the call order is non-trivial."""

    def fake_fetch(url, **kwargs):
        del kwargs
        # Earlier URLs sleep longer so they finish later — the test
        # would fail if `fetch_parallel` returned results in
        # completion order instead of input order.
        i = int(url.rsplit("-", 1)[-1])
        time.sleep(0.02 * (5 - i))
        return f"html-{i}"

    monkeypatch.setattr(download_mod, "fetch_with_retry", fake_fetch)

    urls = [f"http://h/p-{i}" for i in range(5)]
    results = download_mod.fetch_parallel(urls, jobs=4)
    assert [u for u, _ in results] == urls
    assert [r for _, r in results] == [f"html-{i}" for i in range(5)]


def test_fetch_with_retry_decodes(monkeypatch, download_mod):
    """``fetch_with_retry`` is a thin decode wrapper over bytes fetch."""

    monkeypatch.setattr(download_mod, "fetch_bytes_with_retry", lambda url, **kw: b"hello")
    assert download_mod.fetch_with_retry("http://x", encoding="utf-8") == "hello"


def test_fetch_bytes_passes_extra_headers(monkeypatch, download_mod):
    """Per-request headers merge with User-Agent for site-specific fetchers."""

    seen: dict[str, object] = {}

    class FakeResp:
        def read(self):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout):
        del timeout
        seen["headers"] = dict(req.headers)
        return FakeResp()

    monkeypatch.setattr(download_mod.urllib.request, "urlopen", fake_urlopen)
    download_mod.fetch_bytes_with_retry(
        "http://example.test/x",
        extra_headers={"Referer": "https://www.perseus.tufts.edu/"},
        retries=1,
    )
    assert seen["headers"]["Referer"] == "https://www.perseus.tufts.edu/"


def test_fetch_parallel_returns_exceptions_not_raises(monkeypatch, download_mod):
    """One failing URL must not kill the batch. Errors come back in
    the result tuple so the caller decides what to do."""

    def fake_fetch(url, **kwargs):
        del kwargs
        if "bad" in url:
            raise RuntimeError("simulated failure")
        return f"ok-{url}"

    monkeypatch.setattr(download_mod, "fetch_with_retry", fake_fetch)

    results = download_mod.fetch_parallel(
        ["http://a/good", "http://a/bad", "http://a/also-good"],
        jobs=2,
    )
    assert isinstance(results[0][1], str) and results[0][1] == "ok-http://a/good"
    assert isinstance(results[1][1], RuntimeError)
    assert isinstance(results[2][1], str)


def test_fetch_bytes_rejects_small_body(monkeypatch, download_mod):
    class FakeResp:
        def read(self):
            return b"tiny"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(download_mod.urllib.request, "urlopen", lambda req, timeout: FakeResp())
    with pytest.raises(RuntimeError, match="too small"):
        download_mod.fetch_bytes_with_retry("http://example.test/x", retries=1, min_bytes=100)


def test_fetch_bytes_rejects_marker(monkeypatch, download_mod):
    body = b"x" * 500 + b"Hier entsteht eine neue Homepage"

    class FakeResp:
        def read(self):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(download_mod.urllib.request, "urlopen", lambda req, timeout: FakeResp())
    with pytest.raises(RuntimeError, match="rejected"):
        download_mod.fetch_bytes_with_retry(
            "http://example.test/x",
            retries=1,
            reject_markers=("Hier entsteht eine neue Homepage",),
        )


class TestFailureAccumulator:
    """The shared collector #316 asks for: a `main()` appends
    (label, reason) pairs for per-item failures and asks for a summary
    + exit code, instead of each script hand-writing PR #315's shape.
    """

    def test_empty_accumulator_exits_zero_and_prints_nothing(self, capsys, download_mod):
        acc = download_mod.FailureAccumulator()
        assert acc.exit_code() == 0
        assert capsys.readouterr().out == ""

    def test_recording_a_failure_prints_it_immediately(self, capsys, download_mod):
        acc = download_mod.FailureAccumulator()
        acc.record("Gen.xml", "HTTP 404")
        out = capsys.readouterr().out
        assert "Gen.xml" in out
        assert "HTTP 404" in out

    def test_any_recorded_failure_makes_exit_code_nonzero(self, download_mod):
        acc = download_mod.FailureAccumulator()
        acc.record("Gen.xml", "HTTP 404")
        assert acc.exit_code() != 0

    def test_exit_code_lists_every_failure_not_just_the_count(self, capsys, download_mod):
        acc = download_mod.FailureAccumulator()
        acc.record("Gen.xml", "HTTP 404")
        acc.record("Exod.xml", "HTTP 500")
        capsys.readouterr()  # drop the per-record prints
        acc.exit_code()
        out = capsys.readouterr().out
        assert "Gen.xml" in out
        assert "Exod.xml" in out
        assert "2" in out

    def test_len_reflects_recorded_failures(self, download_mod):
        acc = download_mod.FailureAccumulator()
        assert len(acc) == 0
        acc.record("Gen.xml", "HTTP 404")
        assert len(acc) == 1
