"""POST /api/translate — cached LLM translation for the reader."""

from __future__ import annotations

import time
from typing import Any

from ... import llm, translations
from ...errors import BadRequestError, PayloadTooLargeError
from ...translate.coalesce import begin_inflight, current_inflight, finish_inflight
from ...translate.parse import looks_like_refusal, parse_dual_translation
from ...translate.prompts import LANG_NAME, MAX_TRANSLATE_CHARS, TRANSLATE_SYSTEM
from ..server_core import ServerDeps
from ._locks import map_domain_errors

_FOLLOWER_WAIT_SLICE_S = 120.0
_FOLLOWER_WAIT_TOTAL_S = 240.0


def _cached_response(cached: dict[str, Any]) -> dict[str, Any]:
    return {
        "translated_text": cached["translated_text"],
        "literal_text": cached["literal_text"],
        "model": cached["model"],
        "cached": True,
    }


def _lookup_cached(deps: ServerDeps, source: str, target: str) -> dict[str, Any] | None:
    with deps.trans_lock:
        return translations.lookup(
            deps.translations_conn,
            source_text=source,
            target_lang=target,
        )


def _wait_for_leader(deps: ServerDeps, source: str, target: str, waiter) -> dict[str, Any] | None:
    """Follow an in-flight translation. Never duplicate the LLM call.

    Returns the cached response once the leader lands it, or None when
    no leader remains and no cache row appeared (leader failed or
    refused) — the caller decides whether to take over.
    """

    deadline = time.monotonic() + _FOLLOWER_WAIT_TOTAL_S
    while time.monotonic() < deadline:
        remaining = min(_FOLLOWER_WAIT_SLICE_S, deadline - time.monotonic())
        if remaining <= 0:
            break
        waiter.wait(timeout=remaining)
        cached = _lookup_cached(deps, source, target)
        if cached is not None:
            return _cached_response(cached)
        live = current_inflight((source, target))
        if live is None:
            return None
        # A leader is still registered — possibly a NEW one. Wait on the
        # live Event; re-waiting on a replaced, already-set Event would
        # turn this loop into a hot spin of DB lookups.
        waiter = live
    raise llm.LLMError("translation wait timed out")


def _leader_translate(
    deps: ServerDeps,
    *,
    source: str,
    target: str,
    cache_key: tuple[str, str],
    ev,
) -> dict[str, Any]:
    target_name = LANG_NAME.get(target, target)
    messages = [
        llm.Message(role="system", content=TRANSLATE_SYSTEM.format(target_lang_name=target_name)),
        llm.Message(role="user", content=source),
    ]
    try:
        raw = deps.backend.complete(messages, temperature=0.0).strip()
        literal_text, literary_text = parse_dual_translation(raw)
        if looks_like_refusal(literary_text) or looks_like_refusal(literal_text):
            # Deliberately NOT cached: refusals are usually transient
            # (model mood, truncated source), and translations.lookup
            # treats an empty-string row as a valid hit — caching one
            # poisoned the key forever (every later request returned
            # ``cached: true`` with an empty translation).
            return {
                "translated_text": "",
                "literal_text": "",
                "model": deps.backend.name,
                "cached": False,
            }
        with deps.trans_lock:
            translations.insert(
                deps.translations_conn,
                source_text=source,
                target_lang=target,
                translated_text=literary_text,
                literal_text=literal_text,
                model=deps.backend.name,
            )
        return {
            "translated_text": literary_text,
            "literal_text": literal_text,
            "model": deps.backend.name,
            "cached": False,
        }
    finally:
        finish_inflight(cache_key, ev)


@map_domain_errors
def _handle_translate(deps: ServerDeps, payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("source_text")
    target = payload.get("target_lang")
    if not isinstance(source, str) or not source.strip():
        raise BadRequestError("missing or empty 'source_text'")
    if len(source) > MAX_TRANSLATE_CHARS:
        raise PayloadTooLargeError(
            f"source_text exceeds {MAX_TRANSLATE_CHARS}-character limit",
        )
    if not isinstance(target, str) or target not in translations.SUPPORTED_LANGS:
        raise BadRequestError(
            f"target_lang must be one of {sorted(translations.SUPPORTED_LANGS)}",
        )

    cached = _lookup_cached(deps, source, target)
    if cached is not None:
        return _cached_response(cached)
    if deps.backend.name == "none":
        return {
            "translated_text": "(translation unavailable — server running with --llm none)",
            "literal_text": "",
            "model": "none",
            "cached": False,
        }

    cache_key = (source, target)
    for _attempt in range(2):
        is_leader, ev = begin_inflight(cache_key)
        if is_leader:
            return _leader_translate(
                deps,
                source=source,
                target=target,
                cache_key=cache_key,
                ev=ev,
            )
        hit = _wait_for_leader(deps, source, target, ev)
        if hit is not None:
            return hit
        cached = _lookup_cached(deps, source, target)
        if cached is not None:
            return _cached_response(cached)
        # The leader finished without landing a cache row (LLM error or
        # refusal). Loop and try to become the leader ourselves; only a
        # request whose begin_inflight said is_leader may call the LLM.
    raise llm.LLMError("translation repeatedly failed upstream")


# Re-export for tests importing `minerva.server._TRANSLATE_SYSTEM`, etc.
_LANG_NAME = LANG_NAME
_MAX_TRANSLATE_CHARS = MAX_TRANSLATE_CHARS
_TRANSLATE_SYSTEM = TRANSLATE_SYSTEM
