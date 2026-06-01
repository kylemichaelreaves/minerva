"""Tests for `minerva.translations` — schema, lookup, insert, UNIQUE."""

from __future__ import annotations

from pathlib import Path

from minerva import translations


def test_open_db_creates_schema(tmp_path: Path):
    conn = translations.open_db(tmp_path / "t.sqlite")
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "translations" in tables


def test_lookup_miss_returns_none(tmp_path: Path):
    conn = translations.open_db(tmp_path / "t.sqlite")
    assert translations.lookup(conn, source_text="x", target_lang="engg") is None


def test_insert_and_lookup_round_trip(tmp_path: Path):
    conn = translations.open_db(tmp_path / "t.sqlite")
    added = translations.insert(
        conn,
        source_text="Μῆνιν ἄειδε θεὰ",
        target_lang="engg",
        translated_text="Sing, goddess, the wrath",
        literal_text="Wrath sing, goddess",
        model="claude-sonnet-4-6",
        now=100.0,
    )
    assert added is True
    row = translations.lookup(conn, source_text="Μῆνιν ἄειδε θεὰ", target_lang="engg")
    assert row is not None
    assert row["translated_text"] == "Sing, goddess, the wrath"
    assert row["literal_text"] == "Wrath sing, goddess"
    assert row["model"] == "claude-sonnet-4-6"
    assert row["created_at"] == 100.0


def test_insert_overwrites_same_key(tmp_path: Path):
    """`INSERT OR REPLACE` so pre-migration rows (NULL literal_text)
    upgrade on next call. The second insert wins."""

    conn = translations.open_db(tmp_path / "t.sqlite")
    translations.insert(
        conn,
        source_text="a",
        target_lang="engg",
        translated_text="first",
        literal_text="first-literal",
        model="m1",
    )
    translations.insert(
        conn,
        source_text="a",
        target_lang="engg",
        translated_text="second",
        literal_text="second-literal",
        model="m2",
    )
    row = translations.lookup(conn, source_text="a", target_lang="engg")
    assert row is not None
    assert row["translated_text"] == "second"
    assert row["literal_text"] == "second-literal"
    assert row["model"] == "m2"


def test_different_target_lang_is_separate_row(tmp_path: Path):
    conn = translations.open_db(tmp_path / "t.sqlite")
    translations.insert(
        conn,
        source_text="a",
        target_lang="engg",
        translated_text="english",
        literal_text="english-literal",
        model="m",
    )
    translations.insert(
        conn,
        source_text="a",
        target_lang="fraa",
        translated_text="french",
        literal_text="french-literal",
        model="m",
    )
    en = translations.lookup(conn, source_text="a", target_lang="engg")
    fr = translations.lookup(conn, source_text="a", target_lang="fraa")
    assert en is not None and en["translated_text"] == "english"
    assert fr is not None and fr["translated_text"] == "french"


def test_lookup_treats_null_literal_as_miss(tmp_path: Path):
    """Pre-dual-translation rows have NULL `literal_text`. `lookup`
    treats those as a partial miss so the handler re-fetches and
    upgrades the cache row."""

    conn = translations.open_db(tmp_path / "t.sqlite")
    import time

    # Raw INSERT bypassing the helper to simulate a pre-migration row.
    conn.execute(
        "INSERT INTO translations(source_text, target_lang, translated_text, model, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("legacy", "engg", "old translation", "m", time.time()),
    )
    conn.commit()
    assert translations.lookup(conn, source_text="legacy", target_lang="engg") is None


def test_count_and_delete_all(tmp_path: Path):
    conn = translations.open_db(tmp_path / "t.sqlite")
    translations.insert(
        conn,
        source_text="a",
        target_lang="engg",
        translated_text="x",
        literal_text="x-lit",
        model="m",
    )
    translations.insert(
        conn,
        source_text="b",
        target_lang="engg",
        translated_text="y",
        literal_text="y-lit",
        model="m",
    )
    assert translations.count(conn) == 2
    assert translations.delete_all(conn) == 2
    assert translations.count(conn) == 0


def test_supported_langs_set():
    # Locking in the v1 allow-list so accidental additions get caught by tests.
    assert "eng" in translations.SUPPORTED_LANGS
    assert "fra" in translations.SUPPORTED_LANGS
    assert "deu" in translations.SUPPORTED_LANGS
