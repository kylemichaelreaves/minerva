"""Every `terms` subcommand must close the DB connection it opened (#227).

The leak was invisible in normal runs — the CLI process exits after one
command and the OS reclaims the handle — so it only showed up as 68
`ResourceWarning`s once the suite promoted them to errors, and it kept
the repo from adopting `-W error::ResourceWarning` as a broad hygiene
gate.

Two guards here, because they fail on different mistakes:

* the behavioural tests catch a connection left open on a *path* —
  notably the early `return 1` exits, which is where a `close()` at the
  bottom of a handler body would have missed it;
* `test_every_terms_handler_closes_its_connection` catches a *new*
  handler added without either mechanism, which no behavioural test can
  see because it doesn't know the handler exists.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import sqlite3
from pathlib import Path

import pytest

from minerva import store
from minerva.cli.terms._io import _with_db
from minerva.cli.terms.crud import cmd_terms_list, cmd_terms_show
from minerva.cli.terms.linking import cmd_terms_relate

# The five modules that define `terms` subcommand handlers.
_HANDLER_MODULES = ("bulk", "crud", "lemmatize", "linking", "locators")


@pytest.fixture
def db(tmp_path: Path) -> Path:
    """A minimal store — one term, so the read paths have a row to find
    and the not-found paths have something to miss."""

    path = tmp_path / "curator.sqlite"
    conn = store.open_db(path)
    conn.execute(
        "INSERT INTO terms (id, source_form, source_language, short_gloss, "
        "long_description) VALUES (1, 'Geist', 'deu', 'spirit', '')"
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def opened(db: Path, monkeypatch: pytest.MonkeyPatch) -> list[sqlite3.Connection]:
    """Record every connection the handlers open.

    Patched after `db` has built its fixture data, so the list holds only
    connections opened by the code under test.
    """

    conns: list[sqlite3.Connection] = []
    real = store.open_db

    def spy(path, **kwargs):  # type: ignore[no-untyped-def]
        conn = real(path, **kwargs)
        conns.append(conn)
        return conn

    monkeypatch.setattr(store, "open_db", spy)
    return conns


def _is_closed(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


def _assert_all_closed(conns: list[sqlite3.Connection]) -> None:
    assert conns, "handler opened no connection — the spy is not wired up"
    assert all(_is_closed(c) for c in conns)


def test_connection_closed_on_the_success_path(db, opened, capsys):
    ns = argparse.Namespace(db=db, lang=None, like=None, work_id=None, json=False)
    assert cmd_terms_list(ns) == 0
    capsys.readouterr()
    _assert_all_closed(opened)


def test_connection_closed_when_the_handler_returns_early(db, opened, capsys):
    """`show` bails with 1 on an unknown form, part-way through the body.
    A `close()` appended to the end of the handler would miss this."""

    ns = argparse.Namespace(db=db, term_id_or_form="Nichts", lang=None)
    assert cmd_terms_show(ns) == 1
    capsys.readouterr()
    _assert_all_closed(opened)


def test_connection_closed_when_the_handler_never_uses_it(db, opened, capsys):
    """`relate` rejects a self-relation before touching the DB. The
    decorator opens the connection regardless, so it must close it."""

    ns = argparse.Namespace(db=db, a=1, b=1, kind="cognate", note=None, note_file=None)
    assert cmd_terms_relate(ns) == 1
    capsys.readouterr()
    _assert_all_closed(opened)


def test_connection_closed_when_the_handler_raises(db, opened):
    """An exception out of the body must not strand the connection."""

    @_with_db
    def boom(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
        conn.execute("SELECT 1")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        boom(argparse.Namespace(db=db))
    _assert_all_closed(opened)


def test_every_terms_handler_closes_its_connection():
    """Structural guard: a handler must carry `@_with_db` or close its
    own connection. `bulk` and `lemmatize` do the latter — they use the
    connection for a bounded phase and print their report after closing
    it — so this asserts the invariant, not one particular mechanism."""

    handlers = {}
    for modname in _HANDLER_MODULES:
        mod = importlib.import_module(f"minerva.cli.terms.{modname}")
        for name, fn in vars(mod).items():
            if name.startswith("cmd_terms_") and callable(fn) and fn.__module__ == mod.__name__:
                handlers[f"{modname}.{name}"] = fn

    # 4 crud + 5 linking + 3 locators + 1 bulk + 1 lemmatize as of #227.
    assert len(handlers) >= 14, f"handler discovery found only {sorted(handlers)}"

    for label, fn in handlers.items():
        if getattr(fn, "_closes_db", False):
            continue
        assert "conn.close()" in inspect.getsource(fn), (
            f"{label} neither carries @_with_db nor closes its connection (#227)"
        )
