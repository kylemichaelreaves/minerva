"""Materializing `authors/named_passages.py` into the DB (#182).

Same reasoning as `test_work_alias_sync.py`: the declaration is keyed on
``(author, works.title)`` because ``works.id`` is a surrogate reassigned
by insertion order and reshuffled by ``index --reset`` (#193). This is
the step that resolves it to ids, and it has to re-run after every index
for that reason.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from conftest import make_chunk

from minerva import store
from minerva.authors import named_passages
from minerva.cli.index_cmd import cmd_index
from minerva.store.named_passage_sync import sync_named_passages


@pytest.fixture
def db(tmp_path: Path) -> Path:
    """A tiny index carrying one work with a named passage and one without."""

    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(
                    chunk_id="p1",
                    corpus="plato",
                    author="Plato",
                    work="Politeia",
                    lang="grc",
                    text="κατέβην χθὲς εἰς Πειραιᾶ.",
                ),
                make_chunk(
                    chunk_id="m1",
                    corpus="plato",
                    author="Plato",
                    work="Menon",
                    lang="grc",
                    text="ἆρα διδακτὸν ἡ ἀρετή;",
                ),
            ]
        )
    )
    path = tmp_path / "named_passages.sqlite"
    assert cmd_index(argparse.Namespace(db=path, input=jsonl, reset=False)) == 0
    return path


def test_index_materializes_named_passages(db: Path):
    conn = store.open_db(db)
    rows = conn.execute(
        "SELECT w.title, n.label, n.section_start, n.section_end "
        "FROM named_passages n JOIN works w ON w.id = n.work_id "
        "ORDER BY w.title"
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("Menon", "the slave boy", "82b", "85b"),
        ("Politeia", "the divided line", "509d", "511e"),
    ]


def test_label_follows_the_work_across_an_id_reshuffle(db: Path, tmp_path: Path):
    """The point of keying on (author, title) — same #193 failure mode
    `work_aliases` guards against, in the table most likely to reproduce
    it if the keying regressed to a surrogate id."""

    conn = store.open_db(db)
    before = conn.execute(
        "SELECT work_id FROM named_passages WHERE label = 'the divided line'"
    ).fetchone()[0]
    conn.close()

    jsonl2 = tmp_path / "seed2.jsonl"
    jsonl2.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(
                    chunk_id="decoy",
                    corpus="kant",
                    author="Kant",
                    work="Kritik der reinen Vernunft",
                    lang="deu",
                    text="Ich denke, das muss alle meine Vorstellungen begleiten können.",
                ),
                make_chunk(
                    chunk_id="p1",
                    corpus="plato",
                    author="Plato",
                    work="Politeia",
                    lang="grc",
                    text="κατέβην χθὲς εἰς Πειραιᾶ.",
                ),
            ]
        )
    )
    assert cmd_index(argparse.Namespace(db=db, input=jsonl2, reset=True)) == 0

    conn = store.open_db(db)
    row = conn.execute(
        "SELECT w.title, w.id, n.label FROM named_passages n JOIN works w ON w.id = n.work_id "
        "WHERE n.label = 'the divided line'"
    ).fetchone()
    assert row["title"] == "Politeia"
    assert row["label"] == "the divided line"
    assert row["id"] != before, "id reshuffle not reproduced — test proves nothing"


def test_sync_is_a_full_replace_not_an_upsert(db: Path, monkeypatch):
    """The table is derived, so a label removed from the code table has
    to disappear from the DB. An upsert would leave it behind forever."""

    conn = store.open_db(db)
    assert conn.execute("SELECT COUNT(*) FROM named_passages").fetchone()[0] == 2
    monkeypatch.setattr(named_passages, "NAMED_PASSAGES", {})
    monkeypatch.setattr("minerva.store.named_passage_sync.NAMED_PASSAGES", {})
    assert sync_named_passages(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM named_passages").fetchone()[0] == 0


def test_unresolved_entries_are_reported_not_fatal(db: Path, capsys):
    """Most of the table names works a partial index does not contain —
    that is normal. But a title changing underneath a label silently
    undoes the fix, so it gets a line."""

    conn = store.open_db(db)
    capsys.readouterr()
    written = sync_named_passages(conn)
    err = capsys.readouterr().err
    assert written == 2
    assert "name a work not in this index" in err


def test_every_label_is_distinct_within_its_work():
    for (author, title), passages in named_passages.NAMED_PASSAGES.items():
        labels = [p.label for p in passages]
        assert len(set(labels)) == len(labels), f"{author} — {title!r} has a duplicate label"
