"""GET /api/chunks/{id}/syntax.

The parser is monkeypatched throughout: CI has no Stanza. What is under test
is the caching contract (parse once, read thereafter), the merge of
corrections onto the parse, and the response shape the client depends on.
"""

from __future__ import annotations

import pytest
from conftest import StubBackend, make_deps

from minerva.http.handlers.syntax import _handle_chunk_syntax
from minerva.http.server_core import _HTTPError
from minerva.syntax import queries as q

CHUNK = "rep-509d"


def fake_tokens() -> list[q.SyntaxToken]:
    """`Der Geist entwickelt.` — token 1 -> 2, 2 -> 3, 3 = root."""

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
    """Deps whose parser is a counter, so caching is observable."""

    calls: list[str] = []

    def fake_parse_text(text: str) -> list[q.SyntaxToken]:
        calls.append(text)
        return fake_tokens()

    monkeypatch.setattr("minerva.syntax.parse.parse_text", fake_parse_text)
    monkeypatch.setattr("minerva.syntax.parse.parser_id", lambda: "fake-parser")

    d = make_deps(populated_db, StubBackend())
    d.parse_calls = calls  # type: ignore[attr-defined]
    return d


def test_returns_sentences_of_tokens(deps) -> None:
    body = _handle_chunk_syntax(deps, CHUNK)

    assert body["chunk_id"] == CHUNK
    assert len(body["sentences"]) == 1
    assert [t["form"] for t in body["sentences"][0]["tokens"]] == [
        "Der",
        "Geist",
        "entwickelt",
    ]


def test_token_shape_carries_what_the_diagram_needs(deps) -> None:
    tok = _handle_chunk_syntax(deps, CHUNK)["sentences"][0]["tokens"][0]

    assert tok == {
        "id": 1,
        "form": "Der",
        "lemma": "der",
        "upos": "X",
        "feats": None,
        "head": 2,
        "deprel": "det",
        "start": 1,
        "end": 4,
        "corrected": False,
    }


def test_parses_once_then_serves_from_cache(deps) -> None:
    _handle_chunk_syntax(deps, CHUNK)
    _handle_chunk_syntax(deps, CHUNK)
    _handle_chunk_syntax(deps, CHUNK)

    assert len(deps.parse_calls) == 1


def test_unknown_chunk_is_404_not_a_parse_attempt(deps) -> None:
    with pytest.raises(_HTTPError) as exc:
        _handle_chunk_syntax(deps, "no-such-chunk")

    assert exc.value.status == 404
    assert deps.parse_calls == []


def test_corrections_are_replayed_into_the_response(deps) -> None:
    _handle_chunk_syntax(deps, CHUNK)  # populate the cache
    q.append_correction(
        deps.conn, CHUNK, sent_ord=0, tok_id=1, kind="head", from_val="2", to_val="3"
    )

    body = _handle_chunk_syntax(deps, CHUNK)

    first = body["sentences"][0]["tokens"][0]
    assert first["head"] == 3
    assert first["corrected"] is True
    assert body["corrections"] == 1


def test_a_correction_does_not_disturb_the_stored_parse(deps) -> None:
    """The machine parse is the audit trail — "what did the parser say" must
    stay answerable after any number of corrections."""

    _handle_chunk_syntax(deps, CHUNK)
    q.append_correction(
        deps.conn, CHUNK, sent_ord=0, tok_id=1, kind="head", from_val="2", to_val="3"
    )
    _handle_chunk_syntax(deps, CHUNK)

    stored = q.load_parse(deps.conn, CHUNK)
    assert stored is not None
    assert stored[0].head == 2
    assert stored[0].corrected is False


def test_multi_sentence_chunks_group_by_sentence(deps, monkeypatch: pytest.MonkeyPatch) -> None:
    def two_sentences(_text: str) -> list[q.SyntaxToken]:
        base = fake_tokens()
        second = [q.SyntaxToken(**{**vars(t), "sent_ord": 1}) for t in base[:2]]
        return base + second

    monkeypatch.setattr("minerva.syntax.parse.parse_text", two_sentences)

    body = _handle_chunk_syntax(deps, CHUNK)

    assert [s["sent_ord"] for s in body["sentences"]] == [0, 1]
    assert [len(s["tokens"]) for s in body["sentences"]] == [3, 2]
