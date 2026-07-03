"""Chunk read/write and neighbor queries."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path

from .. import orthography
from ..ingest import load_jsonl
from .embeddings import invalidate_embedding_cache
from .schema import _set_meta

# Batch size for the streaming insert in ``insert_chunks``. 5000
# tuples × ~1 KB ≈ 5 MB peak per batch, which keeps the prepared-
# statement bind buffer comfortable while still amortizing SQLite's
# per-statement overhead. Bigger batches gain only marginal throughput
# and start to noticeably extend the rollback window on parse failures.
_INSERT_BATCH = 5000


def _resolve_work_refs(
    conn: sqlite3.Connection,
    *,
    corpus: str,
    author: str,
    work: str,
    lang: str,
    translator: str | None,
    edition_year: str | None,
    citation_system_override: str | None = None,
) -> tuple[int | None, int | None]:
    """Look up or create the works/editions/translations rows for one
    chunk's legacy metadata. Returns ``(edition_id, translation_id)``;
    exactly one is set per CHECK constraint on chunks.

    ``citation_system_override`` lets a specific Work pin its
    citation system to something other than the corpus default (the
    Critique of Pure Reason uses ``kant_ab`` while the rest of Kant
    falls through to ``paragraph``). Honored only when a NEW Works
    row is being created; existing rows keep whatever value they
    were first written with — switching a Work's citation system
    after the fact would invalidate every curated occurrence's
    ``location_sort_key``, so we leave that as an explicit ALTER
    rather than a side effect of re-ingest.

    Re-uses the same classification rules as
    ``migrations/0003_chunks_backfill.py``; if you change one, change
    the other or the on-disk shape will drift on re-ingest. Tests in
    ``test_store_resolve_work_refs.py`` lock the contract.
    """

    from ..migrations.runtime_helpers import (
        citation_system_for_corpus,
        original_language_for_corpus,
        parse_year,
    )

    # 1) Find or create the Work.
    work_row = conn.execute(
        "SELECT id, original_language FROM works WHERE author = ? AND title = ?",
        (author, work),
    ).fetchone()
    if work_row is None:
        original_language = original_language_for_corpus(
            corpus,
            translator=translator,
            this_lang=lang,
        )
        citation_system = citation_system_override or citation_system_for_corpus(corpus)
        cur = conn.execute(
            "INSERT INTO works (author, title, original_language, citation_system) "
            "VALUES (?, ?, ?, ?)",
            (author, work, original_language, citation_system),
        )
        work_id = int(cur.lastrowid)
        is_edition_lang = lang == original_language
    else:
        work_id = int(work_row[0])
        is_edition_lang = lang == work_row[1]

    # 2) Find or create the Edition or Translation row, matching on the
    #    legacy (translator, edition_year) tuple. We look up by the
    #    user-visible name fields because the legacy JSONL keeps these
    #    as TEXT — no surrogate key is available upstream.
    year = parse_year(edition_year)
    translator_value = translator or "(Original)"
    if is_edition_lang:
        name = translator_value if translator_value != "(Original)" else work
        edition_row = conn.execute(
            "SELECT id FROM editions "
            "WHERE work_id = ? AND name = ? AND language = ? "
            "  AND (year IS ? OR year = ?)",
            (work_id, name, lang, year, year),
        ).fetchone()
        if edition_row is not None:
            return int(edition_row[0]), None
        cur = conn.execute(
            "INSERT INTO editions (work_id, name, language, year, notes) VALUES (?, ?, ?, ?, ?)",
            (work_id, name, lang, year, None),
        )
        return int(cur.lastrowid), None
    else:
        trans_row = conn.execute(
            "SELECT id FROM translations "
            "WHERE work_id = ? AND translator_name = ? AND language = ? "
            "  AND (year IS ? OR year = ?)",
            (work_id, translator_value, lang, year, year),
        ).fetchone()
        if trans_row is not None:
            return None, int(trans_row[0])
        cur = conn.execute(
            "INSERT INTO translations "
            "  (work_id, translator_name, year, language, edition_notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (work_id, translator_value, year, lang, None),
        )
        return None, int(cur.lastrowid)


def _author_labels_for_scope(jsonl_path: Path, scope: frozenset[str]) -> set[str]:
    """Lowercased author labels of every JSONL row whose corpus slug is
    in ``scope``. This is the slug → ``chunks_full.corpus`` translation
    the incremental DELETE needs (the view's corpus column is
    ``LOWER(works.author)``, not the slug). One slug may fan out to
    many labels (presocratic → each named philosopher)."""

    labels: set[str] = set()
    for obj in load_jsonl(jsonl_path):
        if obj.get("corpus") in scope and obj.get("author"):
            labels.add(obj["author"].lower())
    return labels


def _db_author_labels_for_scope(
    conn: sqlite3.Connection,
    jsonl_path: Path,
    scope: frozenset[str],
) -> set[str]:
    """Author labels already stored for works being re-ingested.

    Catches parser author-label renames: the new JSONL carries the
    updated label, but stale chunks may still be keyed under the old
    ``chunks_full.corpus`` value until we delete by work title too.
    """

    work_titles: set[str] = set()
    for obj in load_jsonl(jsonl_path):
        if obj.get("corpus") in scope and obj.get("work"):
            work_titles.add(obj["work"])
    if not work_titles:
        return set()
    placeholders = ",".join("?" for _ in work_titles)
    rows = conn.execute(
        f"SELECT DISTINCT LOWER(corpus) AS corpus FROM chunks_full "
        f"WHERE work IN ({placeholders})",
        tuple(work_titles),
    ).fetchall()
    return {row["corpus"] for row in rows if row["corpus"]}


def insert_chunks(
    conn: sqlite3.Connection,
    jsonl_path: Path,
    *,
    mode: str = "full",
    corpora: frozenset[str] | None = None,
) -> int:
    """Bulk-load chunks from a JSONL produced by `ingest.write_jsonl`.

    Two modes:

    * ``mode="full"`` (default, used by ``index --reset`` and the
      classic ``make reindex``) — global destructive rebuild. DELETE
      from chunks/editions/works/translations, full FTS rebuild, then
      re-insert every JSONL row. All-or-nothing: parse failure rolls
      back the entire transaction so the previously-indexed corpus
      survives a malformed JSONL rather than getting wiped.

    * ``mode="incremental"`` (used by ``index --incremental``) —
      corpus-scoped replace aligned with ``merge_jsonl`` semantics.
      ``corpora`` is a frozenset of corpus slugs (matching the
      JSONL ``corpus`` field, e.g. ``"hegel"``, ``"plato"``); only
      chunks in scope are deleted, and only JSONL rows in scope are
      inserted. Out-of-scope chunks (and their lemmas, embeddings,
      cross_references) survive untouched. FTS triggers handle index
      updates so the full ``chunks_fts(rebuild)`` step is skipped.

      ``corpora=None`` in incremental mode raises ``ValueError`` —
      use ``mode="full"`` if you actually want everything reindexed.

    Resolves each row's legacy (corpus, author, work, lang, translator,
    edition_year) tuple to an edition_id or translation_id by way of
    ``_resolve_work_refs``. Works/editions/translations rows are
    created on the fly; subsequent chunks for the same source reuse
    them.

    Cross-references survival: the destructive DELETE chain would
    cascade and wipe `cross_references` (via the editions /
    translations FKs) without intervention. Migration 0013 relaxes
    those cascades to ON DELETE SET NULL, and this function disables
    FK enforcement during the rebuild so the source_chunk_id values
    survive as dangling references — then re-binds them to the
    freshly-inserted edition_id / translation_id via a chunk pivot,
    re-enables FK enforcement, and runs the integrity check. Net
    effect: a `minerva index` re-run on a populated corpus preserves
    every cross_references row whose source_chunk_id still resolves
    against the new chunks (chunk_ids are content-stable, so this is
    every row whose source text didn't change).

    For incremental mode the rebind narrows to the affected corpora
    only (xrefs sourced from out-of-scope chunks are untouched), and
    the orphan sweep only deletes xrefs whose source_chunk_id was in
    the deleted set but didn't survive the re-insert.
    """

    if mode not in ("full", "incremental"):
        raise ValueError(f"insert_chunks mode must be 'full' or 'incremental'; got {mode!r}")
    if mode == "incremental" and corpora is None:
        raise ValueError(
            "insert_chunks mode='incremental' requires a `corpora` frozenset; "
            "pass mode='full' to wipe everything."
        )
    # Normalize for downstream membership checks.
    scope: frozenset[str] = corpora or frozenset()

    # Pre-flight: how many xref rows are we trying to preserve? Used
    # both for the rebind logging and for the integrity check after.
    xref_table_exists = (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cross_references'"
        ).fetchone()
        is not None
    )
    xref_count_before = (
        conn.execute("SELECT COUNT(*) FROM cross_references").fetchone()[0]
        if xref_table_exists
        else 0
    )

    fk_prev = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    # Disable FK enforcement for the destructive sequence so the
    # DELETE chain doesn't cascade through to cross_references /
    # term_renderings et al. The rebind step below re-establishes
    # consistency before we re-enable enforcement.
    conn.execute("PRAGMA foreign_keys = OFF")
    # Track chunk_ids deleted in incremental mode so we can scope
    # the post-insert orphan sweep to those rows only.
    deleted_chunk_ids: set[str] = set()
    try:
        if mode == "full":
            # Drop both chunk-table state AND any works/editions/
            # translations that were derived from the previous ingest's
            # data. With FKs off, dangling source_chunk_id /
            # source_edition_id values in cross_references are tolerated
            # until the rebind runs.
            conn.execute("DELETE FROM translations")
            conn.execute("DELETE FROM editions")
            conn.execute("DELETE FROM works")
            conn.execute("DELETE FROM chunks")
            # FTS rebuild: a single bulk reindex of the FTS5 shadow
            # tables. Skipped in incremental mode because the FTS5
            # triggers (schema.py L49–59) keep the index in sync as we
            # delete + reinsert individual rows.
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        else:
            # Incremental: delete ONLY chunks whose corpus is in scope.
            # ⚠ Scope keys differ between the two sides: the JSONL rows
            # (and the insert filter below) key on the corpus *slug*
            # (``obj["corpus"]``, e.g. "hebrew_mt"), but
            # ``chunks_full.corpus`` is ``LOWER(works.author)`` (e.g.
            # "hebrew bible"). For seven corpora they don't match —
            # hebrew_mt, kjv, luther_1545/1912, marcus_aurelius,
            # new_testament, and presocratic (one slug → nine author
            # labels). Deleting by slug alone matched nothing there, so
            # changed chunks were re-inserted BESIDE their stale
            # predecessors. Pre-scan the JSONL to translate slugs →
            # author labels and delete by the union of both.
            delete_keys = (
                scope
                | _author_labels_for_scope(jsonl_path, scope)
                | _db_author_labels_for_scope(conn, jsonl_path, scope)
            )
            # Capture the chunk_ids first so the FTS triggers fire on
            # row-level deletes (the trigger reads OLD.chunk_id from
            # each DELETE statement). We also remember them for the
            # narrowed xref rebind + orphan-sweep stages below.
            placeholders = ",".join("?" for _ in delete_keys)
            scoped_rows = conn.execute(
                f"SELECT chunk_id FROM chunks_full WHERE corpus IN ({placeholders})",
                tuple(delete_keys),
            ).fetchall()
            deleted_chunk_ids = {row[0] for row in scoped_rows}
            if deleted_chunk_ids:
                # Batch the DELETE to keep the trigger overhead bounded.
                # Single statement per batch is fine — SQLite will
                # run the FTS trigger once per row internally.
                ids_list = list(deleted_chunk_ids)
                for i in range(0, len(ids_list), _INSERT_BATCH):
                    batch_ids = ids_list[i : i + _INSERT_BATCH]
                    qmarks = ",".join("?" for _ in batch_ids)
                    conn.execute(
                        f"DELETE FROM chunks WHERE chunk_id IN ({qmarks})",
                        batch_ids,
                    )
            # Works/editions/translations: leave alone in incremental
            # mode. _resolve_work_refs reuses existing rows when keys
            # match, and orphan rows (work with zero chunks now) are
            # cheap to leave in place — they just don't surface in
            # any chunk query. A future opt would be a post-pass
            # sweep, but it's not needed for correctness.

        # Stream-and-batch insert (Phase 1c of the 2026-05-29 remediation
        # plan): rather than materializing every row in a list before
        # one ``executemany``, accumulate fixed-size batches and flush
        # each. Memory stays flat as the corpus grows past ~500K
        # chunks. All-or-nothing semantics are preserved by the outer
        # try/rollback — if a parse error or an FK violation fires
        # mid-stream, the whole transaction unwinds.
        ord_counter: dict[tuple[str, str], int] = {}
        batch: list[tuple] = []
        inserted = 0
        INSERT_SQL = (
            "INSERT OR REPLACE INTO chunks "
            "(chunk_id, edition_id, translation_id, lang, section, book, page, "
            " speaker, source_file, text, ord, text_norm, block_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        for obj in load_jsonl(jsonl_path):
            # Incremental mode: skip rows whose corpus is out of scope.
            # Done at the row level rather than via pre-filtering so we
            # can stream the same JSONL through unchanged from both
            # modes — keeps merge_jsonl + insert_chunks decoupled.
            if mode == "incremental" and obj["corpus"] not in scope:
                continue
            edition_id, translation_id = _resolve_work_refs(
                conn,
                corpus=obj["corpus"],
                author=obj["author"],
                work=obj["work"],
                lang=obj["lang"],
                translator=obj.get("translator"),
                edition_year=obj.get("edition_year"),
                # The JSONL carries citation_system when a parser
                # decided to override the corpus default (e.g. KrV =
                # kant_ab). Otherwise None → corpus default applies.
                citation_system_override=obj.get("citation_system"),
            )
            key = (obj["work"], obj["lang"])
            ord_counter[key] = ord_counter.get(key, -1) + 1
            batch.append(
                (
                    obj["chunk_id"],
                    edition_id,
                    translation_id,
                    obj["lang"],
                    obj.get("section"),
                    obj.get("book"),
                    obj.get("page"),
                    obj.get("speaker"),
                    obj["source_file"],
                    obj["text"],
                    ord_counter[key],
                    orthography.canonicalize(obj["text"], obj["lang"]),
                    obj.get("block_type"),
                )
            )
            if len(batch) >= _INSERT_BATCH:
                conn.executemany(INSERT_SQL, batch)
                inserted += len(batch)
                batch = []
        # Drain the final partial batch.
        if batch:
            conn.executemany(INSERT_SQL, batch)
            inserted += len(batch)

        # Rebind cross_references to the freshly-inserted edition /
        # translation surrogate ids. Skipped on fresh DBs where the
        # table doesn't exist yet; cheap no-op when the table is empty.
        if xref_table_exists and xref_count_before:
            affected: frozenset[str] | None = (
                frozenset(deleted_chunk_ids) if mode == "incremental" else None
            )
            if mode == "full" or affected:
                scoped_count = (
                    _xref_count_for_chunks(conn, affected)
                    if affected is not None
                    else xref_count_before
                )
                _rebind_cross_references(
                    conn,
                    scoped_count,
                    affected_chunk_ids=affected,
                )

        _set_meta(conn, "ingest.source", str(jsonl_path))
        _set_meta(conn, "ingest.count", str(inserted))

        # FK integrity check BEFORE commit. If the rebind left any
        # dangling references, raise inside the try so the rollback
        # path runs and the bad state never reaches disk. Audit-flagged
        # bug: previously this check ran after a successful commit,
        # meaning a violation surfaced as an exception but the broken
        # state was already persisted. PRAGMA foreign_key_check is
        # read-only — safe to run inside the open transaction without
        # disturbing the pending writes.
        if xref_table_exists:
            bad = conn.execute("PRAGMA foreign_key_check(cross_references)").fetchall()
            if bad:
                raise RuntimeError(
                    f"insert_chunks left {len(bad)} FK violations in "
                    f"cross_references after rebind; first 3: {bad[:3]!r}"
                )

        conn.commit()
    except BaseException:
        # Catch BaseException (not just Exception) so KeyboardInterrupt
        # mid-load also rolls back instead of leaving the chunks table
        # half-deleted. Same path also handles the FK-violation
        # RuntimeError raised above.
        conn.rollback()
        # Re-enable FK enforcement to whatever it was so subsequent
        # calls on this connection don't run with FKs unexpectedly off.
        conn.execute(f"PRAGMA foreign_keys = {'ON' if fk_prev else 'OFF'}")
        raise

    # Re-enable FK enforcement after commit. (The integrity check has
    # already passed inside the transaction.)
    conn.execute(f"PRAGMA foreign_keys = {'ON' if fk_prev else 'OFF'}")

    # Chunk IDs may have changed; existing embeddings table will be
    # rebuilt by a subsequent `minerva embed`. Drop any cached
    # embedding matrix so we don't serve a stale array.
    invalidate_embedding_cache(conn)
    return inserted


def _xref_count_for_chunks(
    conn: sqlite3.Connection, chunk_ids: frozenset[str]
) -> int:
    if not chunk_ids:
        return 0
    placeholders = ",".join("?" for _ in chunk_ids)
    return conn.execute(
        f"SELECT COUNT(*) FROM cross_references "
        f"WHERE source_chunk_id IN ({placeholders})",
        tuple(chunk_ids),
    ).fetchone()[0]


def _rebind_cross_references(
    conn: sqlite3.Connection,
    count_before: int,
    *,
    affected_chunk_ids: frozenset[str] | None = None,
) -> None:
    """Re-link every ``cross_references`` row to the freshly-inserted
    edition / translation surrogate ids.

    Migration 0013 relaxed the source_edition_id / source_translation_id
    cascades to ON DELETE SET NULL, so the prior DELETE FROM editions /
    DELETE FROM translations only nulled those columns rather than
    deleting the rows. The chunk_id values are content-stable, so the
    new ``chunks`` table contains rows with the same chunk_ids as
    before — which gives us a chunk pivot to look up the fresh
    edition_id / translation_id by joining
    ``cross_references.source_chunk_id`` ↔ ``chunks.chunk_id``.

    Orphans (xref rows whose source_chunk_id no longer exists in the
    new chunks — true stale rows because the source content changed)
    are deleted and counted. Same logic for target_chunk_id, except
    target_chunk_id is nullable so we NULL it out rather than deleting
    the row (the target_id pointer to reference_targets keeps the row
    meaningful even without a specific chunk anchor).

    When ``affected_chunk_ids`` is set (incremental mode), only xrefs
    whose ``source_chunk_id`` / ``target_chunk_id`` fall in that set are
    touched — out-of-scope corpora are left alone.
    """

    source_filter = ""
    source_params: tuple[Any, ...] = ()
    if affected_chunk_ids is not None:
        if not affected_chunk_ids:
            return
        placeholders = ",".join("?" for _ in affected_chunk_ids)
        source_filter = f" WHERE source_chunk_id IN ({placeholders})"
        source_params = tuple(affected_chunk_ids)

    conn.execute(
        f"""
        UPDATE cross_references
        SET source_edition_id    = (
            SELECT c.edition_id    FROM chunks c
            WHERE c.chunk_id = cross_references.source_chunk_id
        ),
            source_translation_id = (
            SELECT c.translation_id FROM chunks c
            WHERE c.chunk_id = cross_references.source_chunk_id
        )
        {source_filter}
        """,
        source_params,
    )

    if affected_chunk_ids is not None:
        placeholders = ",".join("?" for _ in affected_chunk_ids)
        cur = conn.execute(
            f"DELETE FROM cross_references "
            f"WHERE source_chunk_id IN ({placeholders}) "
            f"  AND source_chunk_id NOT IN (SELECT chunk_id FROM chunks)",
            tuple(affected_chunk_ids),
        )
    else:
        cur = conn.execute(
            "DELETE FROM cross_references "
            "WHERE source_chunk_id NOT IN (SELECT chunk_id FROM chunks)"
        )
    orphans_source = cur.rowcount

    if affected_chunk_ids is not None:
        placeholders = ",".join("?" for _ in affected_chunk_ids)
        cur = conn.execute(
            f"UPDATE cross_references "
            f"SET target_chunk_id = NULL "
            f"WHERE target_chunk_id IN ({placeholders}) "
            f"  AND target_chunk_id NOT IN (SELECT chunk_id FROM chunks)",
            tuple(affected_chunk_ids),
        )
    else:
        cur = conn.execute(
            "UPDATE cross_references "
            "SET target_chunk_id = NULL "
            "WHERE target_chunk_id IS NOT NULL "
            "  AND target_chunk_id NOT IN (SELECT chunk_id FROM chunks)"
        )
    orphans_target = cur.rowcount

    kept = count_before - orphans_source
    print(
        f"  cross_references: rebound {kept}/{count_before} rows "
        f"({orphans_source} source-orphans deleted, "
        f"{orphans_target} target-orphans NULL'd)",
        flush=True,
    )


def chunk_count(conn: sqlite3.Connection, *, lang: str | None = None) -> int:
    """Total chunks in the index, optionally filtered to one language.

    ``lang`` matches the ``chunks_full`` view's ``lang`` column (e.g.
    ``'grc'`` / ``'eng'`` / ``'lat'``). Default is unrestricted.
    """

    if lang is None:
        return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    return conn.execute("SELECT COUNT(*) FROM chunks_full WHERE lang=?", (lang,)).fetchone()[0]


def iter_chunks(conn: sqlite3.Connection, *, lang: str | None = None) -> Iterator[sqlite3.Row]:
    """Yield chunks with the legacy column shape via the ``chunks_full``
    view. Callers (notably ``embed.py``) read ``row['work']`` etc., so
    keep returning that vocabulary."""

    if lang is None:
        cursor = conn.execute("SELECT * FROM chunks_full ORDER BY chunk_id")
    else:
        cursor = conn.execute(
            "SELECT * FROM chunks_full WHERE lang=? ORDER BY chunk_id",
            (lang,),
        )
    yield from cursor


def fetch_chunks(conn: sqlite3.Connection, chunk_ids: Iterable[str]) -> dict[str, sqlite3.Row]:
    """Return chunks-with-joined-metadata, keyed by chunk_id. Reads
    from ``chunks_full`` so callers still see ``row['work']`` /
    ``row['author']`` / ``row['translator']`` etc."""

    ids = list(chunk_ids)
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT * FROM chunks_full WHERE chunk_id IN ({placeholders})", ids
    ).fetchall()
    return {row["chunk_id"]: row for row in rows}


def neighbor_ids(conn: sqlite3.Connection, chunk_id: str, *, window: int = 1) -> list[str]:
    """Return ``[prev..next]`` chunk_ids belonging to the same
    edition/translation as the given chunk_id. ``ord`` is scoped per
    FK target (one of ``edition_id`` / ``translation_id`` is set), so
    neighborhood iteration naturally stays within the same printed
    source — translations don't bleed into the parallel Greek."""

    row = conn.execute(
        "SELECT edition_id, translation_id, ord FROM chunks WHERE chunk_id = ?",
        (chunk_id,),
    ).fetchone()
    if row is None:
        return []
    if row["edition_id"] is not None:
        rows = conn.execute(
            "SELECT chunk_id FROM chunks WHERE edition_id = ? AND ord BETWEEN ? AND ? ORDER BY ord",
            (row["edition_id"], row["ord"] - window, row["ord"] + window),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT chunk_id FROM chunks "
            "WHERE translation_id = ? AND ord BETWEEN ? AND ? "
            "ORDER BY ord",
            (row["translation_id"], row["ord"] - window, row["ord"] + window),
        ).fetchall()
    return [r["chunk_id"] for r in rows]


