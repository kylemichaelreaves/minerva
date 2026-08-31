"""Concordance endpoints: lemma frequency index + KWIC detail.

Thin wrappers over :mod:`minerva.concordance.queries`; both use the
shared corpus lock so they don't race re-ingest / re-lemmatize.
"""

from __future__ import annotations

from typing import Any

from ...concordance import queries as concordance_queries
from ..server_core import ServerDeps
from ._locks import with_corpus_lock


@with_corpus_lock
def _handle_concordance_index(deps: ServerDeps, query: dict[str, str]) -> dict[str, Any]:
    return concordance_queries.lemma_index(deps.conn, query)


@with_corpus_lock
def _handle_concordance_lemma(deps: ServerDeps, query: dict[str, str]) -> dict[str, Any]:
    return concordance_queries.lemma_detail(deps.conn, query)
