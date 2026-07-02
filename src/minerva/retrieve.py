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

from . import embed, orthography, store
from .store.embeddings import load_embeddings_with_meta

FTS_QUERY_SAFE = re.compile(r"[^\w\s]+", re.UNICODE)

# Lexical-seat reservation (see `_reserved_term_ids` / `search`). A verbose
# question buries a rare key term: BM25 rewards breadth, so passages matching
# several common words (e.g. "Moral", "gut") outrank the one passage carrying
# the term the question is actually about (e.g. "Mißratenen", ~3 chunks). To
# keep that term's passages from being dropped, we find the rarest content
# token in the query and guarantee its top matches a few seats in the result.
_LEXICAL_RESERVE = 3  # max seats reserved for the rarest term's hits
_RARE_DF_MAX = 400  # only reserve for a token appearing in <= this many chunks
_MIN_TERM_LEN = 4  # ignore very short tokens when picking the rarest term


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


def _work_filter(work_id: int | None) -> tuple[str, tuple]:
    # Hard-scope to a single work (e.g. "in the Genealogy"). `work_id`
    # is the works.id surfaced by the chunks_full view; like the corpus
    # filter it rides the `cf` join.
    if work_id is None:
        return "", ()
    return " AND cf.work_id = ?", (work_id,)


def _speaker_filter(speaker: str | None) -> tuple[str, tuple]:
    """Case-insensitive speaker filter; matches what `tei.py` records in
    `chunks.speaker` regardless of how the user types it.
    """

    if not speaker or speaker == "any":
        return "", ()
    return " AND chunks.speaker = ? COLLATE NOCASE", (speaker,)


# Editorial apparatus — translator/editor footnotes (<note>) and dramatis-
# personae lists (<castList>). Retrievable, but `format_locator` attributes
# them to the responsible translator/editor (NEVER the author), so neither the
# LLM prompt nor the citation can present a footnote as the philosopher's
# words. See 2b in docs/block-structure-remediation-plan.md.
_APPARATUS_TYPES = ("note", "cast")
_APPARATUS_LABEL = {"note": "editorial note", "cast": "cast list"}

_TRANSLATED_BY_RE = re.compile(
    r"(?:translated by|English Translation by|Translation by|trans\.?\s*by)\s+(.+)$", re.I
)
_EDITED_BY_RE = re.compile(r"\bed(?:ited by|\.)\s+([A-Z][^.,;]+)")


def _clean_responsible(blob: str | None) -> str | None:
    """Pull a clean translator/editor name from a source-bibliography blob,
    e.g. 'Plato in Twelve Volumes, Vol. 8 translated by W.R.M. Lamb.' →
    'W.R.M. Lamb'. None when no name is recoverable (caller falls back to a
    bare 'editorial note' label)."""
    if not blob:
        return None
    m = _TRANSLATED_BY_RE.search(blob)
    if m:
        name = re.split(r";|\bIntroduction\b|\bin (?:two|three) volumes", m.group(1))[0]
        return name.strip(" .,") or None
    m = _EDITED_BY_RE.search(blob)
    if m:
        return "ed. " + m.group(1).strip(" .,")
    # Already a clean name (e.g. "Wood / Nisbet"), not a bibliography blob.
    if len(blob) <= 50 and "Volume" not in blob and ":" not in blob:
        return blob.strip(" .,") or None
    return None


def _fts_match(
    conn: sqlite3.Connection,
    fts_table: str,
    match_q: str,
    *,
    top_k: int,
    lang: str | None,
    corpus: str | None,
    speaker: str | None,
    work_id: int | None,
    min_chunk_chars: int,
) -> dict[str, float]:
    """One BM25 match against ``fts_table`` (``chunks_fts`` exact or
    ``chunks_fts_norm`` normalized). Returns ``chunk_id -> score`` where
    score is ``-bm25`` (higher is better). ``fts_table`` is an internal
    constant, never user input."""

    if not match_q:
        return {}
    lang_sql, lang_params = _lang_filter(lang)
    corpus_sql, corpus_params = _corpus_filter(corpus)
    work_sql, work_params = _work_filter(work_id)
    speaker_sql, speaker_params = _speaker_filter(speaker)
    # Floor on chunk length filters out scraper boilerplate, navigation
    # breadcrumbs, single-letter signatures, and section banners that
    # otherwise dominate retrieval on author-named queries.
    min_chars_sql = ""
    min_chars_params: tuple = ()
    if min_chunk_chars > 0:
        min_chars_sql = " AND length(chunks.text) >= ?"
        min_chars_params = (min_chunk_chars,)
    # Join through `chunks_full` only when we need an author/work field.
    needs_full = bool(corpus_sql or work_sql)
    full_join = " JOIN chunks_full cf ON cf.chunk_id = chunks.chunk_id" if needs_full else ""
    sql = (
        f"SELECT chunks.chunk_id AS chunk_id, bm25({fts_table}) AS rank "
        f"FROM {fts_table} "
        f"JOIN chunks ON chunks.rowid = {fts_table}.rowid" + full_join + " "
        f"WHERE {fts_table} MATCH ?"
        + lang_sql
        + corpus_sql
        + work_sql
        + speaker_sql
        + min_chars_sql
        + " "
        "ORDER BY rank ASC LIMIT ?"
    )
    rows = conn.execute(
        sql,
        (
            match_q,
            *lang_params,
            *corpus_params,
            *work_params,
            *speaker_params,
            *min_chars_params,
            top_k,
        ),
    ).fetchall()
    return {row[0]: -float(row[1]) for row in rows}


