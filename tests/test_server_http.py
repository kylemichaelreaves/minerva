"""HTTP-plumbing tests for the `minerva serve` shim: the in-process rate
limiter and the CORS-header logic. Split from `test_server.py` so the
chat/handler tests stay focused on application behaviour."""

from __future__ import annotations

from conftest import StubBackend
from conftest import make_deps as _make_deps

from minerva import server


def _make_deps_with_limiter(populated_db, backend, **kwargs):
    """Start each rate-limiter test with a fresh limiter so per-IP /
    per-route bucket counts don't bleed across cases."""

    deps = _make_deps(populated_db, backend, **kwargs)
    deps.rate_limiter = server._RateLimiter()
    return deps


# ---------- Rate limiting ----------


def test_rate_limiter_allows_under_cap(populated_db):
    backend = StubBackend(reply="ok")
    deps = _make_deps_with_limiter(populated_db, backend)
    for _ in range(5):
        assert deps.rate_limiter.allow("chat", "1.2.3.4") is True


def test_rate_limiter_blocks_over_cap(populated_db):
    backend = StubBackend(reply="ok")
    deps = _make_deps_with_limiter(populated_db, backend)
    cap, _ = server._RATE_LIMITS["chat"]
    for _ in range(cap):
        assert deps.rate_limiter.allow("chat", "1.2.3.4") is True
    assert deps.rate_limiter.allow("chat", "1.2.3.4") is False


def test_rate_limiter_isolates_ips(populated_db):
    backend = StubBackend(reply="ok")
    deps = _make_deps_with_limiter(populated_db, backend)
    cap, _ = server._RATE_LIMITS["chat"]
    for _ in range(cap):
        deps.rate_limiter.allow("chat", "1.1.1.1")
    # Different IP is unaffected.
    assert deps.rate_limiter.allow("chat", "2.2.2.2") is True


def test_rate_limiter_isolates_routes(populated_db):
    backend = StubBackend(reply="ok")
    deps = _make_deps_with_limiter(populated_db, backend)
    cap_chat, _ = server._RATE_LIMITS["chat"]
    for _ in range(cap_chat):
        deps.rate_limiter.allow("chat", "1.1.1.1")
    # /api/translate has its own bucket.
    assert deps.rate_limiter.allow("translate", "1.1.1.1") is True


def test_rate_limiter_window_expires(populated_db):
    backend = StubBackend(reply="ok")
    deps = _make_deps_with_limiter(populated_db, backend)
    cap, window = server._RATE_LIMITS["chat"]
    # Fill the bucket at t=0.
    for _ in range(cap):
        assert deps.rate_limiter.allow("chat", "1.1.1.1", now=0.0) is True
    assert deps.rate_limiter.allow("chat", "1.1.1.1", now=0.0) is False
    # After the window slides past, requests are allowed again.
    assert deps.rate_limiter.allow("chat", "1.1.1.1", now=window + 1.0) is True


def test_rate_limiter_drains_expired_timestamps(populated_db):
    """A hit older than the window is popped when that same key sends
    again, so a long-lived caller's deque stays bounded by `cap`.

    This pins *draining*, not eviction: it indexes `_buckets[key]`, so
    it requires the bucket to still be there. It was called
    `..._evicts_drained_buckets` until #161 — a name that reads as
    coverage of the #121 bucket leak while asserting nearly its
    opposite. Eviction is pinned by `..._sweeps_idle_buckets` (#155);
    disable the `_sweep` delete and that test fails while this one
    still passes.
    """

    rl = server._RateLimiter()
    _cap, window = server._RATE_LIMITS["chat"]

    rl.allow("chat", "1.1.1.1", now=0.0)
    rl.allow("chat", "1.1.1.1", now=window + 1.0)

    # The t=0.0 hit aged out; only the second remains.
    assert list(rl._buckets[("chat", "1.1.1.1")]) == [window + 1.0]


