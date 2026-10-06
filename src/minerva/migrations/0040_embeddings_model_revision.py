"""0040_embeddings_model_revision.py — pin stored vectors to a revision (#500).

`embeddings.model` held the bare Hugging Face name, which resolves to
whatever `main` is when the model loads. `embed.DEFAULT_MODEL` is now
`name@revision`, and the incremental embed re-encodes any row whose
`model` differs from the one in use. Without this relabel, every existing
row would read as stale and the next `minerva embed` would re-encode the
whole corpus to arrive at the same vectors.

The revision asserted here is the only snapshot of the model the index
was ever built with on the machine that built it: the HF cache held exactly
one, `e8f8c21…`, which was also `refs/main` on 2026-10-06. A database built
elsewhere from a different snapshot would be mislabelled by this; that is
the cost of not re-encoding 412,105 chunks to prove it.

Idempotent: it only touches rows still carrying the bare name.
"""

from __future__ import annotations

import sqlite3

_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_PINNED = f"{_NAME}@e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


def apply(conn: sqlite3.Connection) -> int | None:
    changed = conn.execute(
        "UPDATE embeddings SET model = ? WHERE model = ?", (_PINNED, _NAME)
    ).rowcount
    conn.execute(
        "UPDATE meta SET value = ? WHERE key = 'embeddings.model' AND value = ?",
        (_PINNED, _NAME),
    )
    # None, not 0, when there was nothing to relabel: a fresh or
    # never-embedded database is "not applicable", not a failed repair.
    return changed or None
