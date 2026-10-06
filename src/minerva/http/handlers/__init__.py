"""Per-endpoint request handlers for the `minerva serve` HTTP shim.

Each module here is one API surface area: `chat`, `conversations`,
`translate`, `reader`, `terms`, `health`. `citations` holds the
response-shaping helpers that span chat (and only chat today, but
factored out so future endpoints emitting Hit-shaped JSON can share).

This `__init__` re-exports every `_handle_*` function, which is the
surface `router.py`, `serve.py` and the handler tests import. That
layering means we can move handlers between modules in here without
touching either.
"""

from __future__ import annotations

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
from .metrics import (  # noqa: F401
    _handle_metrics_requests,
    _handle_metrics_series,
    _handle_metrics_summary,
)
from .reader import (  # noqa: F401
    _handle_chunk_context,
    _handle_lemma_highlights,
    _handle_word_lookup,
    _handle_work_range,
    _handle_work_range_by_slug,
    _handle_works_list,
)
from .references import (  # noqa: F401
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
    _handle_work_occurrence_map,
)
from .translate import _handle_translate  # noqa: F401
