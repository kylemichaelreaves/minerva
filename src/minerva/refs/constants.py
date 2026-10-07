"""Shared cross-reference constants."""

from __future__ import annotations

CURATOR_STATUS_VALUES = ("approved", "rejected", "auto", "manual")

# Who decided a row (#718, migration 0039's CHECK). NULL means no verdict
# was recorded — 5,076 of the rejections predate the column — so readers
# render it "unrecorded", never "machine" (#720). ``refs list
# --curated-by none`` selects it.
CURATED_BY_VALUES = ("human", "llm", "embed")

# Every write that decides a row's status also records who decided it
# and when — ``curated_by`` 'human' | 'llm' | 'embed' and ``curated_at``
# (#718, migration 0039). The stamp is spelled out literally in each
# UPDATE rather than interpolated from a constant here.
#
# Bulk verifiers never re-decide a row a person decided — whatever
# status the person left it in, 'auto' included.
NOT_HUMAN_CURATED = "xr.curated_by IS NOT 'human'"

# The person a cross-reference is credited to (#710): the source chunk's
# ``attributed_to`` when an editor, translator or transcriber wrote it,
# otherwise the source work's author. Every view that credits a citation
# to a source author reads this — the Network page, ``/api/references``
# and its source picker, the review queue, ``refs list``, ``refs review``
# and the llm-verify judge's ``source_author``. Operator *scopes*
# (``refs build --source-author``, the verifiers' filters) keep reading
# ``works.author``: they select a corpus to process, not a person.
# Needs ``chunks c`` and ``works src_work`` in scope.
SOURCE_AUTHOR = "COALESCE(c.attributed_to, src_work.author)"
