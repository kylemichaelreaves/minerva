"""`terms list --like` / `terms works --like` must not leak SQL wildcards.

Both build a ``LIKE`` pattern from a user-supplied string. Neither had
an ``ESCAPE`` clause or escaped the value, so ``--like '%'`` matched
every row instead of none — the CLI half of #120, alongside the
``/api/concordance/index?letter=%`` bypass on the HTTP side.

These drive the argparse handlers directly against a real SQLite store
and read the JSON they emit, so the assertions cover the actual query
the command runs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from minerva import store
from minerva.cli.terms.crud import cmd_terms_list
from minerva.cli.terms.linking import cmd_terms_works


@pytest.fixture
def terms_db(tmp_path: Path) -> Path:
    """A store with terms and works whose text contains no literal
    ``%`` or ``_``, so a correctly escaped filter matches nothing."""

    db_path = tmp_path / "terms.sqlite"
    conn = store.open_db(db_path)
    conn.executemany(
        "INSERT INTO terms (source_form, source_language, short_gloss, "
        "long_description) VALUES (?, ?, ?, ?)",
        [
            ("Geist", "deu", "spirit", "Hegel's central term."),
            ("Aufhebung", "deu", "sublation", "Simultaneously cancels and preserves."),
            ("λόγος", "grc", "reason", "Word, account, ratio."),
        ],
    )
    conn.executemany(
        "INSERT INTO works (author, title, original_language, citation_system) VALUES (?, ?, ?, ?)",
        [
            ("Hegel", "Phänomenologie des Geistes", "deu", "paragraph"),
            ("Plato", "Politeia", "grc", "stephanus"),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


def _run(fn, db_path: Path, like: str | None, capsys, **extra) -> list[dict]:
    args = argparse.Namespace(db=db_path, like=like, json=True, **extra)
    assert fn(args) == 0
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("wildcard", ["%", "_"])
def test_terms_list_like_wildcard_matches_nothing(terms_db, capsys, wildcard):
    rows = _run(cmd_terms_list, terms_db, wildcard, capsys, lang=None)
    assert rows == []


def test_terms_list_like_still_matches_substrings(terms_db, capsys):
    """Guard the fix: escaping must not break ordinary substring search."""

    rows = _run(cmd_terms_list, terms_db, "eist", capsys, lang=None)
    assert [r["source_form"] for r in rows] == ["Geist"]


def test_terms_list_like_unfiltered_returns_all(terms_db, capsys):
    """Establishes what `--like '%'` used to return, so the wildcard
    assertions above are meaningfully different from "empty DB"."""

    rows = _run(cmd_terms_list, terms_db, None, capsys, lang=None)
    assert len(rows) == 3


@pytest.mark.parametrize("wildcard", ["%", "_"])
def test_terms_works_like_wildcard_matches_nothing(terms_db, capsys, wildcard):
    rows = _run(cmd_terms_works, terms_db, wildcard, capsys)
    assert rows == []


def test_terms_works_like_matches_title_and_author(terms_db, capsys):
    """The works filter ORs across title and author — both sides need
    the escape, so both are exercised."""

    by_title = _run(cmd_terms_works, terms_db, "Politeia", capsys)
    assert [r["author"] for r in by_title] == ["Plato"]

    by_author = _run(cmd_terms_works, terms_db, "Hegel", capsys)
    assert [r["title"] for r in by_author] == ["Phänomenologie des Geistes"]


def test_terms_works_like_unfiltered_returns_all(terms_db, capsys):
    rows = _run(cmd_terms_works, terms_db, None, capsys)
    assert len(rows) == 2
