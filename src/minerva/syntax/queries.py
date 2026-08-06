"""Storage and replay for dependency-syntax trees.

The machine parse in ``chunk_syntax`` is immutable. Corrections are an
append-only log in ``chunk_syntax_corrections``. The tree anyone actually sees
is :func:`materialise` replaying the second over the first.

Keeping the parse immutable is what makes "how much of this can I trust"
answerable: every token knows whether a human touched it, so the UI can colour
by epistemic status, and "what did the parser originally say" survives forever.
"""

from __future__ import annotations

import dataclasses
import sqlite3
import time
from collections.abc import Iterable, Sequence

# Only these two columns are correctable. Widening this means widening the
# CHECK constraint in migration 0024 too.
CORRECTABLE = ("head", "deprel")

#: The only language the dependency parser handles. `syntax/parse.py` builds a
#: Stanza German pipeline (`_LANG = "de"`); there is no per-language dispatch,
#: and adding one is explicitly out of scope in the annotation plan.
SUPPORTED_LANG = "deu"


class UnsupportedSyntaxLanguage(Exception):
    """Raised when a chunk is not in a language the parser handles.

    Its whole purpose is to stop the German model from parsing Greek or
    Latin and `save_parse` caching the output as authoritative (#231). The
    caller decides how to surface it; the HTTP layer answers 400.
    """

    def __init__(self, chunk_id: str, lang: str) -> None:
        super().__init__(
            f"syntax parsing is {SUPPORTED_LANG}-only; chunk {chunk_id!r} is {lang!r}"
        )
        self.chunk_id = chunk_id
        self.lang = lang


@dataclasses.dataclass(frozen=True)
class SyntaxToken:
    """One syntactic word. Mirrors the CoNLL-U columns, plus provenance."""

    sent_ord: int
    tok_id: int
    form: str
    lemma: str | None
    upos: str | None
    xpos: str | None
    feats: str | None
    misc: str | None
    # 0 attaches to the sentence root; None is CoNLL-U's `_`, unparsed.
    head: int | None
    deprel: str | None
    surface_start: int
    surface_end: int
    #: True once a correction has touched this token. Never persisted on the
    #: parse row — it is derived at replay time from the correction log.
    corrected: bool = False


@dataclasses.dataclass(frozen=True)
class Correction:
    id: int
    sent_ord: int
    tok_id: int
    kind: str
    from_val: str | None
    to_val: str


def materialise(
    tokens: Sequence[SyntaxToken],
    corrections: Iterable[Correction],
) -> list[SyntaxToken]:
    """Replay *corrections* over the pristine *tokens*.

    Pure: the input sequence is never mutated, because it is the audit trail
    and a caller may well reuse it.

    Corrections are applied in ``id`` order regardless of the order they
    arrive in — the log is append-only, so id order is edit order, and a later
    edit to the same token supersedes an earlier one. A correction addressing
    a token that is not present is ignored rather than raising: the log has no
    foreign key precisely so it outlives a re-ingest, and a patch that no
    longer lines up must be inert rather than fatal.
    """

    index = {(t.sent_ord, t.tok_id): i for i, t in enumerate(tokens)}
    out = list(tokens)

    for c in sorted(corrections, key=lambda c: c.id):
        i = index.get((c.sent_ord, c.tok_id))
        if i is None:
            continue
        if c.kind == "head":
            out[i] = dataclasses.replace(out[i], head=int(c.to_val), corrected=True)
        elif c.kind == "deprel":
            out[i] = dataclasses.replace(out[i], deprel=c.to_val, corrected=True)

    return out


# ---------- the machine parse ----------

_PARSE_COLUMNS = (
    "sent_ord, tok_id, form, lemma, upos, xpos, feats, misc, "
    "head, deprel, surface_start, surface_end"
)


def load_parse(conn: sqlite3.Connection, chunk_id: str) -> list[SyntaxToken] | None:
    """The stored parse for *chunk_id*, or None when it has never been parsed.

    The None/[] distinction matters: a chunk that genuinely parses to no
    tokens would otherwise look uncached forever and be re-parsed on every
    open. ``chunk_syntax_state`` is the record of "we tried".
    """

    parsed = conn.execute(
        "SELECT 1 FROM chunk_syntax_state WHERE chunk_id = ?", (chunk_id,)
    ).fetchone()
    if parsed is None:
        return None

    rows = conn.execute(
        f"SELECT {_PARSE_COLUMNS} FROM chunk_syntax WHERE chunk_id = ? ORDER BY sent_ord, tok_id",
        (chunk_id,),
    ).fetchall()
    return [SyntaxToken(*row) for row in rows]


