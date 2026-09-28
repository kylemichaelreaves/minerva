"""Shared cross-reference constants."""

from __future__ import annotations

CURATOR_STATUS_VALUES = ("approved", "rejected", "auto", "manual")

# Every write that decides a row's status also records who decided it
# and when — ``curated_by`` 'human' | 'llm' | 'embed' and ``curated_at``
# (#718, migration 0039). The stamp is spelled out literally in each
# UPDATE rather than interpolated from a constant here.
#
# Bulk verifiers never re-decide a row a person decided — whatever
# status the person left it in, 'auto' included.
NOT_HUMAN_CURATED = "xr.curated_by IS NOT 'human'"
