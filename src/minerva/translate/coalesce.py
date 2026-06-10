"""In-flight translation coalescing — one LLM call per cache key.

Leadership is explicit: ``begin_inflight`` tells the caller whether it
IS the leader (and hands it the Event it must release via
``finish_inflight``) or a follower (and hands it the leader's Event to
wait on). ``finish_inflight`` releases only the entry the caller
registered, so a stale or confused caller can never pop a newer
leader's Event and prematurely release its followers.
"""

from __future__ import annotations

import threading

_INFLIGHT_TRANSLATIONS: dict[tuple[str, str], threading.Event] = {}
_INFLIGHT_LOCK = threading.Lock()


def begin_inflight(cache_key: tuple[str, str]) -> tuple[bool, threading.Event]:
    """Try to become the leader for ``cache_key``.

    Returns ``(is_leader, event)``. The leader must call
    ``finish_inflight(cache_key, event)`` when done (success or
    failure); followers wait on the returned event.
    """

    with _INFLIGHT_LOCK:
        existing = _INFLIGHT_TRANSLATIONS.get(cache_key)
        if existing is not None:
            return False, existing
        ev = threading.Event()
        _INFLIGHT_TRANSLATIONS[cache_key] = ev
        return True, ev


def finish_inflight(cache_key: tuple[str, str], ev: threading.Event) -> None:
    """Release waiters on ``ev`` and drop the in-flight entry — but only
    if ``ev`` is still the registered entry for ``cache_key``."""

    with _INFLIGHT_LOCK:
        if _INFLIGHT_TRANSLATIONS.get(cache_key) is ev:
            del _INFLIGHT_TRANSLATIONS[cache_key]
    ev.set()


def current_inflight(cache_key: tuple[str, str]) -> threading.Event | None:
    """The live leader's Event for ``cache_key``, or None when no
    translation is in progress. Followers re-fetch this after a wait so
    a leader change hands them the NEW (unset) Event instead of leaving
    them spinning on the old, already-set one."""

    with _INFLIGHT_LOCK:
        return _INFLIGHT_TRANSLATIONS.get(cache_key)
