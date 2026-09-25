"""The KWIC aggregate pass under a filter (#666).

A filtered request needs the filtered total alongside the unfiltered
breakdowns. It used to get it from a `SUM(CASE WHEN <filter> …)` inside the
grouped pass, which evaluated the filter once per lemma row: 671,411 times for
`der`/deu, +14–40 ms over the unfiltered pass. Every filter column is in the
group key, so the same predicate now runs once per group, still in SQL.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

import pytest
from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index
from minerva.concordance import kwic_queries
from minerva.concordance import queries as concordance_queries

# (pos, surface, feats) per token. Each chunk carries all of them, so every
# group is `_CHUNKS` rows deep. Includes the NULL and empty cases a filter
# has to reject without raising.
_TOKENS = [
    ("DET", "der", "Case=Nom|Gender=Masc|Number=Sing"),
    ("DET", "Der", "Case=Nom|Gender=Masc|Number=Sing"),
    ("PRON", "der", "Case=Gen|Number=Plur"),
    ("PRON", "dessen", "Case=Gen|Number=Sing"),
    (None, "der", None),
    ("DET", "der", ""),
]
_CHUNKS = 20


@pytest.fixture
def conn(tmp_path: Path):
    chunks = [
        make_chunk(chunk_id=f"c{i}", work="Logik", author="Hegel", lang="deu",
                   section=str(i), text="der " * len(_TOKENS))
        for i in range(_CHUNKS)
    ]
    db = tmp_path / "agg.sqlite"
    jsonl = tmp_path / "agg.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    assert cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False)) == 0
    c = store.open_db(db)
    c.executemany(
        "INSERT INTO chunk_lemmas (chunk_id, token_index, surface_form, surface_start, "
        " surface_end, lemma, lemma_fold, pos, feats) VALUES (?, ?, ?, ?, ?, 'der', 'der', ?, ?)",
        [
            (f"c{i}", t, surface, t * 4, t * 4 + 3, pos, feats)
            for i in range(_CHUNKS)
            for t, (pos, surface, feats) in enumerate(_TOKENS)
        ],
    )
    c.commit()
    yield c
    c.close()


def _like(pattern: str, value: str | None, _escape: str | None = None) -> bool | None:
    """SQLite's LIKE for the patterns this test sends: `%` wildcards around a
    literal with no `_` or escape in it, ASCII-case-insensitive."""

    if value is None:
        return None
    rx = ".*".join(re.escape(part) for part in pattern.split("%"))
    return re.fullmatch(rx, value, flags=re.IGNORECASE | re.DOTALL) is not None


def test_the_morph_filter_is_evaluated_once_per_group_not_per_row(
    conn: sqlite3.Connection,
) -> None:
    """Counted rather than timed: `LIKE` is overridden with a counting copy,
    and each call is charged to the statement running when it fires. The
    aggregate pass, the request's first statement, calls it once per group."""

    groups = conn.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT pos, surface_form, feats, work_id "
        "FROM chunk_lemmas)"
    ).fetchone()[0]
    rows = conn.execute("SELECT COUNT(*) FROM chunk_lemmas").fetchone()[0]
    assert groups < rows  # or the test cannot tell the two apart

    calls: list[int] = []

    def on_statement(_sql: str) -> None:
        calls.append(0)

    def counting_like(*args: str) -> bool | None:
        calls[-1] += 1
        return _like(*args)

    conn.create_function("like", 2, counting_like)
    conn.create_function("like", 3, counting_like)
    conn.set_trace_callback(on_statement)
    try:
        out = concordance_queries.lemma_detail(
            conn, {"lemma": "der", "lang": "deu", "morph": "Case=Gen"}
        )
    finally:
        conn.set_trace_callback(None)
    assert out["total"] == 2 * _CHUNKS
    assert calls[0] == groups, calls


@pytest.mark.parametrize(
    ("filters", "where"),
    [
        ({}, "1=1"),
        ({"pos": "PRON"}, "pos = 'PRON'"),
        ({"surface": "Der"}, "surface_form = 'Der'"),
        ({"morph": "Case=Gen"}, "feats LIKE '%Case=Gen%'"),
        ({"morph": "Case=Nom,Number=Sing"},
         "feats LIKE '%Case=Nom%' AND feats LIKE '%Number=Sing%'"),
        ({"pos": "DET", "surface": "der"}, "pos = 'DET' AND surface_form = 'der'"),
        ({"morph": "Case=Voc"}, "feats LIKE '%Case=Voc%'"),
        # LIKE is ASCII-case-insensitive, and that stays SQLite's to decide.
        ({"morph": "Case=gen"}, "feats LIKE '%Case=gen%'"),
    ],
)
def test_the_filtered_total_matches_a_count_of_the_rows(
    conn: sqlite3.Connection, filters: dict[str, str], where: str
) -> None:
    want = conn.execute(f"SELECT COUNT(*) FROM chunk_lemmas WHERE {where}").fetchone()[0]
    out = concordance_queries.lemma_detail(conn, {"lemma": "der", "lang": "deu", **filters})
    assert out["total"] == want
    assert len(out["rows"]) == min(want, 50)


def test_the_breakdowns_parse_each_feats_string_once(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#666: `der` has 16,075 groups and 143 distinct `feats` strings, and the
    fold parsed one per group. The breakdowns themselves are unchanged."""

    parsed: list[str | None] = []
    real = kwic_queries._parse_morph_feats

    def spy(feats: str | None) -> dict[str, str]:
        parsed.append(feats)
        return real(feats)

    monkeypatch.setattr(kwic_queries, "_parse_morph_feats", spy)
    _, _, groups = kwic_queries._lemma_aggregates(
        conn, "der", "deu", "", [], "cl.lemma_fold = LOWER(?)", "", []
    )
    parsed.clear()
    out = kwic_queries._fold_breakdowns(groups)
    distinct = {g["feats"] for g in groups if g["feats"]}
    assert len(groups) > len(distinct)
    assert sorted(parsed) == sorted(distinct)
    assert {b["value"]: b["count"] for b in out["case_breakdown"]} == {
        "Nom": 2 * _CHUNKS, "Gen": 2 * _CHUNKS
    }
    assert {b["value"]: b["count"] for b in out["number_breakdown"]} == {
        "Sing": 3 * _CHUNKS, "Plur": _CHUNKS
    }
    assert {b["value"]: b["count"] for b in out["gender_breakdown"]} == {"Masc": 2 * _CHUNKS}