def test_rate_limiter_sweeps_idle_buckets(populated_db):
    """A key whose timestamps have all aged out must be removed, not
    left behind (#121).

    The old code drained expired timestamps but only when that same IP
    sent another request, and then re-stored the empty deque. An IP
    that stopped sending kept its entry forever — unbounded growth
    keyed on an attacker-chosen value under `serve --host 0.0.0.0`.
    """

    rl = server._RateLimiter()
    rl.allow("chat", "1.1.1.1", now=0.0)
    assert ("chat", "1.1.1.1") in rl._buckets

    # A request from a different IP, far enough out that the sweep runs.
    rl.allow("chat", "2.2.2.2", now=server._BUCKET_SWEEP_INTERVAL + 1.0)

    assert ("chat", "1.1.1.1") not in rl._buckets, "idle bucket was never evicted"
    assert ("chat", "2.2.2.2") in rl._buckets


def test_rate_limiter_bucket_count_is_bounded(populated_db):
    """An IP-rotating client must not be able to grow `_buckets`
    without bound between sweeps."""

    rl = server._RateLimiter()
    for i in range(server._MAX_BUCKETS * 2):
        rl.allow("chat", f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}", now=0.0)

    assert len(rl._buckets) <= server._MAX_BUCKETS


def test_rate_limiter_active_bucket_survives_sweep(populated_db):
    """The sweep must not drop a bucket that is still inside its own
    window — that would hand out free capacity to a client already at
    its cap.

    The sweep interval (300s) is longer than the chat window (60s), so
    the bucket has to be filled just *before* a sweep boundary to still
    be live when the sweep runs.
    """

    rl = server._RateLimiter()
    cap, window = server._RATE_LIMITS["chat"]
    sweep = server._BUCKET_SWEEP_INTERVAL

    rl.allow("chat", "9.9.9.9", now=0.0)  # first call arms the sweep clock

    # Fill the cap one second before the sweep fires.
    for _ in range(cap):
        assert rl.allow("chat", "1.1.1.1", now=sweep - 1.0) is True

    # This call triggers the sweep; 1.1.1.1 is still well inside its window.
    assert sweep - (sweep - 1.0) < window
    rl.allow("chat", "8.8.8.8", now=sweep)

    assert ("chat", "1.1.1.1") in rl._buckets
    assert rl.allow("chat", "1.1.1.1", now=sweep) is False


def test_rate_limiter_unknown_route_always_allows(populated_db):
    backend = StubBackend()
    deps = _make_deps_with_limiter(populated_db, backend)
    # Routes without an entry in `_RATE_LIMITS` (e.g. /api/works) are
    # not subject to the limiter; that's intentional — those are cheap.
    for _ in range(10_000):
        assert deps.rate_limiter.allow("/api/works", "1.1.1.1") is True


# ---------- CORS hardening ----------


def test_cors_loopback_allows_default_vite_origin(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    deps.cors_wildcard = False
    deps.allowed_origins = frozenset({"http://localhost:5173"})
    h = server._cors_headers(deps, origin="http://localhost:5173")
    assert h["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert h["Vary"] == "Origin"


def test_cors_loopback_rejects_unlisted_origin(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    deps.cors_wildcard = False
    deps.allowed_origins = frozenset({"http://localhost:5173"})
    h = server._cors_headers(deps, origin="https://attacker.example")
    assert "Access-Control-Allow-Origin" not in h


def test_cors_non_local_with_allow_list_echoes_matching_origin(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    deps.cors_wildcard = False
    deps.allowed_origins = frozenset({"https://trusted.example"})
    h = server._cors_headers(deps, origin="https://trusted.example")
    assert h["Access-Control-Allow-Origin"] == "https://trusted.example"
    assert h["Vary"] == "Origin"


def test_cors_non_local_without_match_omits_allow_origin(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    deps.cors_wildcard = False
    deps.allowed_origins = frozenset({"https://trusted.example"})
    h = server._cors_headers(deps, origin="https://attacker.example")
    # Browsers fall through to same-origin policy when ACAO is missing.
    assert "Access-Control-Allow-Origin" not in h


def test_cors_non_local_empty_allow_list_emits_nothing(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    deps.cors_wildcard = False
    deps.allowed_origins = frozenset()
    h = server._cors_headers(deps, origin="https://anything.example")
    assert "Access-Control-Allow-Origin" not in h


def test_cors_allow_methods_includes_patch(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    h = server._cors_headers(deps, origin=None)
    assert "PATCH" in h["Access-Control-Allow-Methods"]
