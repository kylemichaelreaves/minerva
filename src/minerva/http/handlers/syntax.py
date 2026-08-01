"""GET /api/chunks/{id}/syntax — dependency trees for one chunk.

Parses on first request and caches; every later call is a read. The response
is the *materialised* tree — the machine parse with hand corrections replayed
over it — and each token reports whether a human has touched it, so the client
can colour by epistemic status without re-deriving anything.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from ...syntax import queries as syntax_queries
from ..server_core import ServerDeps, _HTTPError
from ._locks import with_corpus_lock


def _token_json(tok: syntax_queries.SyntaxToken) -> dict[str, Any]:
    return {
        "id": tok.tok_id,
        "form": tok.form,
        "lemma": tok.lemma,
        "upos": tok.upos,
        "feats": tok.feats,
        "head": tok.head,
        "deprel": tok.deprel,
        "start": tok.surface_start,
        "end": tok.surface_end,
        "corrected": tok.corrected,
    }


@with_corpus_lock
def _handle_chunk_syntax(deps: ServerDeps, chunk_id: str) -> dict[str, Any]:
    tokens = syntax_queries.load_or_parse(deps.conn, chunk_id)
    if tokens is None:
        raise _HTTPError(HTTPStatus.NOT_FOUND, "chunk not found")

    corrections = syntax_queries.load_corrections(deps.conn, chunk_id)
    merged = syntax_queries.materialise(tokens, corrections)

    # Group into sentences. Tokens arrive ordered by (sent_ord, tok_id), so a
    # single pass suffices; sentence ordinals are contiguous from 0.
    sentences: list[dict[str, Any]] = []
    for tok in merged:
        if not sentences or sentences[-1]["sent_ord"] != tok.sent_ord:
            sentences.append({"sent_ord": tok.sent_ord, "tokens": []})
        sentences[-1]["tokens"].append(_token_json(tok))

    return {
        "chunk_id": chunk_id,
        "sentences": sentences,
        "corrections": len(corrections),
    }
