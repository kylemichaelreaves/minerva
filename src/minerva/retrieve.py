"""Hybrid retrieval: SQLite FTS5 (BM25) fused with optional cosine search.

Returned `Hit` objects are already enriched with chunk metadata. The retriever
optionally expands each hit with its neighboring chunks within the same work
so the agent can quote across section boundaries.
"""

from __future__ import annotations

import dataclasses
import re
import sqlite3
from collections.abc import Iterable

import numpy as np

from . import embed, orthography, store
from .corpus_registry import corpus_authors
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

# Works addressed by verse rather than by page, section or paragraph. Their
# chunks are *legitimately* a sentence long, so the `min_chunk_chars` floor
# below — written against scraper boilerplate — made them unreachable rather
# than merely down-ranked: 1,937 Quran chunks (31% of that corpus), plus
# `Non occides.` (Exod 20:13, 12 chars) and `Ego et Pater unum sumus.`
# (John 10:30, 24 chars), two of the most-quoted sentences in the corpus
# (#268).
#
# `works.citation_system` rather than a corpus list or `block_type`: it is
# already the column that records how a work is addressed, so a new
# scripture edition is exempt the day it is ingested with no second list to
# remember. `block_type` cannot carry this — it is NULL on 49,728 of the
# 53,774 chunks under the floor. The 31,610 short `paragraph` chunks stay
# filtered, and sampling confirms those are what the floor is for: Renan
# footnote markers (`2. Zach., I, 1-6.`), French OCR residue, running heads.
_VERSE_CITATION_SYSTEMS = ("bcv", "surah_ayah")


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
    # `chunks_full.corpus` is literally `LOWER(works.author)`. With the
    # chunks-redesign of 0003, the column no longer lives on chunks;
    # it's reconstructed by the view. Joining through
    # editions/translations to works would be cheaper but the view
    # keeps callers idiomatic and the planner inlines either way.
    #
    # Callers pass a corpus *id*, which for seven corpora is not an
    # author name — `marcus_aurelius` vs "Marcus Aurelius", and
    # `presocratic` covers nine authors. Matching the id directly
    # filtered those to zero chunks (#174), so resolve it first.
    authors = corpus_authors(corpus)
    if not authors:
        return "", ()
    placeholders = ",".join("?" * len(authors))
    return f" AND cf.corpus IN ({placeholders})", authors


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


def _min_chars_filter(min_chunk_chars: int) -> tuple[str, tuple]:
    """The length floor, with verse-addressed works exempted.

    Both halves of the disjunct are needed. `chunks` carries the work only
    indirectly, through exactly one of `edition_id` or `translation_id` (a
    CHECK constraint enforces the exclusivity), and scripture arrives on
    either side depending on the source: the Vulgate, the KJV and Luther are
    all `editions` rows today, while nothing stops the next scripture ingest
    from landing as a `translations` row. A predicate on one column alone
    silently exempts half the corpus it was written for.
    """

    if min_chunk_chars <= 0:
        return "", ()
    slots = ",".join("?" * len(_VERSE_CITATION_SYSTEMS))
    exempt = (
        f" OR chunks.edition_id IN (SELECT e.id FROM editions e"
        f" JOIN works w ON w.id = e.work_id WHERE w.citation_system IN ({slots}))"
        f" OR chunks.translation_id IN (SELECT t.id FROM translations t"
        f" JOIN works w ON w.id = t.work_id WHERE w.citation_system IN ({slots}))"
    )
    return (
        f" AND (length(chunks.text) >= ?{exempt})",
        (min_chunk_chars, *_VERSE_CITATION_SYSTEMS, *_VERSE_CITATION_SYSTEMS),
    )


def _verse_work_ids(conn: sqlite3.Connection) -> np.ndarray:
    """`works.id` of the verse-addressed works, for the numpy vector filter.

    The SQL form above cannot be reused there: vector filtering runs over
    `EmbeddingChunkMeta`'s fixed-width arrays, not over a query. `work_ids`
    is already one of those columns, so this needs no change to the cached
    metadata (`store/embeddings.py`) — only the id set to test against.
    """

    slots = ",".join("?" * len(_VERSE_CITATION_SYSTEMS))
    rows = conn.execute(
        f"SELECT id FROM works WHERE citation_system IN ({slots})",
        _VERSE_CITATION_SYSTEMS,
    ).fetchall()
    return np.array([int(r[0]) for r in rows], dtype=np.int64)


