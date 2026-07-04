"""Unit tests for scoped cross_reference rebind."""

from __future__ import annotations

from pathlib import Path

from minerva import store
from minerva.sqlite_util import foreign_keys_disabled
from minerva.store.chunks import _rebind_cross_references


def _seed_xrefs(conn) -> None:
    conn.executescript(
        """
        INSERT INTO works (id, author, title, original_language, citation_system)
        VALUES (1, 'Plato', 'Republic', 'grc', 'stephanus'),
               (2, 'Hegel', 'PhdG', 'deu', 'paragraph');

        INSERT INTO editions (id, work_id, name, language, year, is_canonical)
        VALUES (1, 1, 'OCT', 'grc', 1900, 1),
               (2, 2, 'Meiner', 'deu', 1907, 1);

        INSERT INTO chunks (chunk_id, edition_id, lang, section, source_file, text, ord)
        VALUES ('plato-1', 1, 'grc', '509d', 'r.xml', 'plato text', 0);

        INSERT INTO reference_targets (canonical_author, canonical_work)
        VALUES ('Hegel', 'PhdG');

        INSERT INTO cross_references (
          source_chunk_id, target_id, reference_type, source_edition_id,
          source_sort_key, source_form_snapshot, source_instance_index
        ) VALUES
          ('plato-1', (SELECT id FROM reference_targets WHERE canonical_work = 'PhdG'), 'cites', 1, 'S002', 'alpha', 1);
        """
    )
    conn.commit()
    with foreign_keys_disabled(conn):
        conn.execute(
            "INSERT INTO cross_references ("
            "  source_chunk_id, target_id, reference_type, source_edition_id, "
            "  source_sort_key, source_form_snapshot, source_instance_index"
            ") VALUES ("
            "  'hegel-1', (SELECT id FROM reference_targets WHERE canonical_work = 'PhdG'), "
            "  'cites', 2, 'S001', 'beta', 1"
            ")"
        )
        conn.commit()


def test_rebind_scoped_orphan_sweep_keeps_out_of_scope_dangling(tmp_path: Path):
    conn = store.open_db(tmp_path / "rebind.sqlite")
    _seed_xrefs(conn)

    _rebind_cross_references(
        conn,
        count_before=1,
        affected_chunk_ids=frozenset({"plato-1"}),
    )

    rows = conn.execute(
        "SELECT source_chunk_id FROM cross_references ORDER BY source_chunk_id"
    ).fetchall()
    assert [r[0] for r in rows] == ["hegel-1", "plato-1"]


def test_rebind_large_affected_set_does_not_overflow_variables(tmp_path: Path):
    """An affected set larger than SQLite's SQLITE_MAX_VARIABLE_NUMBER
    (32,766 on 3.32+) must not raise 'too many SQL variables' — the
    rebind scopes via a temp-table join, not an IN (?, …) list (#49)."""

    conn = store.open_db(tmp_path / "rebind_big.sqlite")
    _seed_xrefs(conn)

    # Real chunk + 40k synthetic ids that don't exist in `chunks`.
    affected = frozenset({"plato-1", *(f"synthetic-{i}" for i in range(40_000))})

    # Must complete without OperationalError.
    _rebind_cross_references(conn, count_before=1, affected_chunk_ids=affected)

    rows = conn.execute(
        "SELECT source_chunk_id FROM cross_references ORDER BY source_chunk_id"
    ).fetchall()
    # plato-1 rebound and kept; out-of-scope hegel-1 untouched.
    assert [r[0] for r in rows] == ["hegel-1", "plato-1"]
    # The temp table was dropped (no leak for the next statement).
    leaked = conn.execute(
        "SELECT name FROM sqlite_temp_master WHERE name = '_affected_chunk_ids'"
    ).fetchall()
    assert leaked == []
