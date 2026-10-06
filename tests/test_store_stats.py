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
    CHUNKS_BY_CORPUS_LANG_SQL,
    _chunks_by_corpus_lang_cached,
)

# The query CHUNKS_BY_CORPUS_LANG_SQL replaced (#641). Kept verbatim as the
# equivalence reference — the rewrite is only correct if it still answers
# exactly what the view-based grouping did.
_VIEW_BASED_CORPUS_LANG = (
    "SELECT corpus, lang, COUNT(*) FROM chunks_full GROUP BY corpus, lang ORDER BY 1, 2"
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
            "UPDATE chunks SET lang = 'zzz' WHERE chunk_id = (SELECT chunk_id FROM chunks LIMIT 1)"
        )
        populated_db.commit()

        second = _chunks_by_corpus_lang_cached(populated_db)
        assert second == first

    def test_a_changed_total_invalidates_the_cache(self, populated_db):
        first = _chunks_by_corpus_lang_cached(populated_db)
        before_total = get_meta(populated_db, _STATS_CACHE_TOTAL_KEY)

        populated_db.execute(
            "DELETE FROM chunks WHERE chunk_id = (SELECT chunk_id FROM chunks LIMIT 1)"
        )
        populated_db.commit()

        second = _chunks_by_corpus_lang_cached(populated_db)
        assert second != first
        assert get_meta(populated_db, _STATS_CACHE_TOTAL_KEY) != before_total
        assert get_meta(populated_db, _STATS_CACHE_TOTAL_KEY) == "5"

    def test_a_read_only_connection_still_answers_without_caching(self, populated_db):
        populated_db.execute("PRAGMA query_only = ON")
        result = _chunks_by_corpus_lang_cached(populated_db)
        assert isinstance(result, list)
        assert len(result) >= 1


class TestChunksByCorpusLangQuery:
    """#641: the breakdown grouped through `chunks_full`, whose keys are all
    functionally determined by `work_id`. 212.3 ms against 12.7 ms on the live
    corpus, identical 76 rows."""

    def test_the_query_plan_avoids_the_view(self, populated_db):
        """Assert the PLAN, not a duration — #642's reasoning applies here too.

        A timing assertion needs the 428k-row corpus CI does not have, while
        the plan is the property that makes it fast and holds at any row
        count. `chunks_full` joins `works`, `editions` and `translations`, so
        grouping through it runs that join once per chunk to produce 76 rows.
        """
        plan = [
            row[-1]
            for row in populated_db.execute("EXPLAIN QUERY PLAN " + CHUNKS_BY_CORPUS_LANG_SQL)
        ]
        assert any("COVERING INDEX" in step for step in plan), plan
        assert not any("chunks_full" in step for step in plan), plan

    def test_it_matches_the_view_based_query_it_replaced(self, populated_db):
        """Equivalence on the fixture's mixed corpus.

        Passes before and after the rewrite by design — it is the invariant,
        not the change. It earns its place by catching drift: change how
        `corpus` is derived in `chunks_full` and this fails.
        """
        rewritten = [tuple(r) for r in populated_db.execute(CHUNKS_BY_CORPUS_LANG_SQL)]
        reference = [tuple(r) for r in populated_db.execute(_VIEW_BASED_CORPUS_LANG)]
        assert rewritten == reference
        assert len(rewritten) > 0

    def test_counts_are_summed_per_corpus_not_per_work(self, populated_db):
        """The outer GROUP BY is the one thing this query does not share with
        `WORK_COUNTS_SQL`, and dropping it is silently wrong rather than loud.

        An author owning two works in one language yields two inner rows that
        must sum to one output row. Without the outer aggregate the row count
        can stay the same while the values halve, which is why this asserts a
        total rather than a length.
        """
        populated_db.execute(
            "INSERT INTO works (id, author, title, original_language, citation_system) "
            "VALUES (9001, 'Hegel', 'Second Hegel Work', 'deu', 'paragraph')"
        )
        populated_db.execute(
            "INSERT INTO editions (id, work_id, name, language) "
            "VALUES (9001, 9001, 'Test Edition', 'deu')"
        )
        populated_db.execute(
            "INSERT INTO chunks (chunk_id, edition_id, lang, source_file, text, ord, work_id) "
            "VALUES ('hegel-second-1', 9001, 'deu', 'test.xml', 'Zweites Werk.', 1, 9001)"
        )

        rows = {(r[0], r[1]): r[2] for r in populated_db.execute(CHUNKS_BY_CORPUS_LANG_SQL)}
        reference = {(r[0], r[1]): r[2] for r in populated_db.execute(_VIEW_BASED_CORPUS_LANG)}
        assert rows == reference
        # One row for (hegel, deu), carrying both works' chunks.
        assert rows[("hegel", "deu")] == reference[("hegel", "deu")]
        assert rows[("hegel", "deu")] >= 2


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
