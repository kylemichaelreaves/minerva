"""0003_chunks_backfill.py — normalize the legacy stringly-typed columns
on ``chunks`` into FKs against ``works`` / ``editions`` / ``translations``.

What this migration does, in order
----------------------------------
1.  ADD COLUMN ``chunks.edition_id`` and ``chunks.translation_id``.
2.  For each distinct ``(corpus, author, work)`` triple in chunks,
    INSERT a ``works`` row. ``original_language`` is derived from the
    chunks data; ``citation_system`` from a corpus → system map.
3.  For each distinct ``(work, lang, translator, edition_year)`` tuple,
    INSERT an ``editions`` row if it represents the original-language
    edition, or a ``translations`` row otherwise.
4.  UPDATE chunks to set ``edition_id`` / ``translation_id`` by joining
    on the above tuple. Exactly one of the two columns ends up set per
    row; the rest enforce that via the CHECK constraint applied when
    the chunks table is rebuilt below.
5.  Drop legacy indexes referencing the soon-to-disappear columns.
6.  ``ALTER TABLE chunks DROP COLUMN`` for the redundant five:
    ``corpus``, ``author``, ``work``, ``translator``, ``edition_year``.
7.  Apply the CHECK constraint via table-rebuild (SQLite does not
    support adding a CHECK to an existing table). FTS5 triggers are
    rebuilt against the new chunks table.
8.  Recreate indexes pointed at the new FK columns.
9.  Create the ``chunks_full`` VIEW that recomposes the legacy column
    shape via JOIN. Existing call sites switch their FROM clause from
    ``chunks`` to ``chunks_full`` and keep their dict-based access.

After this runs, ``chunks`` holds: chunk_id, edition_id, translation_id,
lang, section, book, page, speaker, source_file, text, ord. Everything
else lives in works / editions / translations.

Rule for splitting Editions vs. Translations
--------------------------------------------
* A chunk whose ``lang`` matches its parent work's ``original_language``
  belongs in an Edition. The ``translator`` field in such chunks holds
  the critical-edition info (e.g., "Platonis Opera, ed. John Burnet") —
  it becomes ``editions.name``.
* All other chunks belong in a Translation. The ``translator`` field
  holds the actual translator's name.

This handles the Plato/Aristotle pattern (where a Greek `chunks.work`
maps to one Edition + one Translation), the Hegel/Kant German-original
pattern (one Edition per `chunks.work`), and the Hegel-translation
pattern (translations exist under separately-titled `chunks.work`
strings with no parent original — each becomes a Work whose
original_language is the translation's own language, matching the data
as-stored).
"""

from __future__ import annotations

import sqlite3

# Use absolute imports because the runner loads this file via
# spec_from_file_location with a synthetic module name — relative
# imports against `minerva.migrations` are unreachable from there.
from minerva.migrations.runtime_helpers import (
    _CITATION_SYSTEM_BY_CORPUS,
    _ORIGINAL_LANG_BY_CORPUS,
    parse_year,
)
from minerva.sqlite_util import execute_script_statements


def apply(conn: sqlite3.Connection) -> None:
    # Idempotency: if `chunks` already lacks the legacy stringly-typed
    # columns, this migration has nothing to do. A fresh DB created
    # from store.SCHEMA arrives in the post-0003 shape directly; this
    # migration only does work for databases that were on the legacy
    # shape before 0003 was written.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(chunks)")}
    if "work" not in cols:
        # Already migrated. Make sure the chunks_full view exists
        # (fresh-DB SCHEMA doesn't create it) and we're done.
        _ensure_chunks_full_view(conn)
        return

    # FK enforcement during the rebuild causes the legacy chunks table
    # to look broken to its FK referrers (term_occurrences,
    # occurrence_renderings) while we're in flight. Disable for the
    # migration; re-enable at exit so callers see the same pragma
    # state they had on entry. The PRAGMA must be set BEFORE the
    # explicit BEGIN (it's a silent no-op inside a transaction), and
    # the BEGIN must be explicit because the ALTER TABLEs below are
    # DDL, which doesn't auto-begin a transaction — without it a
    # mid-migration failure would leave the ALTERs committed and the
    # re-apply would fail on "duplicate column".
    fk_prev = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        if not conn.in_transaction:
            conn.execute("BEGIN")
        _apply_inner(conn)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA foreign_keys = {'ON' if fk_prev else 'OFF'}")


def _ensure_chunks_full_view(conn: sqlite3.Connection) -> None:
    """Create the chunks_full convenience view. Idempotent."""

    conn.execute("""
        CREATE VIEW IF NOT EXISTS chunks_full AS
        SELECT
            c.chunk_id,
            c.lang,
            c.section,
            c.book,
            c.page,
            c.speaker,
            c.source_file,
            c.text,
            c.ord,
            c.edition_id,
            c.translation_id,
            w.id      AS work_id,
            w.author  AS author,
            w.title   AS work,
            LOWER(w.author) AS corpus,
            COALESCE(e.name, t.translator_name) AS translator,
            COALESCE(e.year, t.year)            AS edition_year,
            CASE WHEN c.edition_id IS NOT NULL THEN 1 ELSE 0 END AS is_original
        FROM chunks c
        LEFT JOIN editions     e ON e.id = c.edition_id
        LEFT JOIN translations t ON t.id = c.translation_id
        JOIN works w ON w.id = COALESCE(e.work_id, t.work_id);
    """)