def fetch_chunk_context(
    conn: sqlite3.Connection,
    chunk_id: str,
    *,
    radius: int,
) -> tuple[sqlite3.Row | None, list[sqlite3.Row], list[sqlite3.Row]]:
    """Return ``(focus, before, after)`` rows from ``chunks_full``.

    Neighbors are scoped by the focus chunk's edition/translation —
    the same semantics as :func:`neighbor_ids`. Scoping by
    ``(work, lang)`` instead (the old behavior) bled context across
    same-titled works: every Luther 1912 book shares its title AND
    lang with the 1545 edition, so context at an edition boundary
    walked into the other translation.
    ``before`` / ``after`` are ascending by ``ord``; both are empty
    when ``radius == 0``. Focus is ``None`` when ``chunk_id`` is unknown.
    """

    focus = conn.execute(
        "SELECT corpus, author, work, lang, chunk_id, section, book, page, "
        "speaker, text, ord, edition_id, translation_id "
        "FROM chunks_full WHERE chunk_id=?",
        (chunk_id,),
    ).fetchone()
    if focus is None:
        return None, [], []
    if focus["edition_id"] is not None:
        fk_col, fk_val = "edition_id", focus["edition_id"]
    else:
        fk_col, fk_val = "translation_id", focus["translation_id"]
    before_rows: list[sqlite3.Row] = []
    after_rows: list[sqlite3.Row] = []
    if radius > 0:
        before_rows = list(
            reversed(
                conn.execute(
                    f"SELECT chunk_id, section, book, page, speaker, text, ord "
                    f"FROM chunks_full WHERE {fk_col}=? AND ord<? "
                    f"ORDER BY ord DESC LIMIT ?",
                    (fk_val, focus["ord"], radius),
                ).fetchall()
            )
        )
        after_rows = conn.execute(
            f"SELECT chunk_id, section, book, page, speaker, text, ord "
            f"FROM chunks_full WHERE {fk_col}=? AND ord>? "
            f"ORDER BY ord ASC LIMIT ?",
            (fk_val, focus["ord"], radius),
        ).fetchall()
    return focus, before_rows, after_rows
