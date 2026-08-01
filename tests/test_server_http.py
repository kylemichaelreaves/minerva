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


def test_rate_limiter_evicts_drained_buckets(populated_db):
    deps = _make_deps(populated_db, StubBackend())
    rl = server._RateLimiter()
    rl.allow("chat", "1.1.1.1", now=0.0)
    rl.allow("chat", "1.1.1.1", now=61.0)
    assert len(rl._buckets[("chat", "1.1.1.1")]) == 1


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
