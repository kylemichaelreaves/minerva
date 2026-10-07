"""One resolver for a target's in-corpus work (#523, #800).

`ensure_target` linked exact-then-folded since #524, but the index-time
rebind re-resolved by exact title only, so every index run re-NULLed the
fold-linked targets — Cicero 2–5, #551's repair, were NULL again when
#800 was measured. And neither consulted the alias table. Now
`ensure_target`, `_rebind_reference_targets` and its integrity assert all
call `refs.schema.resolve_target_work`: exact → folded → 1:1 alias.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index
from minerva.refs import schema as refs_schema
from minerva.store import chunks as store_chunks


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    jsonl = tmp_path / "seed.jsonl"
    rows = [
        make_chunk(chunk_id="rp", corpus="cicero", author="Cicero", work="De Re Publica"),
        make_chunk(
            chunk_id="sl", corpus="hegel", author="Hegel", work="Science of Logic", text="Being."
        ),
        *(
            make_chunk(
                chunk_id=f"k{n}",
                corpus="marx",
                author="Marx",
                work=f"Das Kapital, Band {n}",
                lang="deu",
                text=f"Ware {n}.",
            )
            for n in ("I", "II", "III")
        ),
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows))
    db = tmp_path / "t.sqlite"
    assert cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False)) == 0
    c = store.open_db(db)
    yield c
    c.close()


def _work_id(conn: sqlite3.Connection, author: str, title: str) -> int:
    return conn.execute(
        "SELECT id FROM works WHERE author = ? AND title = ?", (author, title)
    ).fetchone()[0]


def _resolved(conn: sqlite3.Connection, author: str, work: str) -> int | None:
    hit = refs_schema.resolve_target_work(conn, author=author, work=work)
    return None if hit is None else hit[0]


class TestResolveTargetWork:
    def test_exact(self, conn) -> None:
        assert _resolved(conn, "Cicero", "De Re Publica") == _work_id(
            conn, "Cicero", "De Re Publica"
        )

    def test_folded(self, conn) -> None:
        assert _resolved(conn, "Cicero", "De republica") == _work_id(
            conn, "Cicero", "De Re Publica"
        )

    def test_a_one_to_one_alias(self, conn) -> None:
        # ALIASES: ("Hegel", "Science of Logic") answers to "Wissenschaft der
        # Logik"; with no German work in the corpus, the alias is the link.
        assert _resolved(conn, "Hegel", "Wissenschaft der Logik") == _work_id(
            conn, "Hegel", "Science of Logic"
        )

    def test_an_ambiguous_alias_declines(self, conn) -> None:
        # All three Bände answer to "Das Kapital": picking one would read
        # as resolved and be wrong two times in three.
        assert _resolved(conn, "Marx", "Das Kapital") is None

    def test_an_alias_never_crosses_authors(self, conn) -> None:
        assert _resolved(conn, "Kant", "Wissenschaft der Logik") is None

    def test_the_wildcard_never_resolves(self, conn) -> None:
        assert _resolved(conn, "Cicero", "*") is None


class TestEnsureTargetUsesIt:
    def test_ensure_target_links_through_an_alias(self, conn) -> None:
        t = refs_schema.ensure_target(
            conn, canonical_author="Hegel", canonical_work="Wissenschaft der Logik"
        )
        assert t.in_corpus_work_id == _work_id(conn, "Hegel", "Science of Logic")


class TestRebindKeepsWhatEnsureTargetLinked:
    @pytest.mark.parametrize(
        ("author", "work", "linked_title"),
        [
            ("Cicero", "De republica", "De Re Publica"),  # #800: folded
            ("Hegel", "Wissenschaft der Logik", "Science of Logic"),  # #523: alias
        ],
    )
    def test_a_non_exact_link_survives_the_rebind(self, conn, author, work, linked_title) -> None:
        refs_schema.ensure_target(conn, canonical_author=author, canonical_work=work)
        conn.commit()
        assert store_chunks._rebind_reference_targets(conn) == 0
        got = conn.execute(
            "SELECT in_corpus_work_id FROM reference_targets "
            "WHERE canonical_author = ? AND canonical_work = ?",
            (author, work),
        ).fetchone()[0]
        assert got == _work_id(conn, author, linked_title)
        store_chunks._assert_reference_targets_resolve(conn)

    def test_the_rebind_relinks_a_nulled_fold_target(self, conn) -> None:
        # The live state #800 measured: a fold-linkable target left NULL.
        refs_schema.ensure_target(conn, canonical_author="Cicero", canonical_work="De republica")
        conn.execute("UPDATE reference_targets SET in_corpus_work_id = NULL")
        assert store_chunks._rebind_reference_targets(conn) == 1

    def test_the_assert_still_catches_a_wrong_work(self, conn) -> None:
        refs_schema.ensure_target(conn, canonical_author="Cicero", canonical_work="De republica")
        conn.execute(
            "UPDATE reference_targets SET in_corpus_work_id = ?",
            (_work_id(conn, "Hegel", "Science of Logic"),),
        )
        with pytest.raises(RuntimeError, match="pointing at the wrong work"):
            store_chunks._assert_reference_targets_resolve(conn)
