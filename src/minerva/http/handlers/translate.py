"""POST /api/translate — cached LLM translation for the reader."""

from __future__ import annotations

from typing import Any

from ... import llm, translations
from ...errors import BadRequestError, PayloadTooLargeError
from ...translate.coalesce import begin_inflight, finish_inflight
from ...translate.parse import looks_like_refusal, parse_dual_translation
from ...translate.prompts import LANG_NAME, MAX_TRANSLATE_CHARS, TRANSLATE_SYSTEM
from ..server_core import ServerDeps
from ._locks import map_domain_errors


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

    with deps.trans_lock:
        cached = translations.lookup(deps.translations_conn, source_text=source, target_lang=target)
    if cached is not None:
        return {
            "translated_text": cached["translated_text"],
            "literal_text": cached["literal_text"],
            "model": cached["model"],
            "cached": True,
        }
    if deps.backend.name == "none":
        return {
            "translated_text": "(translation unavailable — server running with --llm none)",
            "literal_text": "",
            "model": "none",
            "cached": False,
        }

    cache_key = (source, target)
    waiter = begin_inflight(cache_key)
    if waiter is not None:
        waiter.wait(timeout=120.0)
        with deps.trans_lock:
            cached = translations.lookup(
                deps.translations_conn, source_text=source, target_lang=target,
            )
        if cached is not None:
            return {
                "translated_text": cached["translated_text"],
                "literal_text": cached["literal_text"],
                "model": cached["model"],
                "cached": True,
            }

    target_name = LANG_NAME.get(target, target)
    messages = [
        llm.Message(role="system", content=TRANSLATE_SYSTEM.format(target_lang_name=target_name)),
        llm.Message(role="user", content=source),
    ]
    try:
        raw = deps.backend.complete(messages, temperature=0.0).strip()
        literal_text, literary_text = parse_dual_translation(raw)
        if looks_like_refusal(literary_text) or looks_like_refusal(literal_text):
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
        finish_inflight(cache_key)


# Re-export for tests importing `minerva.server._TRANSLATE_SYSTEM`, etc.
_LANG_NAME = LANG_NAME
_MAX_TRANSLATE_CHARS = MAX_TRANSLATE_CHARS
_TRANSLATE_SYSTEM = TRANSLATE_SYSTEM
