"""0036_chunk_lemma_locators.py — copy each chunk's locators onto its lemma rows (#649).

`lemma_detail` (the Concordance's KWIC panel) cost 1,627 ms for `der`/deu and
1,317 ms for `the`/eng, measured on the live index. #649 blamed the page
query's sort. Measured, the sort is free — `ORDER BY … LIMIT 50` keeps a
50-row heap — and a `COUNT(*)` over the same join costs the same as the page:

                                    deu/haben   deu/der    eng/the
    matching rows                      57,677   671,411    597,882
    seek only (fold index)             0.6 ms     8.1 ms     7.3 ms
    seek + join, COUNT(*)            114.2 ms   469.7 ms   462.8 ms
    shipped page query               111.3 ms   462.1 ms   521.3 ms

The cost is the per-row probe into `chunks` for `lang`, `ord` and `work`,
paid for every matching row before any is discarded, by both statements.
`COALESCE(cl.lang, cf.lang) = ?` alone forces it. The aggregate pass
(1,176 of `der`'s 1,627 ms) visits every row by design.

So the three values move onto `chunk_lemmas`, where an index can hold them.
Measured on an APFS clone of snapshot 20260924T230905Z-kwic-denorm-prototype,
every rewritten result compared row-for-row with the shipped query:

                     page (off=0)        aggregate pass
                     old      new        old       new
    deu/haben      113.5 ms  0.1 ms    147.6 ms   6.8 ms
    deu/der        504.3     0.1      1175.7     57.1
    eng/the        552.8     0.1       828.2     40.0
    grc/ὁ          267.3     0.2       551.3     36.1

WHY TRIGGERS, AND NOT A REFRESH CALL
--------------------------------------------------------------------
A copy has to follow its source, and `chunks` moves under `chunk_lemmas` in
a way that is easy to miss: `index --reset` renumbers `ord` (a per-(work,
lang) counter assigned in JSONL order) and reassigns every `works.id`, then
bulk-restores `chunk_lemmas` by `chunk_id` from the pre-index snapshot. A
restored row keeps a valid `chunk_id` and its old locators, joins fine, and
serves KWIC rows in the wrong order or under the wrong work.

A refresh called after `insert_chunks` would fix that path and only that
path — the lemmatize writer, every test fixture that plants lemma rows, and
whatever writes `chunks` next would each have to remember it. It is also
not cheap to call defensively: a mismatch-guarded refresh with nothing to
change measured 46 s on the full table, paid on every `index` including an
incremental one that touched a single corpus.
Triggers make every writer correct without knowing about any of this.

The one path triggers make slow is the one they were most needed for.
Restored before `insert_chunks`, 26.1M lemma rows arrived with the
snapshot's locators and every chunk insert rewrote its rows' indexed
columns; on a clone, rewriting `work_id` alone that way was stopped after
more than five minutes, on a `--reset` main completes in 8 m 31 s in all.
So the `--reset` restore now runs
after the insert and writes each row's locators from the new `chunks` in
the same `INSERT … SELECT` (`store/preserved_state.py`,
`restore_chunk_lemmas_from_snapshot`), dropping the two indexes below for
the copy and rebuilding them after it. A full `--reset` of the live corpus
measured 8 m 06 s that way, against main's 8 m 31 s, with zero drift over
all 26,119,646 rows. The triggers find nothing to correct there, and
remain the guarantee for every other writer.

On an established index this migration itself took 214 s — a one-off
stall on the first `open_db` after it lands, `serve` included.

The `chunk_lemmas` insert trigger fires only when a locator is NULL, so a
writer that supplies them — that restore — pays nothing for it.

WHY `chunk_lemmas_by_fold` GOES
--------------------------------------------------------------------
Both new indexes lead with `lemma_fold`, and the KWIC endpoint is the only
reader of that column — every one of its statements also filters on the
language — so the old single-column index is a strict prefix nobody needs:
447 MB, and one more B-tree for every lemmatize write to maintain.
"""

from __future__ import annotations

import sqlite3

from minerva.store.ddl import chunk_lemmas_kwic_index_creates

