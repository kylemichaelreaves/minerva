"""Materializing `authors/work_aliases.py` into the DB (#195).

The declaration is keyed on ``(author, works.title)`` — a natural key —
because ``works.id`` is a surrogate reassigned by insertion order and
reshuffled by ``index --reset`` (#193). This is the step that resolves it
to ids, and it has to re-run after every index for that reason.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from conftest import make_chunk

from minerva import store
from minerva.authors import work_aliases
from minerva.cli.index_cmd import cmd_index
from minerva.store.work_alias_sync import sync_work_aliases


@pytest.fixture
def db(tmp_path: Path) -> Path:
    """A tiny index carrying one aliased work and one unaliased one."""

    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(
                    chunk_id="k1",
                    corpus="marx",
                    author="Marx",
                    work="Das Kapital, Band I",
                    lang="deu",
                    text="Der Reichtum der Gesellschaften.",
                ),
                make_chunk(
                    chunk_id="m1",
                    corpus="marx",
                    author="Marx",
                    work="Thesen über Feuerbach",
                    lang="deu",
                    text="Die Philosophen haben die Welt nur verschieden interpretiert.",
                ),
            ]
        )
    )
    path = tmp_path / "aliases.sqlite"
    assert cmd_index(argparse.Namespace(db=path, input=jsonl, reset=False)) == 0
    return path


def test_index_materializes_aliases(db: Path):
    conn = store.open_db(db)
    rows = conn.execute(
        "SELECT w.title, a.alias FROM work_aliases a JOIN works w ON w.id = a.work_id"
    ).fetchall()
    assert [tuple(r) for r in rows] == [("Das Kapital, Band I", "Das Kapital")]


def test_alias_follows_the_work_across_an_id_reshuffle(db: Path, tmp_path: Path):
    """The point of keying on (author, title). Re-index with an unrelated
    work inserted first so `works.id` values move, and the alias must
    still land on the Kapital rather than on whatever now holds its old
    id — the #193 failure mode, in the table that would be most likely to
    reproduce it."""

    conn = store.open_db(db)
    before = conn.execute("SELECT work_id FROM work_aliases").fetchone()[0]
    conn.close()

    jsonl2 = tmp_path / "seed2.jsonl"
    jsonl2.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(
                    chunk_id="decoy",
                    corpus="plato",
                    author="Plato",
                    work="Politeia",
                    lang="grc",
                    text="κατέβην χθὲς εἰς Πειραιᾶ.",
                ),
                make_chunk(
                    chunk_id="k1",
                    corpus="marx",
                    author="Marx",
                    work="Das Kapital, Band I",
                    lang="deu",
                    text="Der Reichtum der Gesellschaften.",
                ),
            ]
        )
    )
    assert cmd_index(argparse.Namespace(db=db, input=jsonl2, reset=True)) == 0

    conn = store.open_db(db)
    row = conn.execute(
        "SELECT w.title, w.id, a.alias FROM work_aliases a JOIN works w ON w.id = a.work_id"
    ).fetchone()
    assert row["title"] == "Das Kapital, Band I"
    assert row["alias"] == "Das Kapital"
    assert row["id"] != before, "id reshuffle not reproduced — test proves nothing"


def test_sync_is_a_full_replace_not_an_upsert(db: Path, monkeypatch):
    """The table is derived, so an alias deleted from the code table has
    to disappear from the DB. An upsert would leave it behind forever."""

    conn = store.open_db(db)
    assert conn.execute("SELECT COUNT(*) FROM work_aliases").fetchone()[0] == 1
    monkeypatch.setattr(work_aliases, "ALIASES", {})
    monkeypatch.setattr("minerva.store.work_alias_sync.ALIASES", {})
    assert sync_work_aliases(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM work_aliases").fetchone()[0] == 0


def test_unresolved_entries_are_reported_not_fatal(db: Path, capsys):
    """Most of the alias table names works that a partial index does not
    contain — that is normal. But a title changing underneath an alias
    silently undoes the fix, so it gets a line."""

    conn = store.open_db(db)
    capsys.readouterr()
    written = sync_work_aliases(conn)
    err = capsys.readouterr().err
    assert written == 1
    assert "name a work not in this index" in err


def test_every_alias_entry_is_distinct_from_the_title_it_aliases():
    """An alias equal to the canonical title is dead weight — the title
    is already matched — and usually signals a copy-paste slip."""

    for (author, title), names in work_aliases.ALIASES.items():
        assert title not in names, f"{author} — {title!r} aliases itself"
        assert len(set(names)) == len(names), f"{author} — {title!r} has a duplicate alias"
