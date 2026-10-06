"""Optional embedding backend.

If `sentence-transformers` is installed, we use it. Otherwise, calls into this
module raise a helpful error explaining that vector search is disabled and
lexical (BM25) retrieval still works.

The default model `paraphrase-multilingual-MiniLM-L12-v2` covers Greek and
English in one space, which matters because the Plato corpus is bilingual.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import numpy as np

# `name@revision`. Hugging Face resolves a bare name to whatever `main` is
# today, so an upstream push would silently encode new chunks into a
# different vector space from the stored ones (#500). The whole string is
# also the key `embeddings.model` stores and the incremental embed compares
# against, so bumping the pin re-encodes instead of mixing spaces. The
# revision is the snapshot that produced the 412,105 vectors in the index
# when the pin landed (2026-10-06); migration 0040 relabelled them with it.
DEFAULT_MODEL = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    "@e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
)


class EmbeddingsUnavailable(RuntimeError):
    pass


class Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingsUnavailable(
                "sentence-transformers is not installed. Install with "
                "`pip install -e '.[embed]'` to enable vector search; "
                "lexical (BM25) search still works without it."
            ) from exc
        self.model_name = model_name
        name, _, revision = model_name.partition("@")
        self._model = SentenceTransformer(name, revision=revision or None)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def encode(
        self,
        texts: Iterable[str],
        *,
        batch_size: int = 32,
        normalize: bool = True,
    ) -> np.ndarray:
        items = list(texts)
        if not items:
            return np.zeros((0, self.dim), dtype=np.float32)
        vecs = self._model.encode(
            items,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)


def cosine_search(
    query_vec: np.ndarray, matrix: np.ndarray, top_k: int
) -> tuple[np.ndarray, np.ndarray]:
    """Return (indices, scores) of top-k cosine matches.

    Both `query_vec` and `matrix` should be L2-normalized (default in `encode`),
    so the dot product is the cosine similarity.
    """

    if matrix.size == 0:
        return np.zeros((0,), dtype=np.int64), np.zeros((0,), dtype=np.float32)
    scores = matrix @ query_vec
    k = min(top_k, scores.shape[0])
    idx = np.argpartition(-scores, k - 1)[:k]
    idx = idx[np.argsort(-scores[idx])]
    return idx, scores[idx]


def batched(items: list, batch_size: int) -> Iterator[list]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]
