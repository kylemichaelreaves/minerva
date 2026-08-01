"""Dependency trees for one chunk, and the hand corrections over them.

``GET /api/chunks/{id}/syntax`` parses on first request and caches; every later
call is a read. The response is the *materialised* tree — the machine parse
with hand corrections replayed over it — and each token reports whether a human
has touched it, so the client can colour by epistemic status without
re-deriving anything.

``POST …/syntax/corrections`` and ``DELETE /api/syntax/corrections/{id}`` are
the write half. They append to and remove from a log; the machine parse is
never touched, so "what did the parser originally say" stays answerable.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from ...syntax import queries as syntax_queries
from ...syntax import validate as syntax_validate
from ..server_core import ServerDeps, _HTTPError
from ._locks import with_corpus_lock


def _token_json(tok: syntax_queries.SyntaxToken) -> dict[str, Any]:
    return {
        "id": tok.tok_id,
        "form": tok.form,
        "lemma": tok.lemma,
        "upos": tok.upos,
        "feats": tok.feats,
        "head": tok.head,
        "deprel": tok.deprel,
        "start": tok.surface_start,
        "end": tok.surface_end,
        "corrected": tok.corrected,
    }


@with_corpus_lock
def _handle_chunk_syntax(deps: ServerDeps, chunk_id: str) -> dict[str, Any]:
    tokens = syntax_queries.load_or_parse(deps.conn, chunk_id)
    if tokens is None:
        raise _HTTPError(HTTPStatus.NOT_FOUND, "chunk not found")

    corrections = syntax_queries.load_corrections(deps.conn, chunk_id)
    merged = syntax_queries.materialise(tokens, corrections)

    # Group into sentences. Tokens arrive ordered by (sent_ord, tok_id), so a
    # single pass suffices; sentence ordinals are contiguous from 0.
    sentences: list[dict[str, Any]] = []
    for tok in merged:
        if not sentences or sentences[-1]["sent_ord"] != tok.sent_ord:
            sentences.append({"sent_ord": tok.sent_ord, "tokens": []})
        sentences[-1]["tokens"].append(_token_json(tok))

    return {
        "chunk_id": chunk_id,
        "sentences": sentences,
        "corrections": len(corrections),
    }


# ---------- corrections ----------


def _require_int(payload: dict[str, Any], key: str) -> int:
    """Read an integer field, refusing anything that merely looks like one.

    `bool` is excluded on purpose: it is an `int` subclass in Python, and
    `{"tok_id": true}` would otherwise be read as token 1.
    """

    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _HTTPError(HTTPStatus.BAD_REQUEST, f"{key} must be an integer")
    return value


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or value == "":
        raise _HTTPError(HTTPStatus.BAD_REQUEST, f"{key} must be a non-empty string")
    return value


def _refuse(refusal: syntax_validate.Refusal, status: HTTPStatus) -> None:
    raise _HTTPError(status, refusal.message)


@with_corpus_lock
def _handle_syntax_correction_create(
    deps: ServerDeps,
    chunk_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Append one correction, after checking it leaves a tree behind.

    Validation runs against the *materialised* tree rather than the machine
    parse: the invariants are about what the corrector is looking at, and a
    second edit must be judged against the first.

    ``from_val`` is derived here rather than taken from the payload. It is the
    inspector's "was obj", and a client-supplied value could disagree with the
    tree the correction was actually applied to.
    """

    sent_ord = _require_int(payload, "sent_ord")
    tok_id = _require_int(payload, "tok_id")
    kind = _require_str(payload, "kind")
    to_val = _require_str(payload, "to_val")

    if kind not in syntax_queries.CORRECTABLE:
        raise _HTTPError(
            HTTPStatus.BAD_REQUEST,
            f"kind must be one of {', '.join(syntax_queries.CORRECTABLE)}",
        )

    tokens = syntax_queries.load_or_parse(deps.conn, chunk_id)
    if tokens is None:
        raise _HTTPError(HTTPStatus.NOT_FOUND, "chunk not found")

    corrections = syntax_queries.load_corrections(deps.conn, chunk_id)
    current = syntax_queries.materialise(tokens, corrections)

    target = next(
        (t for t in current if t.sent_ord == sent_ord and t.tok_id == tok_id),
        None,
    )
    if target is None:
        raise _HTTPError(
            HTTPStatus.NOT_FOUND,
            f"no token {tok_id} in sentence {sent_ord} of this chunk",
        )

    if kind == "head":
        try:
            new_head = int(to_val)
        except ValueError:
            raise _HTTPError(HTTPStatus.BAD_REQUEST, "a head must be an integer") from None
        refusal = syntax_validate.validate_head(
            current, sent_ord=sent_ord, tok_id=tok_id, new_head=new_head
        )
        if refusal is not None:
            _refuse(refusal, HTTPStatus.CONFLICT)
        from_val = None if target.head is None else str(target.head)
    else:
        refusal = syntax_validate.validate_deprel(to_val)
        if refusal is not None:
            _refuse(refusal, HTTPStatus.BAD_REQUEST)
        from_val = target.deprel

    correction_id = syntax_queries.append_correction(
        deps.conn,
        chunk_id,
        sent_ord=sent_ord,
        tok_id=tok_id,
        kind=kind,
        from_val=from_val,
        to_val=to_val,
    )

    updated = syntax_queries.materialise(
        tokens, syntax_queries.load_corrections(deps.conn, chunk_id)
    )
    token = next(t for t in updated if t.sent_ord == sent_ord and t.tok_id == tok_id)

    return {
        "id": correction_id,
        "chunk_id": chunk_id,
        "sent_ord": sent_ord,
        "token": _token_json(token),
        "corrections": len(corrections) + 1,
    }


@with_corpus_lock
def _handle_syntax_correction_delete(deps: ServerDeps, correction_id: int) -> bool:
    """Undo one correction. False when there was no such row."""

    return syntax_queries.delete_correction(deps.conn, correction_id)