# Editorial apparatus — translator/editor footnotes (<note>) and dramatis-
# personae lists (<castList>). Retrievable, but `format_locator` attributes
# them to the responsible translator/editor (NEVER the author), so neither the
# LLM prompt nor the citation can present a footnote as the philosopher's
# words. See 2b in docs/block-structure-remediation-plan.md.
_APPARATUS_TYPES = ("note", "cast")
_APPARATUS_LABEL = {"note": "editorial note", "cast": "cast list"}

# The author's OWN words, but paratextual rather than discursive — Nachlass
# title-page drafts and Briefe valedictions that end "... Von Friedrich
# Nietzsche." (#291). Unlike note/cast, `format_locator` must NOT reattribute
# these away from the author (he wrote them), so they stay out of
# `_APPARATUS_TYPES`; they still need to be capped like apparatus, because a
# 66-character signature line outranks his actual philosophical passages on
# any query containing his name. `_PARATEXT_TYPES` is the set the cap
# consults; `_APPARATUS_TYPES` stays the set `format_locator` consults.
_PARATEXT_TYPES = ("signature",)

# The most of a result set that may be apparatus (#165). Notes are short
# and numerous — the Republic carries 2,767 of them against 1,355
# English text chunks — and both halves of retrieval independently
# prefer them: BM25 because its length normalisation rewards brevity,
# vectors because a note *about* a passage reads like a question about
# that passage. Measured on "the divided line": 18 of the top 20 were
# notes, 57 of the 64 ranked candidates were notes, and Plato's own text
# ("a line divided into two unequal sections", 509d) sat at rank 12.
#
# A cap rather than a score penalty: a penalty is a magic number tuned
# to whichever query it was derived from, while a cap states the actual
# policy — apparatus supports the text, so it may not crowd it out.
# Notes stay reachable, and the two that genuinely discuss the divided
# line still come back.
_APPARATUS_MAX_SHARE = 1 / 3

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
    # otherwise dominate retrieval on author-named queries — but not in
    # verse-addressed works, where a short chunk is a whole verse.
    min_chars_sql, min_chars_params = _min_chars_filter(min_chunk_chars)
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
    corpus_names = corpus_authors(corpus)
    if corpus_names:
        # Same id-vs-author resolution as `_corpus_filter`; `isin`
        # because `presocratic` is nine authors, not one.
        keep &= np.isin(meta.corpora, corpus_names)
    if speaker and speaker != "any":
        keep &= meta.speakers_lower == speaker.lower()
    if min_chunk_chars > 0:
        # Same exemption as `_min_chars_filter`, expressed over the cached
        # metadata arrays. Without it the two halves of hybrid retrieval
        # disagree about which chunks exist, which is worse than either
        # policy alone.
        keep &= (meta.text_lens >= min_chunk_chars) | np.isin(meta.work_ids, _verse_work_ids(conn))
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


def _rank_ids(ids: Iterable[str], fused: dict[str, float]) -> list[str]:
    """Order *ids* by fused score, breaking ties on chunk_id.

    The tiebreak is what makes retrieval reproducible. Scores are fused
    into a dict seeded from a set union, and sets of strings iterate in
    hash-randomised order, so with a score-only key Python's stable sort
    carried that arbitrary order straight into the results: `minerva
    eval` swung between 0.507 and 0.557 section MRR across identical
    invocations, which is wider than most regressions it exists to
    catch (#165).
    """

    return sorted(ids, key=lambda c: (-fused.get(c, 0.0), c))


_CAPPED_TYPES = _APPARATUS_TYPES + _PARATEXT_TYPES


