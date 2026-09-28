"""Phase 3 — embedding-based verification + allusion sweep.

Two passes built on the existing ``sentence-transformers`` embedding
infrastructure (`embed.py`, `paraphrase-multilingual-MiniLM-L12-v2`,
384-dim, multilingual). Both passes read pre-computed embeddings
from the ``embeddings`` table (filled by ``minerva embed``).

PASS A — :func:`verify_quoted_references`
    For every ``cross_references`` row already in the table whose
    ``quoted_phrase`` is non-NULL, encode the phrase, cosine-compare
    against the target's chunk embedding(s), and apply the
    confidence thresholds from the plan:

        cosine >= 0.80  →  promote to ``source_method='rule+embed'``,
                           confidence = max(prev, 0.85); set
                           ``target_chunk_id`` if not already.
        cosine <  0.50  →  set ``curator_status='rejected'``; the
                           rule fired but the quote doesn't match
                           the target. Probably a name-mention
                           false positive.
        else             →  leave at the current status for the LLM
                           verifier pass (Phase 4).

PASS B — :func:`find_cross_author_allusions`
    Embedding-only sweep that targets rows the rules CAN'T find:
    Plato echoing Heraclitus, Augustine paraphrasing Plotinus without
    name. For each source-author chunk, find top-k cross-author
    chunks above a cosine threshold (default 0.85). Insert as
    ``source_method='embed_only'``, ``reference_type='alludes'``,
    confidence = cosine score, ``curator_status='auto'``.

    The pair-wise matrix products use vectorized NumPy operations —
    a (3,632 × 13,591) Aquinas-Aristotle matrix completes in a few
    seconds on CPU. Per-pair runtime scales with #source × #target,
    so the CLI lets the user scope to specific pairs.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .. import embed as embed_mod
from .. import store
from . import quote_match
from . import rules as refs_rules
from . import schema as refs_schema
from .constants import NOT_HUMAN_CURATED

# Threshold defaults from the plan. Override via `refs build` flags
# when the user wants to widen recall (lower threshold) or tighten
# precision (raise threshold).
DEFAULT_PROMOTE_THRESHOLD = 0.80
DEFAULT_REJECT_THRESHOLD = 0.50
DEFAULT_ALLUSION_THRESHOLD = 0.85
DEFAULT_ALLUSION_TOP_K = 3


@dataclass(frozen=True)
class VerifyStats:
    promoted: int = 0
    rejected: int = 0
    skipped_no_target: int = 0
    skipped_no_embedding: int = 0
    examined: int = 0
    #: Rows whose target chunk was pinned by locating the quotation in
    #: the text rather than by cosine (issue #269).
    bound_lexically: int = 0
    #: Rows promoted without a chunk binding because the quotation could
    #: not be located in the target work. The reference is verified at
    #: work level; which verse it is stays honestly unresolved.
    promoted_unbound: int = 0


@dataclass(frozen=True)
class AllusionStats:
    pairs_examined: int = 0
    candidates_emitted: int = 0
    candidates_inserted: int = 0
    candidates_skipped_dedup: int = 0


# ──────────────────────────────────────────────────────────────────
# Embedding helpers
# ──────────────────────────────────────────────────────────────────


def _load_embeddings_for_author(
    conn: sqlite3.Connection,
    author: str,
    *,
    min_chunk_chars: int = 0,
) -> tuple[list[str], np.ndarray]:
    """Return (chunk_ids, matrix) for every embedded chunk by ``author``.

    Matrix shape is ``(N, dim)``, L2-normalized (sentence-transformers
    encode with ``normalize=True`` by default — see ``embed.Embedder``).
    Empty result when the author has chunks but no embeddings yet —
    caller decides whether to abort or fall back to a lexical signal.

    ``min_chunk_chars`` filters out short chunks (section banners like
    "§ 46", "Anmerkung", "Articulus 1") whose embeddings collide
    trivially across the corpus. A 80-char floor removes ~25% of
    embed_only false-positives without losing real allusive content.
    """

    sql = (
        "SELECT emb.chunk_id, emb.vector "
        "FROM embeddings emb "
        "JOIN chunks c ON c.chunk_id = emb.chunk_id "
        "LEFT JOIN editions e ON e.id = c.edition_id "
        "LEFT JOIN translations t ON t.id = c.translation_id "
        "LEFT JOIN works w ON w.id = COALESCE(e.work_id, t.work_id) "
        "WHERE w.author = ?"
    )
    params: list[object] = [author]
    if min_chunk_chars > 0:
        sql += " AND length(c.text) >= ?"
        params.append(min_chunk_chars)
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return [], np.zeros((0, 0), dtype=np.float32)
    chunk_ids = [r[0] for r in rows]
    matrix = np.stack([store.blob_to_vector(r[1]) for r in rows])
    return chunk_ids, matrix


_UNLOCATED_NOTE = (
    "embed-verify: the quoted phrase could not be located in this work's "
    "text, so no verse is pinned. The reference is verified at work level "
    "only — see issue #269."
)


def _lexical_note(match: quote_match.LexicalMatch) -> str:
    """Per-row provenance for a lexically-bound target.

    Worth spelling out because ``source_method`` cannot: its CHECK
    constraint has no value for "located by string match", so these rows
    are stamped ``rule+embed`` like any other row this pass adjudicates.
    The note is what distinguishes them.
    """

    if match.exact:
        return (
            "embed-verify: bound by locating the quoted phrase verbatim in "
            "this chunk (normalized for diacritics, æ/œ, u~v and i~j)."
        )
    return (
        f"embed-verify: bound by lexical match — longest run {match.run} "
        f"tokens, {match.coverage:.0%} of the phrase in order. Edition "
        f"spelling differs from the quoting author's."
    )


def _tie_note(
    conn: sqlite3.Connection,
    runners_up: Sequence[quote_match.LexicalMatch],
    *,
    by_cosine: bool,
) -> str:
    """Names the verses passed over, so the pick is visible as a pick.

    A tie means the quotation occurs identically in more than one verse
    and the string is exhausted (issue #276). Whichever way it is then
    settled, the alternative belongs on the row: the reader is not
    misled — the quotation reads correctly in either — but they cannot
    otherwise tell a determined binding from an adjudicated one.
    """

    labels = ", ".join(
        f"{section} ({m.chunk_id})" if section else m.chunk_id
        for m, section in zip(
            runners_up,
            _chunk_sections(conn, [m.chunk_id for m in runners_up]),
            strict=True,
        )
    )
    how = (
        "this one scored higher by cosine among the tied verses"
        if by_cosine
        else "this one picked by stable chunk_id order — no two tied verses "
        "had embeddings to compare"
    )
    return f" {labels} also contain the phrase; {how}."


def _chunk_sections(conn: sqlite3.Connection, chunk_ids: Sequence[str]) -> list[str | None]:
    """Section locators for ``chunk_ids``, in the order given.

    ``chunk_ids`` must be non-empty — the sole caller only builds a note
    when there is a runner-up to name, and an empty ``IN ()`` is not
    valid SQL.
    """

    placeholders = ",".join("?" * len(chunk_ids))
    found = dict(
        conn.execute(
            f"SELECT chunk_id, section FROM chunks WHERE chunk_id IN ({placeholders})",
            tuple(chunk_ids),
        ).fetchall()
    )
    return [found.get(cid) for cid in chunk_ids]


def _adjudicate_tie(
    conn: sqlite3.Connection,
    phrase_vec: np.ndarray,
    tied: Sequence[quote_match.LexicalMatch],
) -> tuple[quote_match.LexicalMatch, list[quote_match.LexicalMatch], bool]:
    """Pick one of several verses that carry the quotation identically.

    Cosine is legitimate here, and only here: the choice is between two
    known-correct texts rather than a search over the whole Psalter,
    which is the distinction #269 turned on.

    Falls back to ``tied[0]`` — the lowest ``chunk_id`` — unless at least
    two candidates have embeddings. A single score is not a comparison,
    and dressing the stable pick up as cosine evidence would be worse
    than admitting it is arbitrary. Returns the winner, the verses passed
    over, and whether cosine actually decided.
    """

    scoreable: list[tuple[quote_match.LexicalMatch, np.ndarray]] = []
    for m in tied:
        vec = _load_embedding_for_chunk(conn, m.chunk_id)
        if vec is not None:
            scoreable.append((m, vec))

    if len(scoreable) < 2:
        return tied[0], list(tied[1:]), False

    winner = max(scoreable, key=lambda mv: float(phrase_vec @ mv[1]))[0]
    return winner, [m for m in tied if m.chunk_id != winner.chunk_id], True


def _work_texts(
    conn: sqlite3.Connection,
    work_id: int,
    cache: dict[int, list[tuple[str, str]]],
) -> list[tuple[str, str]]:
    """``(chunk_id, text)`` for every chunk of ``work_id``, memoized.

    Editions only, matching the embedding query below it — a translation
    of the target work is not the text the author quoted.
    """

    cached = cache.get(work_id)
    if cached is None:
        cached = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT c.chunk_id, c.text FROM chunks c "
                "JOIN editions e ON e.id = c.edition_id "
                "WHERE e.work_id = ?",
                (work_id,),
            ).fetchall()
        ]
        cache[work_id] = cached
    return cached


def _load_embedding_for_chunk(conn: sqlite3.Connection, chunk_id: str) -> np.ndarray | None:
    row = conn.execute(
        "SELECT vector FROM embeddings WHERE chunk_id = ?",
        (chunk_id,),
    ).fetchone()
    if row is None:
        return None
    return store.blob_to_vector(row[0])


# ──────────────────────────────────────────────────────────────────
# PASS A — verify quoted-phrase references
# ──────────────────────────────────────────────────────────────────


def verify_quoted_references(
    conn: sqlite3.Connection,
    embedder: embed_mod.Embedder,
    *,
    promote_threshold: float = DEFAULT_PROMOTE_THRESHOLD,
    reject_threshold: float = DEFAULT_REJECT_THRESHOLD,
    source_author: str | None = None,
    target_author: str | None = None,
) -> VerifyStats:
    """Walk every ``cross_references`` row with a non-NULL
    ``quoted_phrase`` and a known target (``target_chunk_id`` set OR
    ``target.in_corpus_work_id`` set). Cosine-compare the phrase
    against the target chunk(s); promote / reject based on the
    threshold pair.

    Idempotent: re-running won't re-process an already-promoted row
    because the SQL filter selects only ``source_method IN
    ('rule_weak', 'rule_strong')`` — it will NOT match ``rule+embed``
    or ``rule+embed+llm`` (an earlier ``LIKE 'rule_%'`` did, see issue
    #43). Re-runnable safely after a rules pass adds new quoted_phrase
    rows.

    Manual rows (curator_status IN 'manual','approved','rejected') are
    skipped — embedding can't override a curator decision.
    """

    # Pull the candidate rows. JOIN to chunks for the target text +
    # to reference_targets for the in-corpus link. Filter to rows
    # the rules wrote (rule_strong / rule_weak / rule+embed-pending);
    # leave manual/approved/rejected alone.
    clauses = [
        "xr.quoted_phrase IS NOT NULL",
        "xr.curator_status = 'auto'",
        # Only rows the *rules* stamped. Must be an exact set, NOT
        # ``LIKE 'rule_%'`` — the SQLite ``_`` wildcard matches a single
        # char, so ``'rule_%'`` also matches ``'rule+embed'`` and
        # ``'rule+embed+llm'`` and would re-process already-verified
        # rows (overwriting the ``+llm`` provenance and re-billing
        # llm-verify). See issue #43.
        "xr.source_method IN ('rule_weak', 'rule_strong')",
        NOT_HUMAN_CURATED,
    ]
    params: list[object] = []
    if source_author is not None:
        clauses.append("src_work.author = ?")
        params.append(source_author)
    if target_author is not None:
        clauses.append("rt.canonical_author = ?")
        params.append(target_author)
    where = " AND ".join(clauses)

    rows = conn.execute(
        f"SELECT xr.id, xr.quoted_phrase, xr.target_id, xr.target_chunk_id, "
        f"       xr.confidence, "
        f"       rt.in_corpus_work_id, rt.canonical_author "
        f"FROM cross_references xr "
        f"JOIN reference_targets rt ON rt.id = xr.target_id "
        f"JOIN chunks c ON c.chunk_id = xr.source_chunk_id "
        f"LEFT JOIN editions e ON e.id = c.edition_id "
        f"LEFT JOIN translations t ON t.id = c.translation_id "
        f"LEFT JOIN works src_work "
        f"       ON src_work.id = COALESCE(e.work_id, t.work_id) "
        f"WHERE {where}",
        params,
    ).fetchall()

    n_examined = 0
    n_promoted = 0
    n_rejected = 0
    n_skipped_no_target = 0
    n_skipped_no_embedding = 0
    n_bound_lexically = 0
    n_promoted_unbound = 0

    # Encode all phrases at once for batched-throughput. Bookkeeping
    # arrays line up by index with `rows`.
    if not rows:
        return VerifyStats(examined=0)
    phrases = [r[1] for r in rows]
    phrase_vecs = embedder.encode(phrases)

    # Cache target chunk-matrix per (target_author, work_id) so we
    # don't reload the same matrix for sibling rows.
    target_matrix_cache: dict[int, tuple[list[str], np.ndarray]] = {}
    # Same idea for the work's chunk texts, which the lexical binder
    # scans. Sibling rows share a work almost always (the whole
    # quoted-Psalm population is one work), so this loads once.
    work_text_cache: dict[int, list[tuple[str, str]]] = {}

    for i, row in enumerate(rows):
        xr_id = row[0]
        target_chunk_id = row[3]
        in_corpus_work_id = row[5]
        n_examined += 1
        # Cosine may pin a chunk only when it is the sole signal we have.
        # The work-level branch clears this when the quotation could not
        # be located lexically (issue #269).
        may_bind_chunk = True

        # Pick the comparison surface.
        if target_chunk_id is not None:
            # Specific chunk targeted — compare phrase to that chunk.
            target_vec = _load_embedding_for_chunk(conn, target_chunk_id)
            if target_vec is None:
                n_skipped_no_embedding += 1
                continue
            score = float(phrase_vecs[i] @ target_vec)
            best_chunk_id = target_chunk_id
        elif in_corpus_work_id is not None:
            # Work-level target. Try to LOCATE the quotation in the work
            # before asking cosine to guess at it.
            #
            # These rows come from FormulaicQuoteRule, which fires on
            # "in Psalmo: <verse text>." — an exact quotation with the
            # chapter:verse omitted. Cosine over five words of liturgical
            # Latin picks the wrong verse about a third of the time,
            # because the litany Psalms act as an attractor for any short
            # devotional phrase (issue #269): "omnia in sapientia
            # fecisti" is Ps 103:24 and went to Ps 135:7. A quotation is
            # a string, so match it as one; see refs/quote_match.py.
            tied = quote_match.all_lexical_matches(
                phrases[i], _work_texts(conn, in_corpus_work_id, work_text_cache)
            )
            if tied:
                # More than one verse can carry the quotation word for
                # word — Ps 113:12 and Ps 134:15 do. The string has
                # nothing left to say at that point, so cosine settles it
                # among those verses only (issue #276).
                lex, runners_up, by_cosine = _adjudicate_tie(conn, phrase_vecs[i], tied)
                note = _lexical_note(lex)
                if runners_up:
                    note += _tie_note(conn, runners_up, by_cosine=by_cosine)
                # Locating the phrase in a specific verse is near
                # definitional — much stronger evidence than any cosine
                # score, so it does not go through the threshold ladder.
                conn.execute(
                    "UPDATE cross_references "
                    "SET confidence = ?, "
                    "    source_method = 'rule+embed', "
                    "    target_chunk_id = ?, "
                    "    curator_note = ? "
                    "WHERE id = ?",
                    (
                        0.98 if lex.exact else 0.90,
                        lex.chunk_id,
                        note,
                        xr_id,
                    ),
                )
                n_promoted += 1
                n_bound_lexically += 1
                continue

            # Not locatable. Fall through to cosine for the promote /
            # reject decision, but do NOT let it pin a verse — a NULL
            # target is visibly unresolved, a wrong one reads as
            # verified.
            may_bind_chunk = False
            cached = target_matrix_cache.get(in_corpus_work_id)
            if cached is None:
                w_rows = conn.execute(
                    "SELECT emb.chunk_id, emb.vector "
                    "FROM embeddings emb "
                    "JOIN chunks c ON c.chunk_id = emb.chunk_id "
                    "JOIN editions e ON e.id = c.edition_id "
                    "WHERE e.work_id = ?",
                    (in_corpus_work_id,),
                ).fetchall()
                if not w_rows:
                    target_matrix_cache[in_corpus_work_id] = (
                        [],
                        np.zeros((0, 0), dtype=np.float32),
                    )
                else:
                    cids = [r[0] for r in w_rows]
                    mat = np.stack([store.blob_to_vector(r[1]) for r in w_rows])
                    target_matrix_cache[in_corpus_work_id] = (cids, mat)
                cached = target_matrix_cache[in_corpus_work_id]
            target_ids, target_matrix = cached
            if target_matrix.size == 0:
                n_skipped_no_embedding += 1
                continue
            scores = target_matrix @ phrase_vecs[i]
            best_idx = int(np.argmax(scores))
            score = float(scores[best_idx])
            best_chunk_id = target_ids[best_idx]
        else:
            # Out-of-corpus target — nothing to compare against.
            n_skipped_no_target += 1
            continue

        if score >= promote_threshold:
            # Promote: bump confidence + tag with rule+embed; pin to the
            # best-matching chunk if not already attached. Clamp to
            # [0, 1] — float32 matmul can produce 1.0000001 etc.
            new_conf = max(row[4], 0.85, max(0.0, min(1.0, score)))
            if target_chunk_id is None and not may_bind_chunk:
                # Verified as a reference to the work; which chunk stays
                # unresolved on purpose.
                conn.execute(
                    "UPDATE cross_references "
                    "SET confidence = ?, source_method = 'rule+embed', "
                    "    curator_note = ?, "
                    "    curated_by = 'embed', "
                    "    curated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                    "WHERE id = ?",
                    (new_conf, _UNLOCATED_NOTE, xr_id),
                )
                # n_promoted is incremented once for the whole block below.
                n_promoted_unbound += 1
            elif target_chunk_id is None:
                conn.execute(
                    "UPDATE cross_references "
                    "SET confidence = ?, "
                    "    source_method = 'rule+embed', "
                    "    target_chunk_id = ?, "
                    "    curated_by = 'embed', "
                    "    curated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                    "WHERE id = ?",
                    (new_conf, best_chunk_id, xr_id),
                )
            else:
                conn.execute(
                    "UPDATE cross_references "
                    "SET confidence = ?, source_method = 'rule+embed', "
                    "    curated_by = 'embed', "
                    "    curated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                    "WHERE id = ?",
                    (new_conf, xr_id),
                )
            n_promoted += 1
        elif score < reject_threshold:
            conn.execute(
                "UPDATE cross_references "
                "SET curator_status = 'rejected', "
                "    source_method = 'rule+embed', "
                "    curated_by = 'embed', "
                "    curated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                "WHERE id = ?",
                (xr_id,),
            )
            n_rejected += 1
        # else: mid-range — leave for LLM verifier in Phase 4.

    conn.commit()

    return VerifyStats(
        examined=n_examined,
        promoted=n_promoted,
        rejected=n_rejected,
        skipped_no_target=n_skipped_no_target,
        skipped_no_embedding=n_skipped_no_embedding,
        bound_lexically=n_bound_lexically,
        promoted_unbound=n_promoted_unbound,
    )


# ──────────────────────────────────────────────────────────────────
# PASS B — embedding-only allusion sweep
# ──────────────────────────────────────────────────────────────────


# Default channels we sweep when no --pair flag is given. The list is
# narrow on purpose — the per-pair matrix-product cost adds up, and
# these are the channels with both (a) clear historical cross-
# influence and (b) enough texts on both sides to make embedding
# similarity meaningful.
DEFAULT_ALLUSION_PAIRS: tuple[tuple[str, str], ...] = (
    ("Aquinas", "Aristotle"),
    ("Aquinas", "Augustine"),
    ("Augustine", "Plato"),
    ("Augustine", "Aristotle"),
    ("Hegel", "Kant"),
    ("Hegel", "Plato"),
    ("Hegel", "Aristotle"),
    ("Spinoza", "Descartes"),
    ("Kant", "Plato"),
    ("Kant", "Aristotle"),
    # Biblical channels — Aquinas and Augustine cite scripture
    # constantly. Latin↔Latin (Vulgate) is the primary signal; the
    # cross-language Greek pairs work because the embedding model
    # (paraphrase-multilingual-MiniLM-L12-v2) is multilingual, so
    # Latin "Beati pauperes spiritu" pairs with Greek "Μακάριοι οἱ
    # πτωχοὶ τῷ πνεύματι".
    ("Aquinas", "Vulgate"),
    ("Aquinas", "New Testament"),
    ("Aquinas", "Septuagint"),
    ("Augustine", "Vulgate"),
    # Modern-language biblical channels — added with the Luther 1912 /
    # KJV / Sacy corpora. Each pair lets embed-verify Pass B catch
    # unattributed allusions and paraphrases the locator-cite rules
    # can't. Nietzsche's Genealogie and Antichrist parody scripture
    # without naming chapter:verse; expect heavy embed_only output.
    # German philosophers ↔ Luther (target both editions — same
    # text, different orthography; cosine similarity should fire on
    # either when the source author paraphrases).
    ("Hegel", "Luther Bibel 1912"),
    ("Hegel", "Luther Bibel 1545"),
    ("Kant", "Luther Bibel 1912"),
    ("Kant", "Luther Bibel 1545"),
    ("Marx", "Luther Bibel 1912"),
    ("Marx", "Luther Bibel 1545"),
    ("Nietzsche", "Luther Bibel 1912"),
    ("Nietzsche", "Luther Bibel 1545"),
    # English philosophers ↔ KJV. Hobbes is the heaviest biblical
    # exegete in the corpus; Leviathan Parts III–IV alone should
    # surface hundreds of allusions.
    ("Hobbes", "King James Bible"),
    ("Locke", "King James Bible"),
    ("Hume", "King James Bible"),
    # French philosophers ↔ Sacy. Pascal's Pensées is densely
    # biblical (~30% by volume); Rousseau concentrates in the Vicar's
    # Profession of Faith (Émile IV).
    ("Pascal", "Sacy"),
    ("Rousseau", "Sacy"),
    # Cross-language Latin-side pairs. The multilingual model handles
    # Latin↔German/English/French similarity, so Aquinas's "Beati
    # pauperes spiritu" pairs with Luther's "Selig sind, die da
    # geistlich arm sind", KJV's "Blessed are the poor in spirit",
    # and Sacy's "Bienheureux les pauvres d'esprit". Useful as
    # bonus signal for the Aquinas/Augustine undercount.
    ("Aquinas", "Luther Bibel 1912"),
    ("Aquinas", "King James Bible"),
    ("Aquinas", "Sacy"),
    ("Augustine", "Luther Bibel 1912"),
    ("Augustine", "King James Bible"),
    # Spinoza ↔ scripture. The Tractatus Theologico-Politicus is
    # ~30% biblical exegesis; the philological-critical method that
    # the work invented works by close paraphrase of biblical
    # narrative. Vulgate is the direct Latin↔Latin signal; the
    # vernacular pairs are bonus cross-language signal via the
    # multilingual embedding model. Hebrew MT is included because
    # Spinoza was a Hebraist and the TTP is the corpus's most
    # Hebrew-engaged Latin work — chapters VII-X analyse Hebrew
    # idiom directly.
    ("Spinoza", "Vulgate"),
    ("Spinoza", "Hebrew Bible"),
    ("Spinoza", "Septuagint"),
    ("Spinoza", "New Testament"),
    ("Spinoza", "Luther Bibel 1912"),
    ("Spinoza", "King James Bible"),
)


DEFAULT_MIN_CHUNK_CHARS = 80


def find_cross_author_allusions(
    conn: sqlite3.Connection,
    *,
    pairs: Sequence[tuple[str, str]] = DEFAULT_ALLUSION_PAIRS,
    min_cosine: float = DEFAULT_ALLUSION_THRESHOLD,
    top_k: int = DEFAULT_ALLUSION_TOP_K,
    min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS,
    verbose: bool = False,
) -> AllusionStats:
    """For each (source_author, target_author) pair, compute the full
    cosine-similarity matrix and emit ``embed_only`` candidate rows
    for every (source_chunk, target_chunk) edge above ``min_cosine``,
    keeping at most ``top_k`` target chunks per source chunk.

    Embeddings are pre-computed by ``minerva embed``; this pass is
    pure numpy matmul + INSERT, no model calls. Per-pair runtime
    scales with ``#source × #target``: ~3-5 seconds for an Aquinas
    × Aristotle pair on CPU.

    The :func:`refs.rules.insert_candidate` dedup path blocks rows
    that match an existing manual / approved entry or a logically
    identical auto row — so re-running this sweep is idempotent.
    """

    n_pairs = 0
    n_emitted = 0
    n_inserted = 0
    n_skipped = 0

    for source_author, target_author in pairs:
        n_pairs += 1
        src_ids, src_mat = _load_embeddings_for_author(
            conn, source_author, min_chunk_chars=min_chunk_chars
        )
        tgt_ids, tgt_mat = _load_embeddings_for_author(
            conn, target_author, min_chunk_chars=min_chunk_chars
        )
        if not src_ids or not tgt_ids:
            if verbose:
                print(
                    f"  [skip] {source_author} → {target_author}: "
                    f"src_chunks={len(src_ids)}, tgt_chunks={len(tgt_ids)} "
                    f"(missing embeddings?)"
                )
            continue
        if verbose:
            print(
                f"  [pair] {source_author} ({len(src_ids)}) → {target_author} ({len(tgt_ids)}) ..."
            )

        # Full cosine matrix. Both src and tgt are L2-normalized so
        # the dot product is cosine. Memory: src*tgt floats — for the
        # largest pair (Hegel 11k × Plato 17k) that's ~700 MB float32.
        # Use float32 explicitly to keep peak under 1 GB.
        scores = src_mat.astype(np.float32) @ tgt_mat.astype(np.float32).T

        # Find target chunk ids by source. For each source row, take
        # the top-k columns by score; emit those that clear
        # min_cosine. Using argpartition for O(N log K) per row.
        k = min(top_k, scores.shape[1])
        # The slice [:k] from argpartition is unsorted; that's fine —
        # we only care about the rows that clear the threshold.
        for i, src_id in enumerate(src_ids):
            row_scores = scores[i]
            top_idx = np.argpartition(-row_scores, k - 1)[:k]
            # Filter to those that clear the threshold.
            top_idx = top_idx[row_scores[top_idx] >= min_cosine]
            if top_idx.size == 0:
                continue
            # Sort the survivors for nicer report ordering.
            top_idx = top_idx[np.argsort(-row_scores[top_idx])]
            for j in top_idx:
                tgt_chunk_id = tgt_ids[j]
                # Clamp to [0, 1]. Cosine of two L2-normalized
                # vectors is in [-1, 1] mathematically, but float32
                # matmul can produce 1.0000001 etc.; without the
                # clamp the cross_references.confidence CHECK fires.
                # Negative scores can't reach this branch (we filtered
                # by min_cosine >= 0.85 above), but clamp the lower
                # bound too for safety.
                score = float(max(0.0, min(1.0, row_scores[j])))
                n_emitted += 1
                # Build a Candidate and let `insert_candidate` handle
                # target resolution + dedup. The target_work is left
                # as the catch-all "*" so the auto row attaches to the
                # author-level reference_targets row; a future locator-
                # extracting rule can refine the work later.
                # Pin ``target_chunk_id`` on the Candidate itself so the
                # dedup key in ``insert_candidate`` treats each of the
                # top-k target chunks as distinct — otherwise every match
                # for one source chunk collapses to a single row (#44).
                # It also lets the reader's "Open in reader →" resolve.
                cand = refs_rules.Candidate(
                    source_chunk_id=src_id,
                    source_span_start=None,
                    source_span_end=None,
                    source_form_snapshot=None,
                    target_author=target_author,
                    target_work="",
                    target_locator=None,
                    reference_type="alludes",
                    confidence=score,
                    source_method="embed_only",
                    quoted_phrase=None,
                    target_chunk_id=tgt_chunk_id,
                    note=(
                        f"embedding cosine {score:.3f} against "
                        f"{target_author} chunk {tgt_chunk_id[:10]}…"
                    ),
                )
                new_id = refs_rules.insert_candidate(conn, cand)
                if new_id is None:
                    n_skipped += 1
                    continue
                n_inserted += 1

        # Commit per-pair so a long run doesn't hold a huge implicit
        # transaction. Each pair adds at most ~top_k × #source rows.
        conn.commit()
        if verbose:
            print(
                f"           emitted={n_emitted}, inserted={n_inserted}, "
                f"skipped={n_skipped} (running totals)"
            )

    return AllusionStats(
        pairs_examined=n_pairs,
        candidates_emitted=n_emitted,
        candidates_inserted=n_inserted,
        candidates_skipped_dedup=n_skipped,
    )


# Expose a couple of names callers (the CLI in particular) might want
# without reaching into refs.rules.
ensure_target = refs_schema.ensure_target
insert_candidate = refs_rules.insert_candidate

__all__ = [
    "DEFAULT_ALLUSION_PAIRS",
    "DEFAULT_ALLUSION_THRESHOLD",
    "DEFAULT_ALLUSION_TOP_K",
    "DEFAULT_PROMOTE_THRESHOLD",
    "DEFAULT_REJECT_THRESHOLD",
    "AllusionStats",
    "VerifyStats",
    "find_cross_author_allusions",
    "verify_quoted_references",
]
