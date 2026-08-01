"""HTTP entry for ``minerva serve`` — re-exports transport and handler surface.

Transport (``ChatHandler``, CORS, static SPA, ``serve()``) lives in
``http/serve.py``. Handler implementations live in ``http/handlers/``.
"""

from __future__ import annotations

from .http.handlers import (  # noqa: F401
    _CORPUS_TO_DOMINANT,
    _LANG_NAME,
    _MAX_TRANSLATE_CHARS,
    _PASSAGE_PREVIEW_CHARS,
    _TRANSLATE_SYSTEM,
    _answer_to_json,
    _build_retrieval_query,
    _dominant_from_hits,
    _dominant_from_response,
    _handle_chat,
    _handle_chat_stream,
    _handle_chunk_context,
    _handle_chunk_references,
    _handle_conversation_delete,
    _handle_conversation_get,
    _handle_conversations_list,
    _handle_health,
    _handle_landing_stats,
    _handle_lemma_highlights,
    _handle_network_summary,
    _handle_reference_update,
    _handle_references_list,
    _handle_references_sources,
    _handle_review_queue,
    _handle_term_by_id,
    _handle_terms_by_chunk,
    _handle_terms_list,
    _handle_translate,
    _handle_translation_renderings,
    _handle_word_lookup,
    _handle_work_occurrence_map,
    _handle_work_occurrences,
    _handle_work_range,
    _handle_work_references_map,
    _handle_works_list,
    _history_from_payload,
    _hit_to_citation,
    _pinned_ids_from_payload,
    _resolve_pinned,
)
from .http.serve import (  # noqa: F401
    _MAX_REQUEST_BYTES,
    ChatHandler,
    _cors_headers,
    _dispatch_json_mutation,
    _parse_content_length,
    _read_json_body,
    make_handler,
    serve,
)
from .http.server_core import (  # noqa: F401
    _BUCKET_SWEEP_INTERVAL,
    _MAX_BUCKETS,
    _RATE_LIMITS,
    ServerDeps,
    _HTTPError,
    _RateLimiter,
)
