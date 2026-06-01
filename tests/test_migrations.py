"""Tests for the schema-migrations runner."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from minerva import migrations, store


def _open_fresh(tmp_path: Path) -> sqlite3.Connection:
    return store.open_db(tmp_path / "fresh.sqlite")


def test_open_db_applies_pending_migrations(tmp_path: Path):
    """A brand-new database should land at the latest migration version,
    not blank."""
    conn = _open_fresh(tmp_path)
    version = migrations.current_version(conn)
    assert version is not None and version >= 1


def test_open_db_creates_term_glossary_tables(tmp_path: Path):
    conn = _open_fresh(tmp_path)
    table_names = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    # Tables introduced by 0001
    for t in (
        "works",
        "editions",
        "translations",
        "terms",
        "term_relations",
        "term_renderings",
        "term_occurrences",
        "occurrence_renderings",
        "schema_migrations",
    ):
        assert t in table_names, f"missing table: {t}"


def test_apply_is_idempotent(tmp_path: Path):
    """Calling apply() a second time should be a no-op and return [].
    The runner's first responsibility — never replay a migration."""
    conn = _open_fresh(tmp_path)
    ran = migrations.apply(conn)
    assert ran == []  # nothing pending on a freshly-opened DB
    # And the migrations table still has exactly one entry per version.
    rows = conn.execute(
        "SELECT version, COUNT(*) FROM schema_migrations GROUP BY version"
    ).fetchall()
    for _v, n in rows:
        assert n == 1


def test_foreign_keys_pragma_is_on(tmp_path: Path):
    """`open_db` must enable PRAGMA foreign_keys so the new FKs and the
    legacy embeddings cascade actually fire."""
    conn = _open_fresh(tmp_path)
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1


def test_indexes_are_present(tmp_path: Path):
    """A handful of the named indexes from 0001/0004/0005 must exist —
    they're documented as load-bearing for Q1/Q2/Q3 and for the relink
    paths in the design notes."""
    conn = _open_fresh(tmp_path)
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    expected = {
        "term_occ_by_chunk",
        "term_occ_by_edition_term",
        "term_occ_by_shadow",
        "term_render_by_translation",
        "occ_render_by_translation",
        # 0004: partial UNIQUE for canonical editions.
        "editions_canonical_unique",
        # 0005: translation-side shadow address index.
        "occ_render_by_shadow",
    }
    missing = expected - indexes
    assert not missing, f"missing indexes: {missing}"


def test_editions_canonical_default_and_unique_constraint(tmp_path: Path):
    """0004: editions.is_canonical defaults to 1 and the partial
    UNIQUE index permits at most one canonical edition per
    (work_id, language)."""
    conn = _open_fresh(tmp_path)
    conn.executescript(
        "INSERT INTO works (id, author, title, original_language, citation_system) "
        "VALUES (1, 'Plato', 'Republic', 'grc', 'stephanus');"
        "INSERT INTO editions (id, work_id, name, language, year) "
        "VALUES (1, 1, 'Burnet OCT', 'grc', 1903);"
    )
    conn.commit()
    flag = conn.execute("SELECT is_canonical FROM editions WHERE id = 1").fetchone()[0]
    assert flag == 1
    # A second canonical edition for the same (work_id, language) must fail.
    with pytest.raises(sqlite3.IntegrityError):
        conn.executescript(
            "INSERT INTO editions (id, work_id, name, language, year, is_canonical) "
            "VALUES (2, 1, 'Slings OCT', 'grc', 2003, 1);"
        )
    # But a non-canonical one is fine.
    conn.executescript(
        "INSERT INTO editions (id, work_id, name, language, year, is_canonical) "
        "VALUES (3, 1, 'Slings OCT', 'grc', 2003, 0);"
    )
    conn.commit()


def test_heb_ara_langs_accepted(tmp_path: Path):
    """0016 widened the language-code CHECKs on works/editions/translations/
    terms. Verify each table accepts ``heb`` and ``ara`` without an
    IntegrityError, and that an unknown lang ``xyz`` still rejects."""

    conn = _open_fresh(tmp_path)
    conn.executescript(
        """
        INSERT INTO works (id, author, title, original_language, citation_system)
        VALUES
          (101, 'Hebrew Bible', 'Genesis', 'heb', 'bcv'),
          (102, 'Quran', 'Al-Fatiha', 'ara', 'surah_ayah');

        INSERT INTO editions (id, work_id, name, language, year)
        VALUES
          (101, 101, 'WLC', 'heb', 2018),
          (102, 102, 'Tanzil Uthmani', 'ara', 2010);

        INSERT INTO translations (id, work_id, translator_name, year, language)
        VALUES
          (101, 102, 'Pickthall', 1930, 'eng');

        INSERT INTO terms (id, source_form, source_language, short_gloss, long_description)
        VALUES
          (101, 'דָּבָר', 'heb', 'word, thing, matter', 'Hebrew dabar.'),
          (102, 'كتاب', 'ara', 'book, writing', 'Arabic kitab.');
        """
    )
    conn.commit()
    # Unknown lang still rejects.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO terms (source_form, source_language, "
            "short_gloss, long_description) "
            "VALUES ('foo', 'xyz', 'g', 'd')"
        )


