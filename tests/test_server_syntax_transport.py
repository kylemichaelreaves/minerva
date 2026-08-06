"""The correction routes over a real socket.

Handler-level tests cover the logic; these cover the things that only exist in
the transport: the status codes the client branches on, the CSRF defences the
new POST inherits, and the 404 that a DELETE of a missing row must produce.

The last one is the reason this file exists. ``do_DELETE`` answered every
falsy handler result with the literal string "conversation not found" — true
when conversations were the only DELETE route, and wrong the moment a second
one landed.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from conftest import StubBackend, make_deps

from minerva import conversations, store, translations
from minerva.http import server_core
from minerva.http.serve import make_handler
from minerva.syntax import queries as q

ALLOWED = "http://127.0.0.1:5173"
EVIL = "https://evil.example"
CHUNK = "rep-509d"


def fake_tokens() -> list[q.SyntaxToken]:
    def t(tok_id, form, head, deprel):
        return q.SyntaxToken(
            sent_ord=0,
            tok_id=tok_id,
            form=form,
            lemma=form.lower(),
            upos="X",
            xpos=None,
            feats=None,
            misc=None,
            head=head,
            deprel=deprel,
            surface_start=tok_id,
            surface_end=tok_id + len(form),
        )

    return [t(1, "Der", 2, "det"), t(2, "Geist", 3, "nsubj"), t(3, "entwickelt", 0, "root")]


@contextmanager
def running(deps: Any) -> Iterator[str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(deps))
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def request(
    url: str,
    *,
    method: str = "POST",
    body: dict[str, Any] | None = None,
    content_type: str | None = "application/json",
    origin: str | None = None,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers: dict[str, str] = {}
    if content_type is not None:
        headers["Content-Type"] = content_type
    if origin is not None:
        headers["Origin"] = origin

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, (json.loads(raw) if raw else {})


def _path_of(conn: Any) -> Path:
    return Path(str(conn.execute("PRAGMA database_list").fetchone()[2]))


@pytest.fixture
def deps(populated_db, monkeypatch: pytest.MonkeyPatch):
    """Server deps whose connections survive the handler threads. See the
    equivalent fixture in test_server_csrf.py for why they are reopened."""

    monkeypatch.setattr("minerva.syntax.parse.parse_text", lambda _text: fake_tokens())
    monkeypatch.setattr("minerva.syntax.parse.parser_id", lambda: "fake-parser")

    d = make_deps(populated_db, StubBackend(reply="ok"))
    d.conn = store.open_db(_path_of(d.conn), check_same_thread=False)
    d.conversations_conn = conversations.open_db(
        _path_of(d.conversations_conn), check_same_thread=False
    )
    d.translations_conn = translations.open_db(
        _path_of(d.translations_conn), check_same_thread=False
    )
    d.allowed_origins = frozenset({ALLOWED})
    return d


def test_a_correction_round_trips_over_http(deps) -> None:
    with running(deps) as base:
        status, body = request(
            f"{base}/api/chunks/{CHUNK}/syntax/corrections",
            body={"sent_ord": 0, "tok_id": 1, "kind": "deprel", "to_val": "nmod"},
        )

    assert status == 200
    assert body["token"]["deprel"] == "nmod"


def test_undo_answers_204_with_no_body(deps) -> None:
    with running(deps) as base:
        _, created = request(
            f"{base}/api/chunks/{CHUNK}/syntax/corrections",
            body={"sent_ord": 0, "tok_id": 1, "kind": "deprel", "to_val": "nmod"},
        )
        status, _ = request(f"{base}/api/syntax/corrections/{created['id']}", method="DELETE")

    assert status == 204


def test_undo_of_a_missing_correction_says_so(deps) -> None:
    with running(deps) as base:
        status, body = request(f"{base}/api/syntax/corrections/999999", method="DELETE")

    assert status == 404
    # The bug: this used to read "conversation not found" on every DELETE
    # route, whatever the route was.
    assert "conversation" not in body["error"]
    assert "correction" in body["error"]


def test_a_refused_correction_answers_409(deps) -> None:
    with running(deps) as base:
        status, body = request(
            f"{base}/api/chunks/{CHUNK}/syntax/corrections",
            body={"sent_ord": 0, "tok_id": 2, "kind": "head", "to_val": "1"},
        )

    assert status == 409
    assert "subtree" in body["error"]


def test_the_new_post_refuses_a_cross_origin_write(deps) -> None:
    """This route mutates the most expensive data the system holds, so the
    #118 defences have to cover it and not just /api/chat."""

    with running(deps) as base:
        status, _ = request(
            f"{base}/api/chunks/{CHUNK}/syntax/corrections",
            body={"sent_ord": 0, "tok_id": 1, "kind": "deprel", "to_val": "nmod"},
            origin=EVIL,
        )

    assert status == 403
    assert q.load_corrections(deps.conn, CHUNK) == []


def test_the_new_post_refuses_a_form_content_type(deps) -> None:
    with running(deps) as base:
        status, _ = request(
            f"{base}/api/chunks/{CHUNK}/syntax/corrections",
            body={"sent_ord": 0, "tok_id": 1, "kind": "deprel", "to_val": "nmod"},
            content_type=None,
        )

    assert status == 415
    assert q.load_corrections(deps.conn, CHUNK) == []


def test_undo_refuses_a_cross_origin_delete(deps) -> None:
    with running(deps) as base:
        _, created = request(
            f"{base}/api/chunks/{CHUNK}/syntax/corrections",
            body={"sent_ord": 0, "tok_id": 1, "kind": "deprel", "to_val": "nmod"},
        )
        status, _ = request(
            f"{base}/api/syntax/corrections/{created['id']}",
            method="DELETE",
            origin=EVIL,
        )

    assert status == 403
    assert len(q.load_corrections(deps.conn, CHUNK)) == 1


def test_the_correction_post_is_rate_limited(deps, monkeypatch: pytest.MonkeyPatch) -> None:
    """An uncached correction runs a Stanza parse, same as the GET.

    Keyed by router label, not path: this route's path carries a chunk id and
    would never match a fixed string in `_RATE_LIMITS`.
    """

    monkeypatch.setitem(server_core._RATE_LIMITS, "syntax correction create", (2, 60.0))

    codes = []
    with running(deps) as base:
        # Distinct relations, all of them real: a digit would fail the deprel
        # shape check and answer 400 before the limiter was ever the reason.
        for relation in ("nmod", "amod", "appos"):
            status, _ = request(
                f"{base}/api/chunks/{CHUNK}/syntax/corrections",
                body={"sent_ord": 0, "tok_id": 1, "kind": "deprel", "to_val": relation},
            )
            codes.append(status)

    assert codes[:2] == [200, 200]
    assert codes[2] == 429


def test_chat_is_still_rate_limited_after_the_switch_to_labels(
    deps, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard for the key change: /api/chat's limit was keyed by
    path and is now keyed by its label."""

    monkeypatch.setitem(server_core._RATE_LIMITS, "chat", (1, 60.0))

    codes = []
    with running(deps) as base:
        for _ in range(2):
            status, _ = request(f"{base}/api/chat", body={"message": "hallo"})
            codes.append(status)

    assert codes[1] == 429
