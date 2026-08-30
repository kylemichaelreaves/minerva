"""Tests for ``store.stats`` and ``minerva db inspect``."""

from __future__ import annotations

import argparse
import json
from io import StringIO
from unittest.mock import patch

from minerva import store
from minerva.cli.db_cmd import cmd_db
from minerva.cli.stats_cmd import cmd_stats
from minerva.store.schema import get_meta
from minerva.store.stats import (
    _STATS_CACHE_KEY,
    _STATS_CACHE_TOTAL_KEY,
    _chunks_by_corpus_lang_cached,
)


class TestChunksByCorpusLangCache:
    """#344: `/api/health`'s `GROUP BY corpus, lang` full-scans `chunks`
    on every call (~210 ms live) because `corpus` is a computed column
    nothing indexes. Cached in `meta`, invalidated by comparing against
    a cheap `chunk_count()` rather than pinned to one writer."""

    def test_first_call_computes_and_writes_the_cache(self, populated_db):
        assert get_meta(populated_db, _STATS_CACHE_KEY) is None

        result = _chunks_by_corpus_lang_cached(populated_db)

        assert isinstance(result, list)
        assert len(result) >= 1
        assert get_meta(populated_db, _STATS_CACHE_KEY) is not None
        assert get_meta(populated_db, _STATS_CACHE_TOTAL_KEY) == "6"

    def test_second_call_reads_the_cache_without_rescanning(self, populated_db):
        first = _chunks_by_corpus_lang_cached(populated_db)

        # Poison the underlying data without going through the total-
        # count path: if the second call actually re-ran the GROUP BY
        # query it would see this row and disagree with `first`.
        populated_db.execute(
            "UPDATE chunks SET lang = 'zzz' WHERE chunk_id = "
            "(SELECT chunk_id FROM chunks LIMIT 1)"
        )
        populated_db.commit()

        second = _chunks_by_corpus_lang_cached(populated_db)
        assert second == first

    def test_a_changed_total_invalidates_the_cache(self, populated_db):
        first = _chunks_by_corpus_lang_cached(populated_db)
        before_total = get_meta(populated_db, _STATS_CACHE_TOTAL_KEY)

        populated_db.execute(
            "DELETE FROM chunks WHERE chunk_id = "
            "(SELECT chunk_id FROM chunks LIMIT 1)"
        )
        populated_db.commit()

        second = _chunks_by_corpus_lang_cached(populated_db)
        assert second != first
        assert get_meta(populated_db, _STATS_CACHE_TOTAL_KEY) != before_total
        assert get_meta(populated_db, _STATS_CACHE_TOTAL_KEY) == "5"

    def test_a_read_only_connection_still_answers_without_caching(
        self, populated_db
    ):
        populated_db.execute("PRAGMA query_only = ON")
        result = _chunks_by_corpus_lang_cached(populated_db)
        assert isinstance(result, list)
        assert len(result) >= 1


def test_store_stats_shape(populated_db):
    out = store.stats(populated_db)

    # 6 = the five original fixtures + the German syntax chunk (hegel-p17).
    assert out["chunks_total"] == 6
    assert out["embeddings_present"] is False
    assert isinstance(out["chunks_by_corpus_lang"], list)
    assert len(out["chunks_by_corpus_lang"]) >= 1
    assert "timing" in out


def test_store_tables_summary(populated_db):
    tables = store.tables_summary(populated_db)
    names = {row["name"] for row in tables}
    assert "chunks" in names
    assert all("rows" in row for row in tables)


def test_store_db_inspect(populated_db, db_path):
    info = store.db_inspect(populated_db, db_path)

    assert info["db_path"] == str(db_path)
    assert info["db_size_bytes"] > 0
    assert info["journal_mode"]
    assert "table" in info["schema_objects"]
    assert info["migrations_applied"] >= 1
    assert info["latest_migration"]


def test_cmd_stats_json(populated_db, db_path):
    args = argparse.Namespace(db=db_path, tables=False)
    buf = StringIO()

    with patch("sys.stdout", buf):
        rc = cmd_stats(args)

    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["chunks_total"] == 6


def test_cmd_db_inspect_json(populated_db, db_path):
    args = argparse.Namespace(db=db_path, action="inspect")
    buf = StringIO()

    with patch("sys.stdout", buf):
        rc = cmd_db(args)

    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["db_path"] == str(db_path)
    assert payload["latest_migration"]