def test_surah_ayah_citation_accepted(tmp_path: Path):
    """0017 widened ``works.citation_system`` to admit ``surah_ayah``.
    Verify the value lands and ``unknown_system`` still rejects."""

    conn = _open_fresh(tmp_path)
    conn.executescript(
        "INSERT INTO works (id, author, title, original_language, citation_system) "
        "VALUES (201, 'Quran', 'Al-Baqarah', 'ara', 'surah_ayah');"
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO works (id, author, title, original_language, citation_system) "
            "VALUES (202, 'Bogus', 'X', 'ara', 'unknown_system')"
        )


def test_occurrence_renderings_shadow_columns_exist(tmp_path: Path):
    """0005 added the translation-side shadow columns. Their presence
    is the contract that `terms.insert_occurrence_rendering` writes
    against — assert it directly so a future ALTER doesn't drift them
    silently."""
    conn = _open_fresh(tmp_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(occurrence_renderings)")}
    assert {"source_locator_sort_key", "rendered_form_snapshot", "instance_index"} <= cols


def test_term_occurrences_shadow_address_is_unique(tmp_path: Path):
    """The shadow-address UNIQUE constraint is the runtime safety net
    that lets insert_occurrence's retry loop terminate. Confirm it's
    on the right tuple."""
    conn = _open_fresh(tmp_path)
    _seed_fixture(conn)
    # First insert: instance_index = 1.
    conn.execute(
        "INSERT INTO term_occurrences ("
        "  term_id, edition_id, work_id, source_chunk_id, source_start, source_end, "
        "  context_snippet, location_kind, location_payload, "
        "  location_sort_key, source_form_snapshot, instance_index"
        ") VALUES (1, 1, 1, 'chk-1', 0, 6, '…λόγος…', "
        '\'stephanus\', \'{"kind":"stephanus","page":327,"section":"a"}\', '
        "'P0327a', 'λόγος', 1)"
    )
    # Same shadow → second insert at instance_index=1 must fail.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO term_occurrences ("
            "  term_id, edition_id, work_id, source_chunk_id, source_start, source_end, "
            "  context_snippet, location_kind, location_payload, "
            "  location_sort_key, source_form_snapshot, instance_index"
            ") VALUES (1, 1, 1, 'chk-1', 10, 16, '…λόγος…', "
            '\'stephanus\', \'{"kind":"stephanus","page":327,"section":"a"}\', '
            "'P0327a', 'λόγος', 1)"
        )
    # But instance_index=2 with the same shadow prefix is fine.
    conn.execute(
        "INSERT INTO term_occurrences ("
        "  term_id, edition_id, work_id, source_chunk_id, source_start, source_end, "
        "  context_snippet, location_kind, location_payload, "
        "  location_sort_key, source_form_snapshot, instance_index"
        ") VALUES (1, 1, 1, 'chk-1', 10, 16, '…λόγος…', "
        '\'stephanus\', \'{"kind":"stephanus","page":327,"section":"a"}\', '
        "'P0327a', 'λόγος', 2)"
    )
    conn.commit()


def _seed_fixture(conn: sqlite3.Connection) -> None:
    """Minimal works/editions/terms/chunks seed for occurrence inserts.
    Lives here (rather than conftest) because it's only used by the
    migrations and terms test modules. Inserts work/edition rows first,
    then chunks with edition_id set — order matters because the FK
    cascade ON DELETE depends on the parent row existing."""
    conn.executescript(
        """
        INSERT INTO works(id, author, title, original_language, citation_system)
        VALUES (1, 'Plato', 'Republic', 'grc', 'stephanus');

        INSERT INTO editions(id, work_id, name, language, year, notes)
        VALUES (1, 1, 'Burnet OCT', 'grc', 1903, NULL);

        INSERT INTO chunks(chunk_id, edition_id, translation_id, lang,
                           source_file, text, ord)
        VALUES ('chk-1', 1, NULL, 'grc', 'r.xml', 'λόγος ...', 0);

        INSERT INTO terms(id, source_form, source_language,
                          short_gloss, long_description)
        VALUES (1, 'λόγος', 'grc',
                'reason, account, ratio, word',
                'See LSJ; central in Plato and Heraclitus.');
        """
    )
    conn.commit()