def _bm25_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    top_k: int,
    lang: str | None,
    corpus: str | None,
    speaker: str | None,
    min_chunk_chars: int = 0,
    fold_lang: str | None = None,
    work_id: int | None = None,
) -> dict[str, float]:
    """BM25 over the exact index, fused with the normalized index when a
    canonicalizer exists for ``fold_lang``.

    The exact index preserves precision on the verbatim spelling; the
    normalized index (matched with a canonicalized query) recovers
    historical/modern spelling variants — e.g. a *Mißrathenen* query
    finding the modernized *Mißratenen* the text stores, symmetrically.
    Scores are merged by taking the better (higher) per chunk.
    """

    common = {
        "top_k": top_k,
        "lang": lang,
        "corpus": corpus,
        "speaker": speaker,
        "work_id": work_id,
        "min_chunk_chars": min_chunk_chars,
    }
    exact = _fts_match(conn, "chunks_fts", _sanitize_fts_query(query), **common)
    if not orthography.has_canonicalizer(fold_lang):
        return exact
    norm_q = _sanitize_fts_query(orthography.canonicalize(query, fold_lang))
    norm = _fts_match(conn, "chunks_fts_norm", norm_q, **common)
    if not norm:
        return exact
    merged = dict(exact)
    for cid, score in norm.items():
        if score > merged.get(cid, float("-inf")):
            merged[cid] = score
    return merged


def _reserved_term_ids(
    conn: sqlite3.Connection,
    query: str,
    *,
    lang: str | None,
    corpus: str | None,
    speaker: str | None,
    work_id: int | None,
    min_chunk_chars: int,
    fold_lang: str | None,
) -> list[str]:
    """Chunk IDs to guarantee a seat for: the top matches of the *rarest*
    content token in ``query``.

    Counters BM25's breadth bias — a passage matching several common words
    ("Moral", "gut", "böse") outranks the one passage carrying the rare term
    the question is about ("Mißratenen", ~3 chunks), so the term's passages
    fall out of the top-k. Rarity is measured corpus-wide on the normalized
    index (canonicalized, so spelling variants are comparable); the reserved
    hits honor the same lang/corpus/work filters as the main search. Returns
    ``[]`` when no token is specific enough (df ≤ ``_RARE_DF_MAX``) — generic
    or conceptual queries are left untouched.
    """

    tokens = {t for t in FTS_QUERY_SAFE.sub(" ", query).split() if len(t) >= _MIN_TERM_LEN}
    canonical = {orthography.canonicalize(t, fold_lang) if fold_lang else t for t in tokens}
    rarest: tuple[int, str] | None = None  # (corpus-wide df, canonical token)
    for ct in canonical:
        # Cap the count scan at _RARE_DF_MAX + 1: a token past the
        # reservation ceiling can never win, so there's no point
        # walking the rest of a common word's posting list (this used
        # to do a full corpus-wide count per token, serially, under
        # the corpus lock). Exact df is preserved for every token that
        # is still in contention (df <= _RARE_DF_MAX).
        df = conn.execute(
            "SELECT count(*) FROM ("
            "  SELECT 1 FROM chunks_fts_norm WHERE chunks_fts_norm MATCH ? LIMIT ?"
            ")",
            (f'"{ct}"', _RARE_DF_MAX + 1),
        ).fetchone()[0]
        if df and (rarest is None or df < rarest[0]):
            rarest = (df, ct)
    if rarest is None or rarest[0] > _RARE_DF_MAX:
        return []
    hits = _fts_match(
        conn,
        "chunks_fts_norm",
        f'"{rarest[1]}"',
        top_k=_LEXICAL_RESERVE,
        lang=lang,
        corpus=corpus,
        speaker=speaker,
        work_id=work_id,
        min_chunk_chars=min_chunk_chars,
    )
    return sorted(hits, key=lambda c: hits[c], reverse=True)[:_LEXICAL_RESERVE]


