"""POST /api/chunks/{id}/syntax/corrections and DELETE /api/syntax/corrections/{id}.

The write half of the close-reading overlay. These are the routes that mutate
durable scholarly data — the most expensive rows the system holds — so what is
under test is mostly what the endpoint *refuses*: a malformed payload, an edit
that would break the tree, and an edit aimed at a chunk or token that is not
there. A refusal must leave the log untouched.

The parser is monkeypatched throughout; CI has no Stanza.
"""

from __future__ import annotations

import pytest
from conftest import StubBackend, make_deps

from minerva.http.handlers.syntax import (
    _handle_chunk_syntax,
    _handle_syntax_correction_create,
    _handle_syntax_correction_delete,
)
from minerva.http.server_core import _HTTPError
from minerva.syntax import queries as q

# The syntax path is German-only (see `load_or_parse`); an English chunk
# is refused, so this cannot be one of the Plato fixtures.
CHUNK = "hegel-p17"


def fake_tokens() -> list[q.SyntaxToken]:
    """`Der Geist entwickelt.` — 1 -> 2, 2 -> 3, 3 = root."""

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


@pytest.fixture
def deps(populated_db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("minerva.syntax.parse.parse_text", lambda _text: fake_tokens())
    monkeypatch.setattr("minerva.syntax.parse.parser_id", lambda: "fake-parser")
    return make_deps(populated_db, StubBackend())


def post(deps, **payload):
    return _handle_syntax_correction_create(deps, CHUNK, payload)


# ---------- the happy path ----------


def test_relabelling_a_token_records_the_correction(deps) -> None:
    body = post(deps, sent_ord=0, tok_id=1, kind="deprel", to_val="nmod")

    assert body["id"] > 0
    assert body["token"]["deprel"] == "nmod"
    assert body["token"]["corrected"] is True
    assert body["corrections"] == 1


def test_reattaching_a_token_records_the_correction(deps) -> None:
    body = post(deps, sent_ord=0, tok_id=1, kind="head", to_val="3")

    assert body["token"]["head"] == 3
    assert body["token"]["corrected"] is True


def test_the_previous_value_is_captured_without_the_client_sending_it(deps) -> None:
    """`from_val` is provenance — the inspector's "was obj". Deriving it here
    rather than trusting the client means it cannot disagree with the tree the
    correction was actually applied to."""

    post(deps, sent_ord=0, tok_id=1, kind="deprel", to_val="nmod")

    (correction,) = q.load_corrections(deps.conn, CHUNK)
    assert correction.from_val == "det"
    assert correction.to_val == "nmod"


def test_a_second_edit_to_one_token_supersedes_the_first(deps) -> None:
    post(deps, sent_ord=0, tok_id=1, kind="deprel", to_val="nmod")
    body = post(deps, sent_ord=0, tok_id=1, kind="deprel", to_val="amod")

    assert body["token"]["deprel"] == "amod"
    # Append-only: both rows survive, and the later one wins on replay.
    assert len(q.load_corrections(deps.conn, CHUNK)) == 2
    assert body["corrections"] == 2


def test_the_second_edit_records_the_corrected_value_it_replaced(deps) -> None:
    post(deps, sent_ord=0, tok_id=1, kind="deprel", to_val="nmod")
    post(deps, sent_ord=0, tok_id=1, kind="deprel", to_val="amod")

    second = q.load_corrections(deps.conn, CHUNK)[1]
    assert second.from_val == "nmod"


def test_a_correction_parses_the_chunk_if_it_has_never_been_opened(deps) -> None:
    """Reachable from a script, and from a client that posts before its own
    GET lands. Validation needs the tree, so the parse cannot be skipped."""

    body = post(deps, sent_ord=0, tok_id=1, kind="head", to_val="3")

    assert body["token"]["head"] == 3


# ---------- the refusals ----------


def test_refuses_a_cycle_and_writes_nothing(deps) -> None:
    with pytest.raises(_HTTPError) as exc:
        post(deps, sent_ord=0, tok_id=2, kind="head", to_val="1")

    assert exc.value.status == 409
    assert "subtree" in exc.value.message
    assert q.load_corrections(deps.conn, CHUNK) == []


def test_refuses_detaching_the_only_root_and_writes_nothing(deps) -> None:
    with pytest.raises(_HTTPError) as exc:
        post(deps, sent_ord=0, tok_id=3, kind="head", to_val="2")

    assert exc.value.status == 409
    assert "root" in exc.value.message
    assert q.load_corrections(deps.conn, CHUNK) == []


def test_refuses_a_second_root(deps) -> None:
    with pytest.raises(_HTTPError) as exc:
        post(deps, sent_ord=0, tok_id=1, kind="head", to_val="0")

    assert exc.value.status == 409
    assert q.load_corrections(deps.conn, CHUNK) == []


def test_refuses_a_relation_that_is_not_a_ud_label(deps) -> None:
    with pytest.raises(_HTTPError) as exc:
        post(deps, sent_ord=0, tok_id=1, kind="deprel", to_val="Sb")

    assert exc.value.status == 400
    assert q.load_corrections(deps.conn, CHUNK) == []


def test_validates_against_the_corrected_tree_not_the_machine_parse(deps) -> None:
    """The invariants are about the tree in front of the user. Checking the
    pristine parse instead would let a second edit reintroduce a cycle the
    first one had just moved out of the way."""

    # Move 1 under the root, so 2 no longer governs it.
    post(deps, sent_ord=0, tok_id=1, kind="head", to_val="3")
    # Against the machine parse this closes 2 -> 1 -> 2; against the corrected
    # tree it is fine.
    body = post(deps, sent_ord=0, tok_id=2, kind="head", to_val="1")

    assert body["token"]["head"] == 1


# ---------- malformed input ----------


def test_unknown_chunk_is_404(deps) -> None:
    with pytest.raises(_HTTPError) as exc:
        _handle_syntax_correction_create(
            deps, "no-such-chunk", {"sent_ord": 0, "tok_id": 1, "kind": "head", "to_val": "3"}
        )

    assert exc.value.status == 404


def test_unknown_token_is_refused(deps) -> None:
    # 404, not 400: the payload is well-formed, the token it addresses is not
    # there. Same reading as an unknown chunk.
    with pytest.raises(_HTTPError) as exc:
        post(deps, sent_ord=0, tok_id=99, kind="head", to_val="1")

    assert exc.value.status == 404
    assert q.load_corrections(deps.conn, CHUNK) == []


def test_refuses_a_kind_that_is_not_correctable(deps) -> None:
    with pytest.raises(_HTTPError) as exc:
        post(deps, sent_ord=0, tok_id=1, kind="lemma", to_val="x")

    assert exc.value.status == 400


def test_refuses_a_missing_field(deps) -> None:
    with pytest.raises(_HTTPError) as exc:
        _handle_syntax_correction_create(deps, CHUNK, {"sent_ord": 0, "kind": "head"})

    assert exc.value.status == 400


def test_refuses_a_head_that_is_not_an_integer(deps) -> None:
    with pytest.raises(_HTTPError) as exc:
        post(deps, sent_ord=0, tok_id=1, kind="head", to_val="root")

    assert exc.value.status == 400


def test_refuses_a_non_integer_token_id(deps) -> None:
    with pytest.raises(_HTTPError) as exc:
        post(deps, sent_ord=0, tok_id="1; DROP TABLE chunks", kind="head", to_val="3")

    assert exc.value.status == 400


# ---------- undo ----------


def replayed_deprel(deps, tok_id: int) -> str | None:
    """The relation a client would show, replaying the log the way it does.

    The GET answers with the pristine parse and the log side by side, so this
    mirrors `applyCorrections` in `Syntax/corrections/apply.ts`: last write per
    token wins, in id order.
    """

    body = _handle_chunk_syntax(deps, CHUNK)
    token = next(t for t in body["sentences"][0]["tokens"] if t["id"] == tok_id)
    deprel = token["deprel"]
    for c in sorted(body["corrections"], key=lambda c: c["id"]):
        if c["tok_id"] == tok_id and c["kind"] == "deprel":
            deprel = c["to_val"]
    return deprel


def test_deleting_a_correction_reverts_the_token(deps) -> None:
    created = post(deps, sent_ord=0, tok_id=1, kind="deprel", to_val="nmod")

    assert _handle_syntax_correction_delete(deps, created["id"]) is True

    assert replayed_deprel(deps, 1) == "det"
    assert _handle_chunk_syntax(deps, CHUNK)["corrections"] == []


def test_deleting_an_unknown_correction_reports_that_nothing_went(deps) -> None:
    assert _handle_syntax_correction_delete(deps, 4242) is False


def test_undo_of_the_later_edit_leaves_the_earlier_one_standing(deps) -> None:
    post(deps, sent_ord=0, tok_id=1, kind="deprel", to_val="nmod")
    second = post(deps, sent_ord=0, tok_id=1, kind="deprel", to_val="amod")

    _handle_syntax_correction_delete(deps, second["id"])

    assert replayed_deprel(deps, 1) == "nmod"
