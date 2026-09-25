"""Pre-index snapshot and preserved-state restore for ``minerva index``."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from .. import store
from ..sqlite_util import foreign_keys_disabled, table_exists
from .ddl import chunk_lemmas_kwic_index_creates, chunk_lemmas_kwic_index_drops


def _maybe_snapshot_pre_index(db_path: Path, *, incremental: bool = False) -> None:
    """Back up ``db_path`` to ``<db_path>.bak.pre-index`` when the DB
    carries any of the state a ``--reset`` would otherwise annihilate.

    Seven tables are probed, and what they cost to lose runs from hours
    to unrecoverable: LLM-verified cross_references (hours to
    regenerate), chunk_lemmas (~10 min via LatinCy across grc+lat) and
    its ``chunk_lemma_state`` attempt markers (#263), embeddings (~20 min
    to re-encode the full corpus), ``refs_scan_state`` — the rules-scan
    skip cache, 428,606 markers on the live DB, whose loss turns the next
    `refs build --strategy rules` into a full-corpus pass (#288) — the
    term glossary, which unlike any of those is not regenerable at any
    price because it is curator prose (#192), and
    ``reference_targets``, which is the same kind of prose: its
    ``citation_system`` and ``notes`` are hand-written, and migration
    0012 seeds nine out-of-corpus authors with them.
    ``terms`` is the probe for the whole glossary: the other four
    glossary tables all reach it by foreign key, so a non-empty glossary
    always has a non-empty ``terms``. The snapshot is
    overwritten on each subsequent re-index — one snapshot, not a tower
    of them. No-op for fresh DBs, where the file does not exist yet.

    It is NOT a no-op for an otherwise-empty DB any more, and that is a
    deliberate consequence of counting ``reference_targets`` (#274):
    migration 0012 seeds 21 rows into every migrated DB, so any DB the
    migrations have touched now trips the probe. The alternative — a
    predicate that tries to tell curated targets from the seeds — cannot
    be made sound, because the case #274 names is a curator editing a
    seed row's ``notes`` in place, which changes neither the row count
    nor which ``(author, work)`` pairs are present. The cost is one
    extra whole-file copy in the single window where nothing else is
    populated: a mid-build DB holding chunks but no embeddings, lemmas,
    xrefs or glossary. Any DB large enough for that copy to hurt has
    left that window.

    The copy goes through SQLite's backup API, NOT a filesystem copy:
    the DB runs in WAL mode, and a plain ``cp``/``copy2`` grabs the
    main file without the -wal sibling — silently dropping every
    not-yet-checkpointed commit (exactly the rows this snapshot exists
    to protect) and risking a torn copy if a checkpoint runs
    concurrently.

    Skipped for incremental runs: they only delete/reinsert the scoped
    corpora (the preserved tables aren't wiped), and a full backup of
    a multi-GB DB before every 1.5 s incremental index costs ~50× the
    operation it would guard.
    """

    if not db_path.exists():
        return
    if incremental:
        return
    # Read counts via a brand-new connection so we don't entangle with
    # the index pass's connection lifecycle. Closed immediately so the
    # file lock is free for the actual index run.
    probe = sqlite3.connect(db_path)
    try:
        xref_count = _count_or_zero(probe, "cross_references")
        # Counted separately from cross_references, not inferred from it:
        # targets exist before the first `refs build` and outlive a refs
        # clear-out, and inferring one from the other is exactly the #274
        # defect. Without this, a targets-only DB is never snapshotted,
        # `store.reset_db` unlinks it, and the curator's citation_system
        # and notes come back as whatever migration 0012 seeds.
        target_count = _count_or_zero(probe, "reference_targets")
        lemma_count = _count_or_zero(probe, "chunk_lemmas")
        emb_count = _count_or_zero(probe, "embeddings")
        term_count = _count_or_zero(probe, "terms")
        # Probed in its own right, not inferred from chunk_lemmas: a
        # chunk attempted and found barren has a state row and no lemma
        # rows, so a corpus that produced nothing anywhere would score
        # zero on all four counts above and never be snapshotted (#263).
        # Same reasoning as reference_targets above.
        state_count = _count_or_zero(probe, "chunk_lemma_state")
        # The rules-scan skip cache (#288). Its own count for the same
        # reason again: a DB where `refs build` has run but nothing has
        # been lemmatized, embedded or glossed scores zero on every count
        # above, and unsnapshotted means unrestorable.
        scan_count = _count_or_zero(probe, "refs_scan_state")
        if (
            xref_count == 0
            and target_count == 0
            and lemma_count == 0
            and emb_count == 0
            and term_count == 0
            and state_count == 0
            and scan_count == 0
        ):
            return
        backup = db_path.with_suffix(db_path.suffix + ".bak.pre-index")
        # Clear any prior snapshot (and its own WAL siblings) so the
        # backup lands in a fresh file rather than on top of stale pages.
        store.reset_db(backup)
        dest = sqlite3.connect(backup)
        try:
            probe.backup(dest)
        finally:
            dest.close()
    finally:
        probe.close()
    bits = []
    if xref_count:
        bits.append(f"{xref_count} cross_references")
    if target_count:
        bits.append(f"{target_count} reference_targets")
    if lemma_count:
        bits.append(f"{lemma_count:,} chunk_lemmas")
    if emb_count:
        bits.append(f"{emb_count:,} embeddings")
    if term_count:
        bits.append(f"{term_count:,} terms")
    if state_count:
        bits.append(f"{state_count:,} chunk_lemma_state")
    if scan_count:
        bits.append(f"{scan_count:,} refs_scan_state")
    print(
        f"Snapshotted {' + '.join(bits)} to {backup} before re-index.",
        file=sys.stderr,
    )


def _count_or_zero(conn: sqlite3.Connection, table: str) -> int:
    """``SELECT COUNT(*) FROM <table>`` if the table exists; else 0."""

    if not table_exists(conn, table):
        return 0
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _maybe_restore_preserved_state_from_snapshot(conn: sqlite3.Connection, db_path: Path) -> bool:
    """Replay the pre-index snapshot's preserved rows — xrefs, targets,
    lemma attempt markers, syntax corrections, embeddings and the
    rules-scan cache — into the freshly-migrated DB.

    Returns whether ``chunk_lemmas`` should be restored too, which this
    function no longer does itself: see ``restore_chunk_lemmas_from_snapshot``.
    The decision stays here because this guard is the one that knows the
    database is freshly reset; the caller carries it past ``insert_chunks``.
    """

    backup = db_path.with_suffix(db_path.suffix + ".bak.pre-index")
    if not backup.exists():
        return False
    for table in (
        "cross_references",
        "chunk_lemmas",
        "chunk_lemma_state",
        "embeddings",
        "chunk_syntax_corrections",
        # In the guard for a reason stronger than symmetry:
        # ``refs_scan_state.chunk_id`` is a PRIMARY KEY, and the restore
        # below is a plain INSERT. A non-reset re-index whose live cache
        # is populated but whose other tables are all empty — refs built,
        # nothing lemmatized or embedded yet — would try to insert a
        # second copy of rows that never went away and raise
        # IntegrityError instead of no-opping (#288).
        "refs_scan_state",
    ):
        if _count_or_zero(conn, table):
            return False
    # `reference_targets` is deliberately absent from that "live table is
    # already populated, leave it alone" guard: migration 0012 seeds it,
    # so it is NEVER empty on a migrated DB and including it would make
    # this an unconditional early return.
    probe = sqlite3.connect(backup)
    try:
        xref_count = _count_or_zero(probe, "cross_references")
        # Its own count, and its own restore below. A snapshot can hold
        # targets and zero xrefs — before the first `refs build`, or
        # after a refs clear-out — and gating the targets on the xrefs
        # dropped the curator's `citation_system` and `notes` back to the
        # 0012 seeds without a word (#274).
        target_count = _count_or_zero(probe, "reference_targets")
        lemma_count = _count_or_zero(probe, "chunk_lemmas")
        # The lemmatize attempt markers (#263). Counted separately from
        # chunk_lemmas because a barren chunk has one of these and no
        # lemma rows at all — that is the whole point of the table.
        state_count = _count_or_zero(probe, "chunk_lemma_state")
        emb_count = _count_or_zero(probe, "embeddings")
        # Hand corrections to dependency trees. Unlike everything else
        # here these are not recomputable at any price — they are a
        # scholar's judgement about a sentence. `chunk_syntax_corrections`
        # carries no foreign key for the same reason (migration 0024).
        syntax_count = _count_or_zero(probe, "chunk_syntax_corrections")
        # The rules-scan skip cache (#288). Restoring it does not
        # reintroduce the opposite defect #264 part 1 fixed: the
        # end-of-index orphan sweep drops any marker whose chunk did not
        # come back, and a marker that DID come back on a chunk whose text
        # changed is invalidated by the ``text_hash`` comparison in the
        # skip predicate — which is the check that matters here, because
        # ``chunk_id`` hashes only ``text[:120]`` (#285) and an edit past
        # that point keeps the id.
        scan_count = _count_or_zero(probe, "refs_scan_state")
    finally:
        probe.close()
    if (
        xref_count == 0
        and target_count == 0
        and lemma_count == 0
        and state_count == 0
        and emb_count == 0
        and syntax_count == 0
        and scan_count == 0
    ):
        return False

    with foreign_keys_disabled(conn):
        conn.execute("ATTACH DATABASE ? AS snap", (str(backup),))
        try:
            try:
                # Children first on the way out, parents first on the way
                # back in: `cross_references.target_id` points at
                # `reference_targets`, so the DELETE order is xrefs →
                # targets and the restore order is targets → xrefs. The
                # two pairs are otherwise independent — a targets-only
                # snapshot round-trips without an xref in sight (#274).
                xref_restored = 0
                target_restored = 0
                if xref_count:
                    conn.execute("DELETE FROM cross_references")
                if target_count:
                    conn.execute("DELETE FROM reference_targets")
                    target_restored = _restore_from_snap(conn, "reference_targets")
                if xref_count:
                    xref_restored = _restore_from_snap(conn, "cross_references")
                state_restored = 0
                if state_count:
                    state_restored = _restore_from_snap(conn, "chunk_lemma_state")
                syntax_restored = 0
                if syntax_count:
                    syntax_restored = _restore_from_snap(conn, "chunk_syntax_corrections")
                scan_restored = 0
                if scan_count:
                    scan_restored = _restore_from_snap(conn, "refs_scan_state")
                emb_restored = 0
                if emb_count:
                    emb_restored = _restore_from_snap(conn, "embeddings")
                    from .embeddings import bump_embedding_generation

                    bump_embedding_generation(conn)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            if xref_restored or target_restored:
                print(
                    f"Restored {xref_restored} cross_references + "
                    f"{target_restored} reference_targets from {backup}; "
                    f"rebind will rebind to the new chunks.",
                    file=sys.stderr,
                )
            if syntax_restored:
                print(
                    f"Restored {syntax_restored:,} chunk_syntax_corrections from {backup}.",
                    file=sys.stderr,
                )
            if state_restored:
                print(
                    f"Restored {state_restored:,} chunk_lemma_state from {backup}; "
                    f"chunks whose text changed will be re-lemmatized.",
                    file=sys.stderr,
                )
            if emb_restored:
                print(
                    f"Restored {emb_restored:,} embeddings from {backup}; "
                    f"orphan sweep will drop rows whose chunk_id changed.",
                    file=sys.stderr,
                )
            if scan_restored:
                print(
                    f"Restored {scan_restored:,} refs_scan_state from {backup}; "
                    f"`refs build --strategy rules` will skip these chunks "
                    f"instead of re-scanning the corpus.",
                    file=sys.stderr,
                )
        finally:
            conn.execute("DETACH DATABASE snap")
    return lemma_count > 0


# ══════════════════════════════════════════════════════════════════
# Lemma rows (#649)
# ══════════════════════════════════════════════════════════════════
#
# Restored after `insert_chunks`, not with the tables above, because each
# row carries a copy of its chunk's `ord`, resolved language and `work_id`
# (migration 0036) and `--reset` changes all three: `ord` is renumbered in
# JSONL order and every `works.id` is reassigned. Restored before the
# chunks exist, a row can only bring back the snapshot's values, and each
# chunk insert then has to rewrite its lemma rows through the triggers —
# 26.1M rows whose locators sit in two indexes. Measured on a clone,
# rewriting `work_id` alone that way was stopped after more than five
# minutes, on a `--reset` that main completes in 8 m 31 s in all. Joined
# to the new `chunks`, each row is written once with the right values, and
# the triggers find nothing to correct.
#
# The inner join also leaves out every row whose chunk did not come back —
# the same rows `_sweep_orphan_chunk_lemmas` would delete a moment later.

# Written by the restore rather than copied: the snapshot's values are the
# ones that went stale.
_LEMMA_LOCATORS = ("chunk_ord", "lang_resolved", "work_id")


def restore_chunk_lemmas_from_snapshot(conn: sqlite3.Connection, db_path: Path) -> int:
    """Copy the pre-index snapshot's ``chunk_lemmas`` into the live table,
    taking each row's locators from its chunk as ``insert_chunks`` just
    wrote it. Returns the number of rows restored.

    Call only when ``_maybe_restore_preserved_state_from_snapshot`` said so:
    an incremental run takes no snapshot, so the newest one on disk can
    predate a deliberate clear-out, and restoring it would resurrect it.
    """

    backup = db_path.with_suffix(db_path.suffix + ".bak.pre-index")
    if not backup.exists() or _count_or_zero(conn, "chunk_lemmas"):
        return 0
    conn.execute("ATTACH DATABASE ? AS lemmasnap", (str(backup),))
    try:
        live = [row[1] for row in conn.execute("PRAGMA table_info(chunk_lemmas)")]
        snapped = {row[1] for row in conn.execute("PRAGMA lemmasnap.table_info(chunk_lemmas)")}
        copied = [c for c in live if c in snapped and c not in _LEMMA_LOCATORS]
        cols = ", ".join(copied)
        try:
            # The two KWIC indexes come off for the copy and are rebuilt
            # after it, in one transaction. Inserted in `chunk_id` order into
            # two lemma-keyed B-trees far larger than the page cache, the
            # rows landed at random: a full `--reset` measured 26 m 01 s this
            # way against main's 8 m 31 s. `CREATE INDEX` sorts once instead,
            # and the same `--reset` with the rebuild measured 8 m 06 s.
            #
            # The explicit BEGIN is what makes it one transaction: without an
            # open one, `sqlite3` runs DDL in autocommit, so a copy that
            # failed would roll back its rows and leave both indexes gone.
            conn.execute("BEGIN")
            for stmt in chunk_lemmas_kwic_index_drops():
                conn.execute(stmt)
            # Foreign keys stay on: the inner join means every row written
            # has its chunk.
            conn.execute(
                f"INSERT INTO chunk_lemmas ({cols}, {', '.join(_LEMMA_LOCATORS)}) "
                f"SELECT {', '.join('s.' + c for c in copied)}, "
                f"       c.ord, COALESCE(s.lang, c.lang), c.work_id "
                f"FROM lemmasnap.chunk_lemmas s JOIN chunks c ON c.chunk_id = s.chunk_id"
            )
            for stmt in chunk_lemmas_kwic_index_creates():
                conn.execute(stmt)
            restored = conn.execute("SELECT COUNT(*) FROM chunk_lemmas").fetchone()[0]
            snapped_n = conn.execute("SELECT COUNT(*) FROM lemmasnap.chunk_lemmas").fetchone()[0]
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.execute("DETACH DATABASE lemmasnap")
    print(
        f"Restored {restored:,} chunk_lemmas from {backup}; "
        f"{snapped_n - restored:,} left behind with chunks whose chunk_id changed.",
        file=sys.stderr,
    )
    return restored


# ══════════════════════════════════════════════════════════════════
# Term glossary (#192)
# ══════════════════════════════════════════════════════════════════
#
# The glossary restore is deliberately NOT part of
# `_maybe_restore_preserved_state_from_snapshot`, which runs *before*
# `insert_chunks`. Three reasons:
#
#   1. Every glossary row reaches the corpus through a surrogate id —
#      `term_occurrences.edition_id`, `term_renderings.translation_id`
#      — and those rows do not exist until `insert_chunks` has built
#      `works`/`editions`/`translations`.
#   2. Those surrogate ids are handed out by insertion order, so a
#      `--reset` reshuffles them (#193: aristotle.grc.yaml's edition 58
#      is Homer's Iliad today). Copying the raw column across would
#      not merely lose the glossary — it would silently reattach
#      Aristotle's Greek vocabulary to whatever now holds that id.
#      Every FK below is therefore rebound through a NATURAL key.
#   3. Running after the insert means the orphan question is answered
#      by construction: an occurrence whose chunk no longer exists
#      simply fails its join, so there is no separate sweep and no
#      window where FK-invalid rows sit in the table.
#
# `terms` and `term_relations` are the exception — their id space is
# internal to the glossary, so they carry across on their own natural
# key `(source_form, source_language)`.

# Resolves a snapshot `editions` row to the rebuilt one. `editions` is
# UNIQUE (work_id, name, year); `works` is UNIQUE (author, title).
# Language is in the join for defence, not identity.
_EDITION_REBIND = """
    JOIN glossnap.editions s_ed ON s_ed.id = s_occ.edition_id
    JOIN glossnap.works    s_ew ON s_ew.id = s_ed.work_id
    JOIN works    n_ew ON n_ew.author = s_ew.author AND n_ew.title = s_ew.title
    JOIN editions n_ed ON n_ed.work_id  = n_ew.id
                      AND n_ed.name     = s_ed.name
                      AND n_ed.language = s_ed.language
                      AND n_ed.year IS s_ed.year
"""

# Same for `translations`, UNIQUE (work_id, translator_name, year, language).
# `{src}` is the snapshot-side table holding the translation_id column.
_TRANSLATION_REBIND = """
    JOIN glossnap.translations s_tr ON s_tr.id = {src}.translation_id
    JOIN glossnap.works        s_tw ON s_tw.id = s_tr.work_id
    JOIN works        n_tw ON n_tw.author = s_tw.author AND n_tw.title = s_tw.title
    JOIN translations n_tr ON n_tr.work_id         = n_tw.id
                          AND n_tr.translator_name = s_tr.translator_name
                          AND n_tr.language        = s_tr.language
                          AND n_tr.year IS s_tr.year
"""

# Snapshot term → rebuilt term, by the glossary-internal natural key.
_TERM_REBIND = """
    JOIN glossnap.terms s_t ON s_t.id = {src}.term_id
    JOIN terms n_t ON n_t.source_form     = s_t.source_form
                  AND n_t.source_language = s_t.source_language
"""


def restore_glossary_from_snapshot(conn: sqlite3.Connection, db_path: Path) -> None:
    """Bring the five ``terms*`` tables back from the pre-index snapshot,
    rebinding every foreign key through a natural key.

    Runs after ``insert_chunks``. Additive and idempotent: every insert
    is ``OR IGNORE`` against the table's own natural UNIQUE, so a
    non-reset re-index (where the live glossary was never dropped) is a
    no-op rather than a constraint crash.
    """

    backup = db_path.with_suffix(db_path.suffix + ".bak.pre-index")
    if not backup.exists():
        return
    probe = sqlite3.connect(backup)
    try:
        if not table_exists(probe, "terms"):
            return
        if _count_or_zero(probe, "terms") == 0:
            return
    finally:
        probe.close()

    conn.execute("ATTACH DATABASE ? AS glossnap", (str(backup),))
    try:
        try:
            counts = _restore_glossary_tables(conn)
            dropped = _unrestorable_occurrences(conn)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.execute("DETACH DATABASE glossnap")

    _report_glossary_restore(counts, dropped, backup)


def _restore_glossary_tables(conn: sqlite3.Connection) -> dict[str, int]:
    """The five inserts, in FK-dependency order. Returns rows written
    per table (0 when everything was already present)."""

    written: dict[str, int] = {}

    written["terms"] = conn.execute(
        """
        INSERT OR IGNORE INTO terms
            (source_form, source_language, transliteration, lemma,
             short_gloss, long_description)
        SELECT source_form, source_language, transliteration, lemma,
               short_gloss, long_description
        FROM glossnap.terms
        """
    ).rowcount

    written["term_relations"] = conn.execute(
        """
        INSERT OR IGNORE INTO term_relations
            (term_id, related_term_id, relation_kind, notes)
        SELECT n_a.id, n_b.id, s_rel.relation_kind, s_rel.notes
        FROM glossnap.term_relations s_rel
        JOIN glossnap.terms s_a ON s_a.id = s_rel.term_id
        JOIN glossnap.terms s_b ON s_b.id = s_rel.related_term_id
        JOIN terms n_a ON n_a.source_form = s_a.source_form
                      AND n_a.source_language = s_a.source_language
        JOIN terms n_b ON n_b.source_form = s_b.source_form
                      AND n_b.source_language = s_b.source_language
        """
    ).rowcount

    written["term_renderings"] = conn.execute(
        f"""
        INSERT OR IGNORE INTO term_renderings
            (term_id, translation_id, default_rendering, translator_note)
        SELECT n_t.id, n_tr.id, s_rd.default_rendering, s_rd.translator_note
        FROM glossnap.term_renderings s_rd
        {_TERM_REBIND.format(src="s_rd")}
        {_TRANSLATION_REBIND.format(src="s_rd")}
        """
    ).rowcount

    # `work_id` is denormalized from the edition, so it is taken from the
    # REBUILT edition's work rather than copied — the schema requires the
    # two to agree.
    written["term_occurrences"] = conn.execute(
        f"""
        INSERT OR IGNORE INTO term_occurrences
            (term_id, edition_id, work_id, source_chunk_id, source_start,
             source_end, context_snippet, location_kind, location_payload,
             location_sort_key, tradition, source_form_snapshot, instance_index)
        SELECT n_t.id, n_ed.id, n_ew.id, s_occ.source_chunk_id,
               s_occ.source_start, s_occ.source_end, s_occ.context_snippet,
               s_occ.location_kind, s_occ.location_payload,
               s_occ.location_sort_key, s_occ.tradition,
               s_occ.source_form_snapshot, s_occ.instance_index
        FROM glossnap.term_occurrences s_occ
        {_TERM_REBIND.format(src="s_occ")}
        {_EDITION_REBIND}
        JOIN chunks c ON c.chunk_id = s_occ.source_chunk_id
        """
    ).rowcount

    # The parent occurrence is found again through its shadow address —
    # the same tuple the UNIQUE constraint is keyed on — which is what
    # makes this survivable without preserving `term_occurrences.id`.
    written["occurrence_renderings"] = conn.execute(
        f"""
        INSERT OR IGNORE INTO occurrence_renderings
            (occurrence_id, translation_id, translation_chunk_id,
             translation_start, translation_end, rendered_text, notes,
             source_locator_sort_key, rendered_form_snapshot, instance_index)
        SELECT n_occ.id, n_tr.id, s_or.translation_chunk_id,
               s_or.translation_start, s_or.translation_end,
               s_or.rendered_text, s_or.notes, s_or.source_locator_sort_key,
               s_or.rendered_form_snapshot, s_or.instance_index
        FROM glossnap.occurrence_renderings s_or
        JOIN glossnap.term_occurrences s_occ ON s_occ.id = s_or.occurrence_id
        {_EDITION_REBIND}
        JOIN term_occurrences n_occ
              ON n_occ.edition_id           = n_ed.id
             AND n_occ.location_sort_key    = s_occ.location_sort_key
             AND n_occ.source_form_snapshot = s_occ.source_form_snapshot
             AND n_occ.instance_index       = s_occ.instance_index
        {_TRANSLATION_REBIND.format(src="s_or")}
        JOIN chunks c ON c.chunk_id = s_or.translation_chunk_id
        """
    ).rowcount

    return written


def _unrestorable_occurrences(conn: sqlite3.Connection) -> dict[str, int]:
    """Split the occurrences that did NOT come back by cause, so the
    operator sees which kind of loss happened.

    ``chunk_gone`` is the expected, benign case: the chunk's text
    changed, its content hash changed with it, and the stored character
    offsets no longer address anything. ``work_gone`` means the edition
    itself is absent from the rebuilt corpus — a dropped or renamed
    work, which is worth a second look.
    """

    chunk_gone = conn.execute(
        """
        SELECT COUNT(*) FROM glossnap.term_occurrences s_occ
        WHERE NOT EXISTS (
            SELECT 1 FROM chunks c WHERE c.chunk_id = s_occ.source_chunk_id
        )
        """
    ).fetchone()[0]
    resolvable_editions = conn.execute(
        f"""
        SELECT COUNT(*) FROM glossnap.term_occurrences s_occ
        {_EDITION_REBIND}
        JOIN chunks c ON c.chunk_id = s_occ.source_chunk_id
        """
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM glossnap.term_occurrences").fetchone()[0]
    return {
        "chunk_gone": chunk_gone,
        "work_gone": total - chunk_gone - resolvable_editions,
    }


def _report_glossary_restore(counts: dict[str, int], dropped: dict[str, int], backup: Path) -> None:
    """Print what came back and what didn't. Silent when the snapshot
    added nothing and lost nothing — the common non-reset case."""

    restored = ", ".join(f"{n:,} {table}" for table, n in counts.items() if n)
    if restored:
        print(f"Restored glossary from {backup}: {restored}.", file=sys.stderr)
    if dropped["chunk_gone"]:
        print(
            f"Dropped {dropped['chunk_gone']:,} term_occurrences (chunks whose "
            f"text changed — the stored offsets no longer address anything); "
            f"re-run `minerva terms import` to re-find them.",
            file=sys.stderr,
        )
    if dropped["work_gone"]:
        print(
            f"Dropped {dropped['work_gone']:,} term_occurrences whose edition is "
            f"absent from the rebuilt corpus (renamed or removed work).",
            file=sys.stderr,
        )


def _restore_from_snap(conn: sqlite3.Connection, table: str) -> int:
    """Bulk-copy ``snap.<table>`` into the live ``<table>``.

    Only the columns the two schemas have in common are copied. The
    snapshot is taken at the top of ``cmd_index``, *before* the fresh DB
    is migrated, so on the first run after a migration that adds a column
    the live table has a column the snapshot does not — and copying by
    the live column list raises ``no such column``, taking the whole
    index run with it. Migration 0028 (``refs_scan_state.rules_hash``,
    #287) is the first column-add to an already-preserved table; the
    columns it leaves behind take their declared default, which is why
    such a column must be nullable or defaulted.

    The reverse case — a column present in the snapshot and dropped
    since — is covered by the same intersection.
    """

    live = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    snapped = {row[1] for row in conn.execute(f"PRAGMA snap.table_info({table})")}
    cols = ", ".join(name for name in live if name in snapped)
    conn.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM snap.{table}")
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
