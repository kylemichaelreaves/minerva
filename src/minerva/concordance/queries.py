"""Concordance read queries — lemma index + KWIC.

Public API re-exported from :mod:`index_queries` and :mod:`kwic_queries`.
"""

from __future__ import annotations

from .index_queries import lemma_index
from .kwic_queries import lemma_detail

__all__ = ["lemma_detail", "lemma_index"]
