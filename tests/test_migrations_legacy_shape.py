"""Apply the full migration chain to a legacy-shaped (pre-0003) DB.

Fresh DBs arrive in the post-0003 shape directly (store.SCHEMA), so
0003's table-rebuild path — the most invasive migration in the chain —
was previously exercised by NOTHING: every test opened a fresh DB and
0003 short-circuited at its idempotency guard. This test constructs
the legacy stringly-typed ``chunks`` shape that 0003 documents as its
input contract and runs the ordinary ``store.open_db`` upgrade path
over it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from minerva import migrations, store
from minerva.sqlite_util import table_exists

# The legacy shape as documented and consumed by 0003 (chunks with the
# five stringly-typed columns) plus the FTS5 shadow + triggers that
# 0003 drops and recreates, and the embeddings/meta peers store.SCHEMA
# declared before the runner existed.
_LEGACY_SCHEMA = """
CREATE TABLE chunks (
    chunk_id     TEXT PRIMARY KEY,
    corpus       TEXT NOT NULL,
    author       TEXT NOT NULL,
    work         TEXT NOT NULL,
    lang         TEXT NOT NULL,
    section      TEXT,
    book         TEXT,
    page         TEXT,
    speaker      TEXT,
    source_file  TEXT NOT NULL,
    text         TEXT NOT NULL,
    ord          INTEGER NOT NULL,
    translator   TEXT,
    edition_year TEXT
);
CREATE INDEX chunks_corpus ON chunks(corpus);
CREATE INDEX chunks_work_ord ON chunks(work, ord);

CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text, content='chunks', content_rowid='rowid'
);
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

CREATE TABLE embeddings (
    chunk_id  TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    model     TEXT NOT NULL,
    dim       INTEGER NOT NULL,
    vector    BLOB NOT NULL
);

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _build_legacy_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_LEGACY_SCHEMA)
    conn.executemany(
        "INSERT INTO chunks (chunk_id, corpus, author, work, lang, section, "
        "  source_file, text, ord, translator, edition_year) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            # Greek original (legacy 2-letter lang for 0002 to convert).
            ("g1", "plato", "Plato", "Republic", "gr", "509d",
             "rep.xml", "ἀγαθόν original", 0, "(Original)", None),
            # English translation of the same work.
            ("e1", "plato", "Plato", "Republic", "en", "509d",
             "rep_en.xml", "the good translated", 1, "Jowett", "1892"),
        ],
    )
    conn.commit()
    conn.close()


def test_legacy_db_converges_through_full_migration_chain(tmp_path: Path):
    db = tmp_path / "legacy.sqlite"
    _build_legacy_db(db)

    # The ordinary upgrade path: open_db applies SCHEMA (IF NOT EXISTS
    # no-ops against the legacy tables) then the full migration chain.
    conn = store.open_db(db)

    # Landed at the current head.
    head = migrations.current_version(conn)
    assert head is not None and head >= 22

    # 0003 rebuilt chunks without the stringly-typed columns...
    cols = {row[1] for row in conn.execute("PRAGMA table_info(chunks)")}
    assert "work" not in cols and "corpus" not in cols
    assert {"edition_id", "translation_id"} <= cols

    # ...and split the rows into one Work + one Edition + one Translation.
    works = conn.execute(
        "SELECT author, title, original_language FROM works"
    ).fetchall()
    assert [tuple(w) for w in works] == [("Plato", "Republic", "grc")]
    assert conn.execute("SELECT COUNT(*) FROM editions").fetchone()[0] == 1
    tr = conn.execute(
        "SELECT translator_name, language FROM translations"
    ).fetchone()
    assert (tr[0], tr[1]) == ("Jowett", "eng")

    # Chunk rows survived with correct FK classification and 0002's
    # lang conversion applied.
    rows = conn.execute(
        "SELECT chunk_id, lang, edition_id IS NOT NULL, "
        "       translation_id IS NOT NULL "
        "FROM chunks ORDER BY chunk_id"
    ).fetchall()
    assert [tuple(r) for r in rows] == [("e1", "eng", 0, 1), ("g1", "grc", 1, 0)]

    # The chunks_full view recomposes the legacy column shape.
    full = conn.execute(
        "SELECT chunk_id, corpus, author, work FROM chunks_full ORDER BY chunk_id"
    ).fetchall()
    assert [tuple(r) for r in full] == [
        ("e1", "plato", "Plato", "Republic"),
        ("g1", "plato", "Plato", "Republic"),
    ]

    # FTS survived the trigger rebuild AND the normalized shadow (0021)
    # got backfilled for the legacy rows.
    hit = conn.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'translated'"
    ).fetchall()
    assert len(hit) == 1
    assert table_exists(conn, "cross_references")  # 0012/0013 applied
    norm = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE text_norm IS NOT NULL"
    ).fetchone()[0]
    assert norm == 2

    # Whole-DB FK integrity after the rebuild dance.
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    # Idempotent: a second open applies nothing.
    conn.close()
    conn2 = store.open_db(db)
    assert migrations.apply(conn2) == []