def save_parse(
    conn: sqlite3.Connection,
    chunk_id: str,
    tokens: Sequence[SyntaxToken],
    *,
    parser: str,
) -> None:
    """Replace *chunk_id*'s parse. Corrections are untouched — they are
    addressed by (sent_ord, tok_id) and replayed over whatever is current."""

    conn.execute("DELETE FROM chunk_syntax WHERE chunk_id = ?", (chunk_id,))
    conn.executemany(
        f"INSERT INTO chunk_syntax(chunk_id, {_PARSE_COLUMNS}) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                chunk_id,
                t.sent_ord,
                t.tok_id,
                t.form,
                t.lemma,
                t.upos,
                t.xpos,
                t.feats,
                t.misc,
                t.head,
                t.deprel,
                t.surface_start,
                t.surface_end,
            )
            for t in tokens
        ],
    )
    conn.execute(
        "INSERT INTO chunk_syntax_state(chunk_id, parser, parsed_at) VALUES (?, ?, ?) "
        "ON CONFLICT(chunk_id) DO UPDATE SET parser = excluded.parser, "
        "parsed_at = excluded.parsed_at",
        (chunk_id, parser, time.time()),
    )
    conn.commit()


# ---------- the correction log ----------


def load_corrections(conn: sqlite3.Connection, chunk_id: str) -> list[Correction]:
    rows = conn.execute(
        "SELECT id, sent_ord, tok_id, kind, from_val, to_val "
        "FROM chunk_syntax_corrections WHERE chunk_id = ? ORDER BY id",
        (chunk_id,),
    ).fetchall()
    return [Correction(*row) for row in rows]


def append_correction(
    conn: sqlite3.Connection,
    chunk_id: str,
    *,
    sent_ord: int,
    tok_id: int,
    kind: str,
    from_val: str | None,
    to_val: str,
) -> int:
    """Record one edit. Returns its id, which is also its replay position."""

    if kind not in CORRECTABLE:
        raise ValueError(f"kind must be one of {CORRECTABLE}, got {kind!r}")

    cur = conn.execute(
        "INSERT INTO chunk_syntax_corrections"
        "(chunk_id, sent_ord, tok_id, kind, from_val, to_val, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (chunk_id, sent_ord, tok_id, kind, from_val, to_val, time.time()),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def load_or_parse(conn: sqlite3.Connection, chunk_id: str) -> list[SyntaxToken] | None:
    """The parse for *chunk_id*, parsing and caching it on first request.

    Returns None when no such chunk exists — distinct from ``[]``, which is a
    chunk that genuinely parses to nothing.

    This is the "parse on demand" half of the design: the corpus fills in
    where someone actually reads, rather than paying an hour up front to
    produce trees for text nobody has opened. The first call for a chunk costs
    a pipeline load (~4s, once per process) plus the parse (~0.15s for a
    paragraph); every later call is a read.

    Raises :class:`UnsupportedSyntaxLanguage` for a chunk the parser cannot
    handle — checked before the cache read and before Stanza is imported.
    """

    # Language first, before the cache read and before the Stanza import.
    #
    # Before the cache, because a cached tree for a non-German chunk could
    # only have come from the German model and should not be served either.
    # Before the import, because CI has no `[lemma]` extra — a guard placed
    # after it would pass locally and fail there.
    row = conn.execute(
        "SELECT text, lang FROM chunks WHERE chunk_id = ?", (chunk_id,)
    ).fetchone()
    if row is None:
        return None
    lang = str(row["lang"])
    if lang != SUPPORTED_LANG:
        raise UnsupportedSyntaxLanguage(chunk_id, lang)

    cached = load_parse(conn, chunk_id)
    if cached is not None:
        return cached

    # Imported here, not at module scope: `stanza` is in the optional
    # `[lemma]` extra, and every other function in this module must keep
    # working without it.
    from .parse import parse_text, parser_id

    tokens = parse_text(str(row["text"]))
    save_parse(conn, chunk_id, tokens, parser=parser_id())
    return tokens


def delete_correction(conn: sqlite3.Connection, correction_id: int) -> bool:
    """Drop one correction — the undo. Returns whether a row was removed."""

    cur = conn.execute("DELETE FROM chunk_syntax_corrections WHERE id = ?", (correction_id,))
    conn.commit()
    return cur.rowcount > 0
