"""In-flight translation coalescing — one LLM call per cache key."""

from __future__ import annotations

import threading

_INFLIGHT_TRANSLATIONS: dict[tuple[str, str], threading.Event] = {}
_INFLIGHT_LOCK = threading.Lock()


def begin_inflight(cache_key: tuple[str, str]) -> threading.Event | None:
    """Register in-flight work. Returns an Event to wait on, or None if first."""

    with _INFLIGHT_LOCK:
        existing = _INFLIGHT_TRANSLATIONS.get(cache_key)
        if existing is not None:
            return existing
        _INFLIGHT_TRANSLATIONS[cache_key] = threading.Event()
        return None


def finish_inflight(cache_key: tuple[str, str]) -> None:
    """Release waiters and drop the in-flight entry."""

    with _INFLIGHT_LOCK:
        ev = _INFLIGHT_TRANSLATIONS.pop(cache_key, None)
    if ev is not None:
        ev.set()


def is_inflight(cache_key: tuple[str, str]) -> bool:
    """Return whether a translation for ``cache_key`` is still in progress."""

    with _INFLIGHT_LOCK:
        return cache_key in _INFLIGHT_TRANSLATIONS