def _vector_search(
    conn: sqlite3.Connection,
    query_vec: np.ndarray,
    *,
    top_k: int,
    lang: str | None,
    corpus: str | None,
    speaker: str | None,
    min_chunk_chars: int = 0,
    work_id: int | None = None,
) -> dict[str, float]:
    # Filter columns come memoized alongside the embedding matrix (same
    # invalidation), so this doesn't re-scan chunks_full per request. (In
    # practice min_chunk_chars defaults > 0, so a filter is essentially always
    # active anyway.)
    ids, matrix, meta = load_embeddings_with_meta(conn)
    if not ids:
        return {}
    keep = np.ones(len(ids), dtype=bool)
    if lang not in {None, "any"}:
        keep &= meta.langs == lang
    if corpus not in {None, "any"}:
        keep &= meta.corpora == corpus
    if speaker and speaker != "any":
        keep &= meta.speakers_lower == speaker.lower()
    if min_chunk_chars > 0:
        keep &= meta.text_lens >= min_chunk_chars
    if work_id is not None:
        keep &= meta.work_ids == work_id
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
    fold_lang: str | None = None,
    work_id: int | None = None,
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
        conn,
        query,
        top_k=fetch_pool,
        lang=lang,
        corpus=corpus,
        speaker=speaker,
        min_chunk_chars=min_chunk_chars,
        fold_lang=fold_lang,
        work_id=work_id,
    )
    vec_raw: dict[str, float] = {}
    if embedder is not None and store.has_embeddings(conn):
        q_vec = embedder.encode([query])[0]
        vec_raw = _vector_search(
            conn,
            q_vec,
            top_k=fetch_pool,
            lang=lang,
            corpus=corpus,
            speaker=speaker,
            min_chunk_chars=min_chunk_chars,
            work_id=work_id,
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

    ordered = [cid for cid, _ in sorted(fused.items(), key=lambda x: x[1], reverse=True)]
    if not ordered:
        return []
    selected = ordered[:top_k]
    # Guarantee the rarest query term's passages a seat, so a key term named
    # in the question can't be displaced by thematically-similar (vector) or
    # common-word (BM25-breadth) matches. No-op for generic/conceptual queries.
    reserved = _reserved_term_ids(
        conn,
        query,
        lang=lang,
        corpus=corpus,
        speaker=speaker,
        work_id=work_id,
        min_chunk_chars=min_chunk_chars,
        fold_lang=fold_lang,
    )
    forced = [cid for cid in reserved if cid not in selected]
    if forced:
        keep = selected[: max(0, top_k - len(forced))]
        selected = sorted({*keep, *forced}, key=lambda c: fused.get(c, 0.0), reverse=True)[:top_k]
    base_ids = selected
    # One neighbor query per hit, reused for the text assembly below
    # (this used to hit `neighbor_ids` a second time per hit).
    neighbors = {cid: store.neighbor_ids(conn, cid, window=expand_neighbors) for cid in base_ids}
    expanded_ids: list[str] = []
    seen: set[str] = set()
    for cid in base_ids:
        for nid in neighbors[cid]:
            if nid not in seen:
                seen.add(nid)
                expanded_ids.append(nid)

    metas = store.fetch_chunks(conn, expanded_ids)
    out: list[Hit] = []
    for cid in base_ids:
        meta_row = metas.get(cid)
        if meta_row is None:
            continue
        meta = store.to_meta_dict(meta_row)
        if expand_neighbors > 0:
            parts: list[str] = []
            for nid in neighbors[cid]:
                row = metas.get(nid)
                if row is not None and row["text"]:
                    parts.append(row["text"])
            if parts:
                meta = dict(meta)
                meta["text"] = "\n\n".join(parts)
        out.append(
            Hit(
                chunk_id=cid,
                score=fused.get(cid, 0.0),
                bm25=bm25_raw.get(cid, 0.0),
                cosine=vec_raw.get(cid, 0.0),
                meta=meta,
            )
        )
    return out


def format_locator(meta: dict) -> str:
    """Compose a human citation like `Plato, Republic 514a (Bk 7)`.

    Editorial apparatus (block_type 'note'/'cast') is attributed to the
    responsible translator/editor — NOT the work's author — so a footnote is
    never presented as the philosopher's words: e.g.
    `Republic 327a — editorial note (W.R.M. Lamb)`."""

    block_type = meta.get("block_type")
    if block_type in _APPARATUS_TYPES:
        work = meta.get("work") or ""
        section = meta.get("section")
        loc_bits = [b for b in (work, section) if b]
        loc = " ".join(loc_bits) if loc_bits else "(unknown)"
        label = _APPARATUS_LABEL.get(block_type, "editorial")
        who = _clean_responsible(meta.get("translator"))
        return f"{loc} — {label}" + (f" ({who})" if who else "")

    if block_type == "objection":
        # A dialectical voice by ANOTHER author hosted in the work —
        # Hobbes/Caterus/Arnauld/… objecting to Descartes' Meditations.
        # Cite the objector (stored in `speaker`), never the work's
        # author: "Objections et Réponses Obj. III, ¶ 3 — objection
        # (Hobbes)". Unlike note/cast, these stay fully retrievable —
        # they're substantive philosophy, not editorial apparatus.
        work = meta.get("work") or ""
        section = meta.get("section")
        loc_bits = [b for b in (work, section) if b]
        loc = " ".join(loc_bits) if loc_bits else "(unknown)"
        who = meta.get("speaker")
        return f"{loc} — objection" + (f" ({who})" if who else "")

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
