"""Tests for the throwaway-DB plumbing in `conftest.py` itself.

`make_deps` hands out `conversations` / `translations` connections that
nobody owns. Before #246 they were never closed, so a full run emitted
900 `ResourceWarning: unclosed database` warnings and
`-W error::ResourceWarning` — a cheap, broad hygiene gate — could not be
switched on. These tests pin the teardown that makes the gate possible.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from conftest import (  # type: ignore[import-not-found]
    StubBackend,
    _close_throwaway_conns,
    _conv_conn,
    _owner_is_test_code,
    _trans_conn,
    make_deps,
)

from minerva import store


def _is_closed(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


def test_close_throwaway_conns_closes_connections_handed_out_by_the_helpers() -> None:
    conv = _conv_conn()
    trans = _trans_conn()
    assert not _is_closed(conv)
    assert not _is_closed(trans)

    _close_throwaway_conns()

    assert _is_closed(conv)
    assert _is_closed(trans)


def test_close_throwaway_conns_closes_every_connection_make_deps_opened(
    populated_db: sqlite3.Connection,
) -> None:
    deps = make_deps(populated_db, StubBackend())

    _close_throwaway_conns()

    assert _is_closed(deps.conversations_conn)
    assert _is_closed(deps.translations_conn)
    # The corpus connection is swept too. It is opened by the
    # `populated_db` fixture — test code — so the registry owns it, and
    # the fixture's own `conn.close()` is then a harmless second close.
    assert _is_closed(deps.conn)


def test_a_connection_a_test_still_needs_survives_until_teardown(
    populated_db: sqlite3.Connection,
) -> None:
    """The sweep runs at teardown, never mid-test.

    Several tests pass their own connection to `make_deps`
    (`test_chat_stream`, `test_lock_split`, `test_server_reader`) and
    assert against it after the handler returns. That works because
    `_close_throwaway_conns_after_each_test` fires after the test body,
    not because those connections are unowned — this pins the timing,
    which is the property they actually depend on.
    """

    caller_owned = sqlite3.connect(":memory:")
    deps = make_deps(populated_db, StubBackend(), conversations_conn=caller_owned)

    # No sweep call here: this is the ordinary in-test state.
    assert not _is_closed(caller_owned)
    assert not _is_closed(deps.translations_conn)
    caller_owned.execute("SELECT 1")


def test_close_throwaway_conns_is_idempotent() -> None:
    conv = _conv_conn()

    _close_throwaway_conns()
    _close_throwaway_conns()  # must not raise on an already-closed conn

    assert _is_closed(conv)


class TestOwnerAttribution:
    """The sweep closes connections *test code* opened, and only those.

    That asymmetry is the whole point. If it swept everything, a
    connection leaked by a production code path would be quietly closed
    at teardown and `-W error::ResourceWarning` would go green over a
    real bug — which is exactly the class of defect the gate found in six
    CLI handlers while #246 was being fixed.
    """

    def test_a_connection_a_test_opens_through_store_open_db_is_swept(self, tmp_path: Path) -> None:
        # `store.open_db` → `store.schema` → `sqlite_util.open_sqlite` →
        # `sqlite3.connect`. Every frame in that chain is plumbing, so
        # the owner is this test.
        conn = store.open_db(tmp_path / "owned.sqlite")

        _close_throwaway_conns()

        assert _is_closed(conn)

    def test_a_bare_sqlite3_connect_in_a_test_is_swept(self) -> None:
        """The `sqlite3.connect(":memory:")` shape, which bypasses
        `open_sqlite` entirely — 42 of the suite's warnings came from one
        such line in `test_detect_work.py`."""

        conn = sqlite3.connect(":memory:")

        _close_throwaway_conns()

        assert _is_closed(conn)

    def test_a_frame_from_production_code_is_not_treated_as_test_owned(self) -> None:
        """Compile a call under a production filename to synthesise the
        frame a leaking CLI handler would produce."""

        code = compile(
            "verdict = probe()",
            "/Users/x/src/minerva/src/minerva/cli/some_cmd.py",
            "exec",
        )
        namespace: dict[str, object] = {"probe": _owner_is_test_code}
        exec(code, namespace)

        assert namespace["verdict"] is False

    def test_a_frame_from_test_code_is_treated_as_test_owned(self) -> None:
        # Under the real tests directory — attribution compares against
        # this file's own parent, so a look-alike path elsewhere is
        # (correctly) not test code.
        code = compile(
            "verdict = probe()",
            str(Path(__file__).parent / "test_synthetic.py"),
            "exec",
        )
        namespace: dict[str, object] = {"probe": _owner_is_test_code}
        exec(code, namespace)

        assert namespace["verdict"] is True


# There is deliberately no test here asserting "the suite emits no
# `unclosed database` warning". A `recwarn`-based version of that
# assertion cannot work: `sqlite3.Connection.__del__` is what emits the
# warning, so a connection leaked by an *earlier* test surfaces during
# whichever later test happens to trigger collection — the assertion
# then fails in a test that is not the one at fault. (Written that way
# first; it went red on six unrelated leaks.) The
# `-W error::ResourceWarning` entry in `[tool.pytest.ini_options]`
# addopts is the same assertion done correctly: it fires on the leaking
# test, and `-X tracemalloc=N` points at the allocation site.
