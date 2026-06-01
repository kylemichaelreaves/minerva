"""Response shaping for retrieval hits.

`_hit_to_citation` turns a `retrieve.Hit` into the JSON shape the
frontend renders in the margin column. `_dominant_from_hits` picks
the corpus glyph (Π / Α / H / K) shown at the top of the chat
response.
"""

from __future__ import annotations

import re
from typing import Any

from . import retrieve
from .corpus_registry import CORPUS_TO_DOMINANT as _CORPUS_TO_DOMINANT

_PASSAGE_PREVIEW_CHARS = 280


def citations_from_hits(
    pinned: list[retrieve.Hit],
    hits: list[retrieve.Hit],
) -> list[dict[str, Any]]:
    """Build numbered citation dicts: pinned first, then retrieval hits."""

    citations: list[dict[str, Any]] = []
    n = 1
    for h in pinned:
        citations.append(_hit_to_citation(h, n, pinned=True))
        n += 1
    for h in hits:
        citations.append(_hit_to_citation(h, n, pinned=False))
        n += 1
    return citations


def _hit_to_citation(hit: retrieve.Hit, n: int, *, pinned: bool = False) -> dict[str, Any]:
    text = hit.meta["text"]
    if len(text) > _PASSAGE_PREVIEW_CHARS:
        text = text[:_PASSAGE_PREVIEW_CHARS].rstrip() + " […]"
    return {
        "n": n,
        "chunk_id": hit.chunk_id,
        "src": retrieve.format_locator(hit.meta),
        "speaker": hit.meta.get("speaker"),
        "text": text,
        "score": round(hit.score, 4),
        "pinned": pinned,
    }


def _dominant_from_hits(hits: list[retrieve.Hit], *, top_n: int = 3) -> str:
    if not hits:
        return "P"
    counts: dict[str, int] = {}
    for h in hits[:top_n]:
        corpus = (h.meta.get("corpus") or "").lower()
        code = _CORPUS_TO_DOMINANT.get(corpus)
        if code is not None:
            counts[code] = counts.get(code, 0) + 1
    if not counts:
        return "P"
    top_corpus = (hits[0].meta.get("corpus") or "").lower()
    top_code = _CORPUS_TO_DOMINANT.get(top_corpus)
    return max(counts, key=lambda c: (counts[c], 1 if c == top_code else 0))


_CITE_MARKER_RE = re.compile(r"\[(\d+)\]")


def _dominant_from_response(
    response_text: str,
    pinned: list[retrieve.Hit],
    hits: list[retrieve.Hit],
) -> str:
    ordered = [*pinned, *hits]
    if not ordered:
        return "P"
    cited_ns: set[int] = set()
    for m in _CITE_MARKER_RE.finditer(response_text):
        try:
            cited_ns.add(int(m.group(1)))
        except ValueError:
            continue
    cited_hits = [ordered[n - 1] for n in sorted(cited_ns) if 1 <= n <= len(ordered)]
    if cited_hits:
        return _dominant_from_hits(cited_hits, top_n=len(cited_hits))
    return _dominant_from_hits(hits or pinned)
