"""Per-endpoint request handlers for the `minerva serve` HTTP shim.

Each module here is one API surface area: `chat`, `conversations`,
`translate`, `reader`, `terms`, `health`. `citations` holds the
response-shaping helpers that span chat (and only chat today, but
factored out so future endpoints emitting Hit-shaped JSON can share).

`server.py` re-exports every name below at `minerva.server.<name>`,
which is the path tests use. That layering means we can move handlers
around in here without touching the test suite.
"""

from __future__ import annotations

from ... import chat_service
from ...citations import (  # noqa: F401
    _dominant_from_hits,
    _dominant_from_response,
    _hit_to_citation,
    citations_from_hits,
)
from ...corpus_registry import CORPUS_TO_DOMINANT as _CORPUS_TO_DOMINANT  # noqa: F401
from ..server_core import ServerDeps as ServerDeps
from ..server_core import _HTTPError as _HTTPError
from .chat import (  # noqa: F401
    _handle_chat,
    _handle_chat_stream,
)
from .concordance import (  # noqa: F401
    _handle_concordance_index,
    _handle_concordance_lemma,
)
from .conversations import (  # noqa: F401
    _handle_conversation_delete,
    _handle_conversation_get,
    _handle_conversations_list,
)
from .health import _handle_health, _handle_landing_stats  # noqa: F401
from .reader import (  # noqa: F401
    _handle_chunk_context,
    _handle_lemma_highlights,
    _handle_word_lookup,
    _handle_work_range,
    _handle_works_list,
)
from .references import (  # noqa: F401
    _handle_chunk_references,
    _handle_network_summary,
    _handle_reference_update,
    _handle_references_list,
    _handle_references_sources,
    _handle_review_queue,
    _handle_work_references_map,
)
from .syntax import (  # noqa: F401
    _handle_chunk_syntax,
    _handle_syntax_correction_create,
    _handle_syntax_correction_delete,
)
from .terms import (  # noqa: F401
    _handle_term_by_id,
    _handle_terms_by_chunk,
    _handle_terms_list,
    _handle_translation_renderings,
    _handle_work_occurrence_map,
    _handle_work_occurrences,
)
from .translate import (  # noqa: F401
    _LANG_NAME,
    _MAX_TRANSLATE_CHARS,
    _TRANSLATE_SYSTEM,
    _handle_translate,
)

_PASSAGE_PREVIEW_CHARS = 280

# Back-compat aliases for tests importing `minerva.server._answer_to_json`.
_answer_to_json = chat_service.answer_to_json
_build_retrieval_query = chat_service.build_retrieval_query
_history_from_payload = chat_service.history_from_payload
_pinned_ids_from_payload = chat_service.pinned_ids_from_payload
_resolve_pinned = chat_service.resolve_pinned
