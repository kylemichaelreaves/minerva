"""Hybrid retrieval: SQLite FTS5 (BM25) fused with optional cosine search.

Returned `Hit` objects are already enriched with chunk metadata. The retriever
optionally expands each hit with its neighboring chunks within the same work
so the agent can quote across section boundaries.
"""

from __future__ import annotations

import dataclasses
import re
import sqlite3

import numpy as np

from . import embed, store

FTS_QUERY_SAFE = re.compile(r"[^\w\s]+", re.UNICODE)


@dataclasses.dataclass
class Hit:
    chunk_id: str
    score: float
    bm25: float
    cosine: float
    meta: dict


def _sanitize_fts_query(q: str) -> str:
    cleaned = FTS_QUERY_SAFE.sub(" ", q)
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"' for t in tokens)


def _lang_filter(lang: str | None) -> tuple[str, tuple]:
    if lang in {None, "any"}:
        return "", ()
    return " AND chunks.lang = ?", (lang,)


def _corpus_filter(corpus: str | None) -> tuple[str, tuple]:
    # `corpus` is the lowercased author name. With the chunks-redesign
    # of 0003, the column no longer lives on chunks; it's reconstructed
    # by the `chunks_full` view from works.author. Joining through
    # editions/translations to works would be cheaper but the view
    # keeps callers idiomatic and the planner inlines either way.
    if corpus in {None, "any"}:
        return "", ()
    return " AND cf.corpus = ?", (corpus,)


def _speaker_filter(speaker: str | None) -> tuple[str, tuple]:
    """Case-insensitive speaker filter; matches what `tei.py` records in
    `chunks.speaker` regardless of how the user types it.
    """

    if not speaker or speaker == "any":
        return "", ()
    return " AND chunks.speaker = ? COLLATE NOCASE", (speaker,)


def _bm25_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    top_k: int,
    lang: str | None,
    corpus: str | None,
    speaker: str | None,
    min_chunk_chars: int = 0,
) -> dict[str, float]:
    fts_q = _sanitize_fts_query(query)
    if not fts_q:
        return {}
    lang_sql, lang_params = _lang_filter(lang)
    corpus_sql, corpus_params = _corpus_filter(corpus)
    speaker_sql, speaker_params = _speaker_filter(speaker)
    # Floor on chunk length filters out scraper boilerplate, navigation
    # breadcrumbs, single-letter signatures, and section banners that
    # otherwise dominate vector retrieval on author-named queries.
    min_chars_sql = ""
    min_chars_params: tuple = ()
    if min_chunk_chars > 0:
        min_chars_sql = " AND length(chunks.text) >= ?"
        min_chars_params = (min_chunk_chars,)
    # Join through `chunks_full` only when we need the author/corpus
    # field — saves the planner from a useless JOIN on the common
    # "no corpus filter" path.
    full_join = " JOIN chunks_full cf ON cf.chunk_id = chunks.chunk_id" if corpus_sql else ""
    sql = (
        "SELECT chunks.chunk_id AS chunk_id, bm25(chunks_fts) AS rank "
        "FROM chunks_fts "
        "JOIN chunks ON chunks.rowid = chunks_fts.rowid" + full_join + " "
        "WHERE chunks_fts MATCH ?"
        + lang_sql + corpus_sql + speaker_sql + min_chars_sql + " "
        "ORDER BY rank ASC LIMIT ?"
    )
    rows = conn.execute(
        sql,
        (fts_q, *lang_params, *corpus_params, *speaker_params, *min_chars_params, top_k),
    ).fetchall()
    return {row[0]: -float(row[1]) for row in rows}


def _vector_search(
    conn: sqlite3.Connection,
    query_vec: np.ndarray,
    *,
    top_k: int,
    lang: str | None,
    corpus: str | None,
    speaker: str | None,
    min_chunk_chars: int = 0,
) -> dict[str, float]:
    ids, matrix = store.load_all_embeddings(conn)
    if not ids:
        return {}
    needs_filter = (
        lang not in {None, "any"}
        or corpus not in {None, "any"}
        or (bool(speaker) and speaker != "any")
        or min_chunk_chars > 0
    )
    if needs_filter:
        # Earlier this query bound one placeholder per chunk_id; with
        # 215k embeddings in the index SQLite hits its parameter cap
        # (~32k since 3.32, 999 before). A full table scan is cheap
        # here (chunks_full is small per-row) and dodges the cap
        # entirely. The Python-side filter still drops unmatched IDs.
        rows = conn.execute(
            "SELECT chunk_id, lang, corpus, speaker, length(text) FROM chunks_full"
        ).fetchall()
        meta_by_id = {r[0]: (r[1], r[2], r[3], r[4]) for r in rows}
        speaker_lower = speaker.lower() if speaker else None
        keep = np.array(
            [
                (lang in {None, "any"} or meta_by_id.get(cid, ("", "", "", 0))[0] == lang)
                and (corpus in {None, "any"} or meta_by_id.get(cid, ("", "", "", 0))[1] == corpus)
                and (
                    not speaker_lower
                    or speaker_lower == "any"
                    or (meta_by_id.get(cid, ("", "", "", 0))[2] or "").lower() == speaker_lower
                )
                and (
                    min_chunk_chars <= 0
                    or meta_by_id.get(cid, ("", "", "", 0))[3] >= min_chunk_chars
                )
                for cid in ids
            ],
            dtype=bool,
        )
        if not keep.any():
            return {}
        ids = [c for c, k in zip(ids, keep, strict=True) if k]
        matrix = matrix[keep]
    idx, scores = embed.cosine_search(query_vec, matrix, top_k)
    return {ids[i]: float(s) for i, s in zip(idx.tolist(), scores.tolist(), strict=True)}


