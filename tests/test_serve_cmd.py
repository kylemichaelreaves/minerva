"""`cmd_serve` itself — the wiring between argv and `server.serve` (#584).

`tests/test_cli_args.py` exercised `register()` through `build_parser()`, so
the argparse surface was covered and the function it dispatches to was not:
every line of `cmd_serve` read 0 hits. The three behaviours below are the ones
with a return value an operator sees — the refusal, the backend failure, and
the lock being released however `serve` ends.

`server.serve` blocks forever, so it is replaced. That is the point of the
seam: everything up to the call is what this tests.
"""

from __future__ import annotations

import sqlite3

import pytest

from minerva import llm
from minerva.cli import serve_cmd


@pytest.fixture
def args(tmp_path, populated_db, db_path):
    """Parsed from the REAL parser, not hand-built.

    A hand-written `argparse.Namespace` drifts silently: it is the shape
    `register()` had when the test was written, and a new option — or a
    `type=Path` where the test wrote `str` — goes unnoticed until `cmd_serve`
    trips over it in production. Parsing real argv keeps the two in step.
    """

    from minerva.cli import build_parser

    return build_parser().parse_args(
        [
            "serve",
            # `db_path`, not `populated_db` — the latter is the seeded
            # CONNECTION, and str() on it yields
            # "<sqlite3.Connection object at 0x...>", which argparse accepts
            # and `store.open_db` then CREATES as an empty database in the
            # CWD. The test still passes; it is just no longer testing
            # anything, and it litters the repo root.
            "--db", str(db_path),
            "--conversations-db", str(tmp_path / "conversations.sqlite"),
            "--translations-db", str(tmp_path / "translations.sqlite"),
            "--concept-cache-db", str(tmp_path / "concepts.sqlite"),
            "--metrics-db", str(tmp_path / "metrics.sqlite"),
            "--llm", "none",
        ]
    )


def test_refuses_when_another_server_holds_the_lock(args, monkeypatch, capsys):
    monkeypatch.setattr(
        serve_cmd.serve_lock, "find_running_server", lambda _db: "pid 4242 on port 8000"
    )
    assert serve_cmd.cmd_serve(args) == 2
    err = capsys.readouterr().err
    assert "already running" in err
    assert "pid 4242" in err


def test_a_backend_that_cannot_be_built_exits_2_without_taking_the_lock(
    args, monkeypatch, capsys
):
    monkeypatch.setattr(serve_cmd.serve_lock, "find_running_server", lambda _db: None)
    monkeypatch.setattr(
        serve_cmd, "make_backend", lambda _a: (_ for _ in ()).throw(llm.LLMError("no api key"))
    )

    def fail(*a, **k):
        raise AssertionError("the lock must not be written when startup fails")

    monkeypatch.setattr(serve_cmd.serve_lock, "write_serve_lock", fail)

    assert serve_cmd.cmd_serve(args) == 2
    assert "no api key" in capsys.readouterr().err


def test_the_serve_lock_is_cleared_even_when_serve_raises(args, monkeypatch):
    """`finally: clear_serve_lock` is what stops a crash from locking out the
    next start — the failure mode the lock exists to prevent, inverted."""

    from minerva import server as server_mod

    monkeypatch.setattr(serve_cmd.serve_lock, "find_running_server", lambda _db: None)
    calls: list[str] = []
    monkeypatch.setattr(
        serve_cmd.serve_lock, "write_serve_lock", lambda *a, **k: calls.append("write")
    )
    monkeypatch.setattr(
        serve_cmd.serve_lock, "clear_serve_lock", lambda *a, **k: calls.append("clear")
    )

    def boom(**kwargs):
        calls.append("serve")
        raise KeyboardInterrupt

    monkeypatch.setattr(server_mod, "serve", boom)

    with pytest.raises(KeyboardInterrupt):
        serve_cmd.cmd_serve(args)
    assert calls == ["write", "serve", "clear"]


def test_no_metrics_skips_the_metrics_database(args, monkeypatch, tmp_path):
    from minerva import server as server_mod

    args.no_metrics = True
    monkeypatch.setattr(serve_cmd.serve_lock, "find_running_server", lambda _db: None)
    monkeypatch.setattr(serve_cmd.serve_lock, "write_serve_lock", lambda *a, **k: None)
    monkeypatch.setattr(serve_cmd.serve_lock, "clear_serve_lock", lambda *a, **k: None)
    seen: dict[str, object] = {}
    monkeypatch.setattr(server_mod, "serve", lambda **kw: seen.update(kw))

    assert serve_cmd.cmd_serve(args) == 0
    assert seen["metrics_conn"] is None
    assert not (tmp_path / "metrics.sqlite").exists()
    # Proves the connection handed to `serve` is the SEEDED index and not a
    # fresh empty file created from a mis-stringified path.
    assert isinstance(seen["conn"], sqlite3.Connection)
    assert seen["conn"].execute("SELECT count(*) FROM chunks").fetchone()[0] > 0


def test_a_backend_failure_opens_no_databases_at_all(args, monkeypatch, capsys):
    """#614: four connections were opened before the backend was built, and
    the LLMError path returned past them without closing any.

    Asserted as ORDERING rather than by counting live handles: the fix is that
    `make_backend` runs first, so there is no window to leak in. Counting
    handles would pass just as well for a fix that opened them and closed them
    in a `finally`, which is a different and larger change.
    """

    opened: list[str] = []
    monkeypatch.setattr(serve_cmd.serve_lock, "find_running_server", lambda _db: None)
    for name in ("store", "conversations", "translations", "concept_cache"):
        mod = getattr(serve_cmd, name)
        real = mod.open_db

        def spy(*a, _n=name, _real=real, **k):
            opened.append(_n)
            return _real(*a, **k)

        monkeypatch.setattr(mod, "open_db", spy)

    monkeypatch.setattr(
        serve_cmd, "make_backend", lambda _a: (_ for _ in ()).throw(llm.LLMError("no api key"))
    )

    assert serve_cmd.cmd_serve(args) == 2
    assert opened == [], f"opened {opened} before discovering the backend could not be built"
    assert "no api key" in capsys.readouterr().err