def _apply_inner(conn: sqlite3.Connection) -> None:

    # ── 1. ADD COLUMNs ────────────────────────────────────────────────
    conn.execute("ALTER TABLE chunks ADD COLUMN edition_id     INTEGER")
    conn.execute("ALTER TABLE chunks ADD COLUMN translation_id INTEGER")

    # ── 2. Backfill `works` ───────────────────────────────────────────
    # For each distinct (corpus, author, work), determine original_language:
    #   * if the work has chunks where translator='(Original)' or NULL,
    #     use the lang of those (typically one lang);
    #   * else, fall back to the corpus's primary original_language IF
    #     any chunk of this work is in that language;
    #   * else, use whatever single lang the work has.
    work_rows = conn.execute("""
        SELECT corpus, author, work,
               GROUP_CONCAT(DISTINCT lang) AS langs,
               GROUP_CONCAT(DISTINCT CASE
                  WHEN translator IS NULL OR translator = '(Original)' THEN lang
               END) AS original_langs
        FROM chunks
        GROUP BY corpus, author, work
        ORDER BY corpus, author, work
    """).fetchall()

    work_id_by_key: dict[tuple[str, str], int] = {}
    for corpus, author, work, langs_csv, original_langs_csv in work_rows:
        langs = set((langs_csv or "").split(","))
        original_langs = set(filter(None, (original_langs_csv or "").split(",")))
        primary = _ORIGINAL_LANG_BY_CORPUS.get(corpus, "eng")
        if original_langs:
            # Prefer the corpus-canonical original language if it appears
            # in the (Original)/NULL marker set; otherwise pick the
            # alphabetic-first member (deterministic, just for reproducibility).
            chosen = primary if primary in original_langs else sorted(original_langs)[0]
        elif primary in langs:
            chosen = primary
        else:
            # No (Original)-marked chunks AND no chunks in the corpus's
            # canonical language — this is a translation-only work
            # (e.g., Plato Euthyphro in English, with no paired Greek in
            # the corpus). Stub the Work with the corpus's canonical
            # original_language; no Edition row will be created. The
            # chunks all end up as Translations against this stub Work.
            chosen = primary
        citation_system = _CITATION_SYSTEM_BY_CORPUS.get(corpus, "paragraph")
        cur = conn.execute(
            "INSERT INTO works (author, title, original_language, citation_system) "
            "VALUES (?, ?, ?, ?)",
            (author, work, chosen, citation_system),
        )
        work_id_by_key[(author, work)] = int(cur.lastrowid)

    # ── 3. Backfill editions + translations ───────────────────────────
    tuple_rows = conn.execute("""
        SELECT corpus, author, work, lang,
               COALESCE(translator, '(Original)') AS translator,
               edition_year
        FROM chunks
        GROUP BY corpus, author, work, lang, translator, edition_year
    """).fetchall()

    edition_id_by_key: dict[tuple[int, str, str, str | None], int] = {}
    translation_id_by_key: dict[tuple[int, str, str, str | None], int] = {}
    for corpus, author, work, lang, translator, edition_year in tuple_rows:
        work_id = work_id_by_key[(author, work)]
        # Get the work's original_language back so we know which slot.
        original_language = conn.execute(
            "SELECT original_language FROM works WHERE id = ?", (work_id,)
        ).fetchone()[0]
        is_edition = (lang == original_language)
        year = parse_year(edition_year)
        if is_edition:
            name = translator if translator != "(Original)" else work
            cur = conn.execute(
                "INSERT INTO editions (work_id, name, language, year, notes) "
                "VALUES (?, ?, ?, ?, ?)",
                (work_id, name, lang, year, None),
            )
            edition_id_by_key[(work_id, lang, translator, edition_year)] = int(cur.lastrowid)
        else:
            cur = conn.execute(
                "INSERT INTO translations "
                "  (work_id, translator_name, year, language, edition_notes) "
                "VALUES (?, ?, ?, ?, ?)",
                (work_id, translator, year, lang, None),
            )
            translation_id_by_key[(work_id, lang, translator, edition_year)] = int(cur.lastrowid)

    # ── 4. Point each chunk at its edition or translation ─────────────
    chunk_updates = conn.execute("""
        SELECT chunk_id, author, work, lang,
               COALESCE(translator, '(Original)') AS translator,
               edition_year
        FROM chunks
    """).fetchall()

    update_batch: list[tuple[int | None, int | None, str]] = []
    for chunk_id, author, work, lang, translator, edition_year in chunk_updates:
        work_id = work_id_by_key[(author, work)]
        ed = edition_id_by_key.get((work_id, lang, translator, edition_year))
        tr = translation_id_by_key.get((work_id, lang, translator, edition_year))
        if ed is None and tr is None:
            raise RuntimeError(
                f"chunk {chunk_id} could not be matched to an edition or "
                f"translation (author={author!r}, work={work!r}, lang={lang!r}, "
                f"translator={translator!r}, edition_year={edition_year!r})"
            )
        update_batch.append((ed, tr, chunk_id))
    conn.executemany(
        "UPDATE chunks SET edition_id = ?, translation_id = ? WHERE chunk_id = ?",
        update_batch,
    )

    # ── 5-7. Drop legacy indexes; rebuild chunks without legacy cols ──
    # We rebuild the table (rather than relying on multiple
    # `ALTER TABLE ... DROP COLUMN`) because we also want to add a CHECK
    # constraint requiring exactly one FK to be set per row. SQLite
    # can't add a CHECK to an existing table; the canonical rebuild
    # dance is the way. Statement-by-statement (not executescript) so
    # the whole rebuild stays inside this migration's transaction.
    execute_script_statements(conn, """
        DROP INDEX IF EXISTS chunks_corpus;
        DROP INDEX IF EXISTS chunks_work_ord;

        -- FTS5 triggers reference the chunks table; drop them now and
        -- recreate after the rebuild, against the new shape.
        DROP TRIGGER IF EXISTS chunks_ai;
        DROP TRIGGER IF EXISTS chunks_ad;
        DROP TRIGGER IF EXISTS chunks_au;

        CREATE TABLE chunks_new (
            chunk_id        TEXT PRIMARY KEY,
            edition_id      INTEGER REFERENCES editions(id) ON DELETE CASCADE,
            translation_id  INTEGER REFERENCES translations(id) ON DELETE CASCADE,
            lang            TEXT NOT NULL,
            section         TEXT,
            book            TEXT,
            page            TEXT,
            speaker         TEXT,
            source_file     TEXT NOT NULL,
            text            TEXT NOT NULL,
            ord             INTEGER NOT NULL,
            CHECK ((edition_id IS NULL) <> (translation_id IS NULL))
        );

        INSERT INTO chunks_new (
            chunk_id, edition_id, translation_id, lang,
            section, book, page, speaker, source_file, text, ord
        )
        SELECT
            chunk_id, edition_id, translation_id, lang,
            section, book, page, speaker, source_file, text, ord
        FROM chunks;

        DROP TABLE chunks;
        ALTER TABLE chunks_new RENAME TO chunks;

        -- ── 8. Indexes ─────────────────────────────────────────────
        CREATE INDEX chunks_by_edition_ord     ON chunks(edition_id, ord);
        CREATE INDEX chunks_by_translation_ord ON chunks(translation_id, ord);
        CREATE INDEX chunks_by_lang            ON chunks(lang);

        -- FTS triggers, rebuilt. content='chunks' / content_rowid='rowid'
        -- still align because chunks_fts was created with those refs and
        -- chunk rowids are preserved across the rebuild (INSERT order
        -- matches old rowids because we SELECTed in rowid order
        -- implicitly via PK).
        --
        -- NOTE: chunks_fts itself is untouched. The triggers below
        -- mirror writes from chunks → chunks_fts going forward.
        CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
        END;
        CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text)
                VALUES('delete', old.rowid, old.text);
        END;
        CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text)
                VALUES('delete', old.rowid, old.text);
            INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
        END;

        -- Rebuild the FTS index because the underlying chunks rowids
        -- may have shifted on table rebuild. Without this, BM25 search
        -- can return phantom rows.
        INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');

        -- ── 9. chunks_full view: legacy column shape via JOIN ──────
        -- Call sites that used to read `chunks.author`, `chunks.work`,
        -- etc. can switch their FROM clause from `chunks` to
        -- `chunks_full` and otherwise stay the same. `corpus` is the
        -- lowercased author name — the four-author corpus naming
        -- (plato/aristotle/hegel/kant) is conveniently the same as
        -- lowercase author.
        CREATE VIEW chunks_full AS
        SELECT
            c.chunk_id,
            c.lang,
            c.section,
            c.book,
            c.page,
            c.speaker,
            c.source_file,
            c.text,
            c.ord,
            c.edition_id,
            c.translation_id,
            w.id      AS work_id,
            w.author  AS author,
            w.title   AS work,
            LOWER(w.author) AS corpus,
            COALESCE(e.name, t.translator_name) AS translator,
            COALESCE(e.year, t.year)            AS edition_year,
            CASE WHEN c.edition_id IS NOT NULL THEN 1 ELSE 0 END AS is_original
        FROM chunks c
        LEFT JOIN editions     e ON e.id = c.edition_id
        LEFT JOIN translations t ON t.id = c.translation_id
        JOIN works w ON w.id = COALESCE(e.work_id, t.work_id);
    """)
