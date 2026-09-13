"""Request-timing metrics: bucket math, a durable store, and the recorder.

Kept in its own database file rather than a table in the corpus index.
`minerva index --reset` unlinks the index file outright (`store.reset_db`),
and a `--reset` re-index is exactly the event whose latency impact these
numbers exist to bracket. The sibling modules `conversations`,
`translations` and `concept_cache` are separate files for the same reason —
see the `--conversations-db` help text in `cli/serve_cmd.py`.
"""

from __future__ import annotations

from .histogram import BUCKET_COUNT, BUCKET_UPPER_MS, bucket_index, quantile

__all__ = ["BUCKET_COUNT", "BUCKET_UPPER_MS", "bucket_index", "quantile"]