def _apparatus_ids(conn: sqlite3.Connection, ids: list[str]) -> set[str]:
    """Which of *ids* are apparatus or paratext rather than discursive
    primary text — i.e. everything `_cap_apparatus` may skip."""

    if not ids:
        return set()
    placeholders = ",".join("?" * len(ids))
    type_slots = ",".join("?" * len(_CAPPED_TYPES))
    rows = conn.execute(
        f"SELECT chunk_id FROM chunks_full WHERE chunk_id IN ({placeholders}) "
        f"AND block_type IN ({type_slots})",
        (*ids, *_CAPPED_TYPES),
    )
    return {r[0] for r in rows}


def _cap_apparatus(
    conn: sqlite3.Connection,
    ordered: list[str],
    top_k: int,
    exempt: frozenset[str] = frozenset(),
) -> list[str]:
    """Take the top *top_k*, letting apparatus fill at most a third.

    Score order is preserved throughout: this only skips apparatus once
    its share is spent, and backfills from the skipped ones when there
    is not enough primary text to fill the result — a work that is
    mostly apparatus, or a question actually about a footnote, still
    gets a full answer rather than a short one.

    *exempt* ids are never skipped, though apparatus among them still
    spends the allowance. That is how a reserved seat survives the cap: a
    term rare enough to earn one is sometimes rare precisely because only
    a footnote uses it, and dropping that note would answer a question
    about the term with nothing about the term.
    """

    # Every candidate, not a prefix: a note past the window would
    # otherwise be miscounted as primary text and take a reserved slot.
    # `ordered` is bounded by `fetch_pool`, so this stays one small query.
    apparatus = _apparatus_ids(conn, ordered)
    if not apparatus:
        return ordered[:top_k]

    cap = max(1, int(top_k * _APPARATUS_MAX_SHARE))
    selected: list[str] = []
    deferred: list[str] = []
    used = 0
    for cid in ordered:
        if cid in apparatus:
            if cid not in exempt and used >= cap:
                deferred.append(cid)
                continue
            used += 1
        selected.append(cid)
        if len(selected) == top_k:
            return selected
    # Not enough primary text to fill the page — give the slots back.
    selected.extend(deferred[: top_k - len(selected)])
    return selected[:top_k]


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
    BM25 and vector retrieval. Default 60 excludes short scraper
    boilerplate below that length — navigation breadcrumbs, bare section
    banners like "ETHICS BOOK I", running heads. It does **not** exclude
    title-page lines or letter valedictions ("Von Friedrich Nietzsche")
    that happen to land at 66+ characters; those are a `block_type`
    problem the length floor cannot reach, not this one (#291) — they're
    typed `block_type='signature'` at ingest and capped by
    `_PARATEXT_TYPES` instead. Pass 0 to disable when you specifically
    want to see the chunks under the floor (e.g., a curation pass
    surfacing scrape garbage to delete).

    Works addressed by verse (``works.citation_system`` in
    ``_VERSE_CITATION_SYSTEMS``) are exempt from the floor: their short
    chunks are whole verses, not boilerplate, and the filter made 17,905
    of them — including all 1,937 Quran chunks — unreachable rather than
    down-ranked (#268).
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

    ordered = _rank_ids(fused, fused)
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
        # Represent the rare term with the author's own words where any
        # exist. A term is often rare *because* only a footnote uses it,
        # and those still get one seat — but three notes about a variant
        # reading are not worth three of six slots.
        forced_apparatus = _apparatus_ids(conn, forced)
        forced = [c for c in forced if c not in forced_apparatus] + [
            c for c in forced if c in forced_apparatus
        ][:1]
        keep = selected[: max(0, top_k - len(forced))]
        selected = _rank_ids({*keep, *forced}, fused)[:top_k]
    # The apparatus share is the last word. Applied before the reserved
    # seats it was not: the merge above reinstated exactly the notes the
    # cap had just excluded. Reserved seats stay exempt so the guarantee
    # survives, and the rest of the ranking follows the selection to give
    # the cap primary text to promote in place of what it drops.
    selected = _cap_apparatus(
        conn,
        selected + [cid for cid in ordered if cid not in selected],
        top_k,
        exempt=frozenset(forced),
    )
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