def _normalize_scores(d: dict[str, float]) -> dict[str, float]:
    if not d:
        return {}
    values = np.array(list(d.values()), dtype=np.float64)
    lo, hi = float(values.min()), float(values.max())
    if hi - lo < 1e-9:
        return dict.fromkeys(d, 1.0)
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


def search(
    conn: sqlite3.Connection,
    query: str,
    *,
    top_k: int = 8,
    lang: str | None = "eng",
    corpus: str | None = None,
    speaker: str | None = None,
    embedder: embed.Embedder | None = None,
    fetch_pool: int = 32,
    bm25_weight: float = 0.5,
    vector_weight: float = 0.5,
    expand_neighbors: int = 1,
    min_chunk_chars: int = 60,
) -> list[Hit]:
    """Hybrid search returning at most `top_k` hits, optionally with neighbors.

    ``min_chunk_chars`` filters out chunks below that length from BOTH
    BM25 and vector retrieval. Default 60 excludes scraper boilerplate
    (navigation breadcrumbs, single-line signatures, section banners
    like "ETHICS BOOK I", repeated work titles) that otherwise dominate
    vector retrieval on author-named queries — e.g., "Friedrich
    Nietzsche" letter signatures outranked his actual philosophical
    passages on queries containing the name "Nietzsche". Pass 0 to
    disable when you specifically want to see those chunks (e.g.,
    a curation pass surfacing scrape garbage to delete).
    """

    bm25_raw = _bm25_search(
        conn, query, top_k=fetch_pool, lang=lang, corpus=corpus, speaker=speaker,
        min_chunk_chars=min_chunk_chars,
    )
    vec_raw: dict[str, float] = {}
    if embedder is not None and store.has_embeddings(conn):
        q_vec = embedder.encode([query])[0]
        vec_raw = _vector_search(
            conn, q_vec, top_k=fetch_pool, lang=lang, corpus=corpus, speaker=speaker,
            min_chunk_chars=min_chunk_chars,
        )

    bm25_n = _normalize_scores(bm25_raw)
    vec_n = _normalize_scores(vec_raw)

    if vec_n:
        ids = set(bm25_n) | set(vec_n)
        fused = {
            cid: bm25_weight * bm25_n.get(cid, 0.0) + vector_weight * vec_n.get(cid, 0.0)
            for cid in ids
        }
    else:
        fused = bm25_n

    ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]
    if not ranked:
        return []

    base_ids = [cid for cid, _ in ranked]
    expanded_ids: list[str] = []
    seen: set[str] = set()
    for cid in base_ids:
        for nid in store.neighbor_ids(conn, cid, window=expand_neighbors):
            if nid not in seen:
                seen.add(nid)
                expanded_ids.append(nid)

    metas = store.fetch_chunks(conn, expanded_ids)
    out: list[Hit] = []
    for cid in base_ids:
        meta_row = metas.get(cid)
        if meta_row is None:
            continue
        out.append(
            Hit(
                chunk_id=cid,
                score=fused.get(cid, 0.0),
                bm25=bm25_raw.get(cid, 0.0),
                cosine=vec_raw.get(cid, 0.0),
                meta=store.to_meta_dict(meta_row),
            )
        )
    return out


def expanded_passage(hit: Hit, conn: sqlite3.Connection, *, window: int = 1) -> str:
    """Concatenate `window` neighbors on each side of `hit` for richer context."""

    nbrs = store.neighbor_ids(conn, hit.chunk_id, window=window)
    rows = store.fetch_chunks(conn, nbrs)
    parts: list[str] = []
    for nid in nbrs:
        row = rows.get(nid)
        if row is None:
            continue
        loc = format_locator(store.to_meta_dict(row))
        parts.append(f"[{loc}] {row['text']}")
    return "\n\n".join(parts)


def format_locator(meta: dict) -> str:
    """Compose a human citation like `Plato, Republic 514a (Bk 7)`."""

    bits: list[str] = []
    author = meta.get("author") or ""
    work = meta.get("work") or ""
    if author and work:
        bits.append(f"{author}, {work}")
    elif work:
        bits.append(work)
    section = meta.get("section")
    if section:
        bits.append(section)
    book = meta.get("book")
    if book and (meta.get("work") or "").lower().startswith(("republic", "laws")):
        bits.append(f"Bk {book}")
    lang = meta.get("lang")
    if lang and lang != "eng":
        bits.append(f"[{lang}]")
    return " ".join(bits) if bits else "(unknown)"
