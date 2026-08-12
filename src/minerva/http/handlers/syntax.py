"""Dependency trees for one chunk, and the hand corrections over them.

``GET /api/chunks/{id}/syntax`` parses on first request and caches; every later
call is a read. It answers with the **pristine machine parse and the
correction log separately**, rather than with the two already merged.

That is deliberate. The client replays the log itself
(`Syntax/corrections/apply.ts`, the mirror of :func:`materialise`), which is
what makes the optimistic queue and undo work: to take a correction back the
client has to know its id and be able to recompute the tree without it, and
neither is possible from a merged tree. Merging server-side would also mean
every undo needed a round trip to see its own effect.

``POST …/syntax/corrections`` and ``DELETE /api/syntax/corrections/{id}`` are
the write half. They append to and remove from a log; the machine parse is
never touched, so "what did the parser originally say" stays answerable.
"""

from __future__ import annotations

from collections.abc import Sequence
from http import HTTPStatus
from typing import Any

from ...syntax import queries as syntax_queries
from ...syntax import validate as syntax_validate
from ..server_core import ServerDeps, _HTTPError
from ._locks import map_domain_errors, with_corpus_lock


def _token_json(tok: syntax_queries.SyntaxToken) -> dict[str, Any]:
    return {
        "id": tok.tok_id,
        "form": tok.form,
        "lemma": tok.lemma,
        "upos": tok.upos,
        # The German tagset says things UPOS cannot — PRF for a reflexive,
        # which is exactly the distinction the `expl:pv` correction turns on.
        # Also the difference between a faithful CoNLL-U export and a lossy one.
        "xpos": tok.xpos,
        "feats": tok.feats,
        "misc": tok.misc,
        "head": tok.head,
        "deprel": tok.deprel,
        "start": tok.surface_start,
        "end": tok.surface_end,
        "corrected": tok.corrected,
    }


def _correction_json(c: syntax_queries.Correction) -> dict[str, Any]:
    return {
        "id": c.id,
        "sent_ord": c.sent_ord,
        "tok_id": c.tok_id,
        "kind": c.kind,
        "from_val": c.from_val,
        "to_val": c.to_val,
    }


def _load_or_parse_or_400(deps: ServerDeps, chunk_id: str) -> list[syntax_queries.SyntaxToken]:
    """`load_or_parse_locked`, with its language refusal mapped to an HTTP status.

    Shared by both handlers that reach the parser: the GET path and the
    correction-create path. 400, not 404, for a wrong-language chunk — the
    chunk exists, the request is the problem, and a 404 here would send the
    caller looking for a missing chunk instead. A missing chunk still 404s,
    via the `None` return `load_or_parse` documents for that case.

    Takes `deps.corpus_lock` itself, around the database work only, so the
    Stanza parse does not stall other readers (#340). Neither caller may
    hold that lock when it gets here — see the note on each.
    """

    try:
        tokens = syntax_queries.load_or_parse_locked(deps.conn, chunk_id, deps.corpus_lock)
    except syntax_queries.UnsupportedSyntaxLanguage as exc:
        raise _HTTPError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
    if tokens is None:
        raise _HTTPError(HTTPStatus.NOT_FOUND, "chunk not found")
    return tokens


# NOT `@with_corpus_lock`: the parse inside `_load_or_parse_or_400` must run
# outside the lock, and it takes the lock itself for the parts that need it.
# `map_domain_errors` still has to be applied by hand — it normally arrives
# as part of the lock decorator.
@map_domain_errors
def _handle_chunk_syntax(deps: ServerDeps, chunk_id: str) -> dict[str, Any]:
    tokens = _load_or_parse_or_400(deps, chunk_id)

    with deps.corpus_lock:
        corrections = syntax_queries.load_corrections(deps.conn, chunk_id)

    # Group into sentences. Tokens arrive ordered by (sent_ord, tok_id), so a
    # single pass suffices; sentence ordinals are contiguous from 0.
    sentences: list[dict[str, Any]] = []
    for tok in tokens:
        if not sentences or sentences[-1]["sent_ord"] != tok.sent_ord:
            sentences.append({"sent_ord": tok.sent_ord, "tokens": []})
        sentences[-1]["tokens"].append(_token_json(tok))

    return {
        "chunk_id": chunk_id,
        "sentences": sentences,
        # The log itself, not just its effect. Undo addresses a correction by
        # id, and the inspector's "was obj" is a `from_val` — with only the
        # materialised tree, a reload leaves Revert pointing at nothing.
        "corrections": [_correction_json(c) for c in corrections],
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


def _check_and_prior_value(
    current: Sequence[syntax_queries.SyntaxToken],
    *,
    kind: str,
    to_val: str,
    sent_ord: int,
    tok_id: int,
    target: syntax_queries.SyntaxToken,
) -> str | None:
    """Validate one edit and return the value it replaces.

    Split out of the handler so each kind's rule sits on its own, and so the
    handler stays under the cognitive-complexity bar it crossed when `upos`
    became the third kind (#253). Raises `_HTTPError` on a refusal; returns
    `from_val` otherwise, which the caller records as provenance.
    """

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
        return None if target.head is None else str(target.head)

    if kind == "upos":
        # Membership, not shape: the realistic mistake is a TIGER tag in the
        # UD column, and `NN` is shaped exactly like `NOUN` (#253).
        refusal = syntax_validate.validate_upos(to_val)
        if refusal is not None:
            _refuse(refusal, HTTPStatus.BAD_REQUEST)
        return target.upos

    refusal = syntax_validate.validate_deprel(to_val)
    if refusal is not None:
        _refuse(refusal, HTTPStatus.BAD_REQUEST)
    return target.deprel


# NOT `@with_corpus_lock`, for the same reason as `_handle_chunk_syntax`: a
# correction to a chunk nobody has opened parses it first, and holding the
# lock across that parse is exactly the stall #340 measured. The lock is taken
# below instead, around the read-validate-append block, which still has to be
# atomic — two corrections to one token must not interleave between
# `materialise` and `append_correction`.
@map_domain_errors
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

    # Outside the lock: may parse.
    tokens = _load_or_parse_or_400(deps, chunk_id)

    with deps.corpus_lock:
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

        from_val = _check_and_prior_value(
            current, kind=kind, to_val=to_val, sent_ord=sent_ord, tok_id=tok_id, target=target
        )

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