_COLUMNS = (
    ("chunk_ord", "INTEGER"),
    # `COALESCE(chunk_lemmas.lang, chunks.lang)`, resolved once. `lang` stays
    # the sparse cross-script override migration 0032 made it; this is the
    # value every consumer used to compute per row.
    ("lang_resolved", "TEXT"),
    # No REFERENCES: `works.id` is reassigned on every `--reset`, and the
    # restore runs with foreign keys off. The triggers keep it right.
    ("work_id", "INTEGER"),
)

# `chunk_ord IS NULL` is the re-entrancy guard: a retry fills only what an
# interrupted attempt left, and a fresh database matches no rows.
_BACKFILL = """
UPDATE chunk_lemmas
   SET chunk_ord     = c.ord,
       lang_resolved = COALESCE(chunk_lemmas.lang, c.lang),
       work_id       = c.work_id
  FROM chunks c
 WHERE c.chunk_id = chunk_lemmas.chunk_id
   AND chunk_lemmas.chunk_ord IS NULL
"""

# One body for both `chunks` triggers: a chunk inserted and a chunk whose
# locators changed need the same thing done to its lemma rows.
_PUSH_TO_LEMMAS = """BEGIN
        UPDATE chunk_lemmas
           SET chunk_ord     = NEW.ord,
               lang_resolved = COALESCE(lang, NEW.lang),
               work_id       = NEW.work_id
         WHERE chunk_id = NEW.chunk_id;
    END"""

_TRIGGERS = (
    # A lemma row written without locators — lemmatize, a test fixture, a
    # restore from a snapshot older than this migration — takes its chunk's.
    """
    CREATE TRIGGER IF NOT EXISTS chunk_lemmas_locators_ai
    AFTER INSERT ON chunk_lemmas
    WHEN NEW.chunk_ord IS NULL OR NEW.lang_resolved IS NULL OR NEW.work_id IS NULL
    BEGIN
        UPDATE chunk_lemmas
           SET chunk_ord     = (SELECT ord FROM chunks WHERE chunk_id = NEW.chunk_id),
               lang_resolved = COALESCE(
                   NEW.lang, (SELECT lang FROM chunks WHERE chunk_id = NEW.chunk_id)),
               work_id       = (SELECT work_id FROM chunks WHERE chunk_id = NEW.chunk_id)
         WHERE rowid = NEW.rowid;
    END
    """,
    # The override changing moves the resolved language with it.
    """
    CREATE TRIGGER IF NOT EXISTS chunk_lemmas_lang_au
    AFTER UPDATE OF lang ON chunk_lemmas
    BEGIN
        UPDATE chunk_lemmas
           SET lang_resolved = COALESCE(
                   NEW.lang, (SELECT lang FROM chunks WHERE chunk_id = NEW.chunk_id))
         WHERE rowid = NEW.rowid;
    END
    """,
    # A chunk (re-)inserted pushes its locators onto whatever lemma rows
    # already carry its id. `insert_chunks` uses INSERT OR REPLACE, so this
    # is the incremental re-index's path: that run renumbers `ord` for its
    # corpora and leaves their lemma rows in place.
    f"""
    CREATE TRIGGER IF NOT EXISTS chunks_locators_ai
    AFTER INSERT ON chunks
    {_PUSH_TO_LEMMAS}
    """,
    f"""
    CREATE TRIGGER IF NOT EXISTS chunks_locators_au
    AFTER UPDATE OF ord, lang, work_id ON chunks
    {_PUSH_TO_LEMMAS}
    """,
)


def apply(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(chunk_lemmas)")}
    for name, decl in _COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE chunk_lemmas ADD COLUMN {name} {decl}")

    # Backfill before indexing: filling the columns under two live indexes
    # would maintain both B-trees row by row instead of building them once.
    conn.execute(_BACKFILL)
    for stmt in _TRIGGERS:
        conn.execute(stmt)
    for stmt in chunk_lemmas_kwic_index_creates():
        conn.execute(stmt)
    conn.execute("DROP INDEX IF EXISTS chunk_lemmas_by_fold")
