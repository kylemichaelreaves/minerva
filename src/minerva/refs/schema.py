"""CRUD helpers for ``reference_targets`` and ``cross_references``.

This module is the only place that should write to ``cross_references``
in production code. The shadow address (edition_id, sort_key,
source_form_snapshot, instance_index) makes inserts survive a chunks
re-ingest, but only if every insert assigns ``instance_index``
correctly — the helpers below enforce that.

The insert pattern mirrors ``terms.insert_occurrence`` (see
``terms.py``); cross-references reuse the same shadow-address shape,
so the retry-on-UNIQUE-conflict loop is the same.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from typing import Any

from ..sqlite_util import insert_with_shadow_retry
from .constants import CURATED_BY_VALUES, SOURCE_AUTHOR

# Same budget as terms.py's _MAX_INSERT_RETRIES — bounded high enough
# for plausible curator-collision bursts, low enough that a programming
# bug (e.g. missing row preventing progress) fails fast.
_MAX_INSERT_RETRIES = 8


class RefsError(Exception):
    """Raised when a cross-references write can't be completed."""


# ──────────────────────────────────────────────────────────────────
# Target resolution
# ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReferenceTarget:
    """Read-side shape of one ``reference_targets`` row."""

    id: int
    canonical_author: str
    canonical_work: str
    citation_system: str | None
    in_corpus_work_id: int | None
    notes: str | None


def find_target_by_author_work(
    conn: sqlite3.Connection,
    *,
    canonical_author: str,
    canonical_work: str,
) -> ReferenceTarget | None:
    """Look up a target by its (author, work) UNIQUE key. Returns None
    if not present — caller decides whether to create one via
    :func:`ensure_target`."""

    row = conn.execute(
        "SELECT id, canonical_author, canonical_work, citation_system, "
        "       in_corpus_work_id, notes "
        "FROM reference_targets "
        "WHERE canonical_author = ? AND canonical_work = ?",
        (canonical_author, canonical_work),
    ).fetchone()
    if row is None:
        return None
    return ReferenceTarget(
        id=int(row[0]),
        canonical_author=str(row[1]),
        canonical_work=str(row[2]),
        citation_system=row[3],
        in_corpus_work_id=row[4],
        notes=row[5],
    )


def find_target_by_id(conn: sqlite3.Connection, target_id: int) -> ReferenceTarget | None:
    row = conn.execute(
        "SELECT id, canonical_author, canonical_work, citation_system, "
        "       in_corpus_work_id, notes "
        "FROM reference_targets WHERE id = ?",
        (target_id,),
    ).fetchone()
    if row is None:
        return None
    return ReferenceTarget(
        id=int(row[0]),
        canonical_author=str(row[1]),
        canonical_work=str(row[2]),
        citation_system=row[3],
        in_corpus_work_id=row[4],
        notes=row[5],
    )


def _title_key(value: str) -> str:
    """Fold a work title to the key two spellings of the same title
    share: accents decomposed and dropped, case flattened, everything
    that is not a letter or digit removed.

    Deliberately blunt. It exists to absorb the drift that is on the
    record — ``'De republica'`` against ``'De Re Publica'``, which
    differs in case *and* word division, and ``'Tusculanae
    disputationes'`` against ``'Tusculanae Disputationes'``, which
    differs by one letter — not to guess at titles that are genuinely
    different. Anything blunt enough to fold two distinct works
    together is caught by the ambiguity check in
    :func:`find_work_by_title_key`, which declines rather than picks.
    """

    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", stripped.lower())


def find_work_by_title_key(
    conn: sqlite3.Connection,
    *,
    author: str,
    title: str,
) -> tuple[int, str] | None:
    """``(works.id, citation_system)`` for the one work of ``author``
    whose title folds to the same key as ``title``, or None.

    Scoped to a single author, so the scan is over that author's works
    rather than the whole table, and a title cannot reach across
    authors. Returns None when more than one work matches: picking
    either would be arbitrary, and a NULL ``in_corpus_work_id`` is
    visibly unresolved where a wrong one reads as resolved — the same
    trade ``verify_quoted_references`` makes for a phrase it cannot
    locate (#269).
    """

    wanted = _title_key(title)
    if not wanted:
        return None
    matches = [
        (int(row[0]), row[1])
        for row in conn.execute(
            "SELECT id, citation_system, title FROM works WHERE author = ?",
            (author,),
        ).fetchall()
        if _title_key(str(row[2])) == wanted
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _find_work_by_alias(
    conn: sqlite3.Connection, *, author: str, title: str
) -> tuple[int, str] | None:
    """The one in-corpus work of ``author`` that answers to ``title`` as an
    alias (#523), or None — including when several do: "Das Kapital"
    names all three Bände, and a guess would read as resolved.

    Reads the code-owned natural keys in ``authors/work_aliases.ALIASES``,
    not the ``work_aliases`` table: the index rebinds targets before it
    re-syncs that table, so the table can still hold pre-reset work ids
    at the moment this runs (#800).
    """

    from ..authors.work_aliases import ALIASES

    wanted = _title_key(title)
    if not wanted:
        return None
    titles = {
        work_title
        for (alias_author, work_title), names in ALIASES.items()
        if alias_author == author and any(_title_key(n) == wanted for n in names)
    }
    matches = [
        (int(row[0]), row[1])
        for t in sorted(titles)
        for row in conn.execute(
            "SELECT id, citation_system FROM works WHERE author = ? AND title = ?", (author, t)
        )
    ]
    return matches[0] if len(matches) == 1 else None


def resolve_target_work(
    conn: sqlite3.Connection, *, author: str, work: str
) -> tuple[int, str] | None:
    """``(works.id, citation_system)`` a target's ``(author, work)`` names,
    or None. Exact title, then folded (#493/#524), then a one-to-one
    alias (#523); each step declines on ambiguity rather than picking.

    The single resolver for ``reference_targets.in_corpus_work_id``:
    :func:`ensure_target` links with it, and the index's rebind and its
    integrity assert (``store/chunks.py``) re-resolve with it. They used
    to disagree — the rebind was exact-only, so every index run re-NULLed
    the folded links ``ensure_target`` had made (#800).
    """

    if work == "*":
        return None
    exact = conn.execute(
        "SELECT id, citation_system FROM works WHERE author = ? AND title = ?",
        (author, work),
    ).fetchone()
    if exact is not None:
        return int(exact[0]), exact[1]
    return find_work_by_title_key(conn, author=author, title=work) or _find_work_by_alias(
        conn, author=author, title=work
    )


def ensure_target(
    conn: sqlite3.Connection,
    *,
    canonical_author: str,
    canonical_work: str,
    citation_system: str | None = None,
    notes: str | None = None,
) -> ReferenceTarget:
    """Look up or create a target. If the (author, work) pair already
    exists, return that row regardless of the other inputs (do not
    update — curator can edit via the CLI explicitly).

    If the named work matches an in-corpus ``works`` row (by
    :func:`resolve_target_work`: exact, folded, then a one-to-one
    alias), the new ``reference_targets`` row is created with
    ``in_corpus_work_id`` set so the reader's "Open in reader →"
    affordance can resolve."""

    existing = find_target_by_author_work(
        conn,
        canonical_author=canonical_author,
        canonical_work=canonical_work,
    )
    if existing is not None:
        return existing

    # Auto-link to a works row if one matches. A miss is silent — the
    # target is simply created out-of-corpus and nothing says why (#493)
    # — so the resolver tries folded and alias spellings too.
    work_row = resolve_target_work(conn, author=canonical_author, work=canonical_work)
    in_corpus_work_id: int | None = None
    if work_row is not None:
        in_corpus_work_id = work_row[0]
        # If the caller didn't specify a citation_system, inherit from
        # the works row.
        if citation_system is None:
            citation_system = work_row[1]

    cur = conn.execute(
        "INSERT INTO reference_targets "
        "(canonical_author, canonical_work, citation_system, in_corpus_work_id, notes) "
        "VALUES (?, ?, ?, ?, ?)",
        (canonical_author, canonical_work, citation_system, in_corpus_work_id, notes),
    )
    new_id = int(cur.lastrowid or 0)
    return ReferenceTarget(
        id=new_id,
        canonical_author=canonical_author,
        canonical_work=canonical_work,
        citation_system=citation_system,
        in_corpus_work_id=in_corpus_work_id,
        notes=notes,
    )


# ──────────────────────────────────────────────────────────────────
# Cross-reference inserts (shadow-address-safe)
# ──────────────────────────────────────────────────────────────────


def next_instance_index(
    conn: sqlite3.Connection,
    *,
    source_edition_id: int | None,
    source_sort_key: str | None,
    source_form_snapshot: str | None,
) -> int:
    """Next available ``source_instance_index`` for a fresh row at the
    given shadow-address prefix. Returns 1 when no prior row exists
    with the same (edition_id, sort_key, source_form_snapshot).

    Mirrors :func:`terms.next_instance_index`. Caller should
    immediately INSERT using this value and retry on UNIQUE conflict
    (the convention in :func:`insert_cross_reference`)."""

    row = conn.execute(
        "SELECT COALESCE(MAX(source_instance_index), 0) + 1 "
        "FROM cross_references "
        "WHERE source_edition_id IS ? "
        "  AND source_sort_key IS ? "
        "  AND source_form_snapshot IS ?",
        (source_edition_id, source_sort_key, source_form_snapshot),
    ).fetchone()
    return int(row[0])


def _resolve_source_edition_translation(
    conn: sqlite3.Connection, chunk_id: str
) -> tuple[int | None, int | None]:
    """Read (edition_id, translation_id) for a chunk_id. Exactly one
    of the two is non-NULL (enforced by the chunks schema)."""

    row = conn.execute(
        "SELECT edition_id, translation_id FROM chunks WHERE chunk_id = ?",
        (chunk_id,),
    ).fetchone()
    if row is None:
        raise RefsError(f"unknown source_chunk_id {chunk_id!r}")
    return (row[0], row[1])


def insert_cross_reference(
    conn: sqlite3.Connection,
    *,
    source_chunk_id: str,
    target_id: int,
    reference_type: str,
    source_span_start: int | None = None,
    source_span_end: int | None = None,
    source_form_snapshot: str | None = None,
    quoted_phrase: str | None = None,
    target_chunk_id: str | None = None,
    target_locator: str | None = None,
    target_locator_payload: dict[str, Any] | None = None,
    target_sort_key: str | None = None,
    confidence: float = 1.0,
    source_method: str = "manual",
    curator_status: str = "manual",
    curator_note: str | None = None,
    source_sort_key: str | None = None,
) -> int:
    """Insert one cross-reference row and return its new ``id``.

    Computes ``source_instance_index`` from the prior state of the
    table, inserts, retries on the shadow-address UNIQUE conflict up
    to ``_MAX_INSERT_RETRIES`` times. Resolves (edition_id,
    translation_id) from the source_chunk_id via the chunks table so
    callers don't have to pass them.

    ``target_locator_payload`` is serialized to JSON on the way in.
    The caller is responsible for matching its shape to the target's
    ``citation_system``; the schema doesn't enforce payload structure.
    """

    src_edition_id, src_translation_id = _resolve_source_edition_translation(conn, source_chunk_id)

    payload_json: str | None = None
    if target_locator_payload is not None:
        payload_json = json.dumps(target_locator_payload, ensure_ascii=False)

    def _do_insert(idx: int) -> int:
        cur = conn.execute(
            "INSERT INTO cross_references ("
            "  source_chunk_id, source_span_start, source_span_end, "
            "  source_form_snapshot, quoted_phrase, "
            "  target_id, target_chunk_id, target_locator, "
            "  target_locator_payload, target_sort_key, "
            "  reference_type, confidence, source_method, "
            "  curator_status, curator_note, "
            "  source_edition_id, source_translation_id, "
            "  source_sort_key, source_instance_index"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_chunk_id,
                source_span_start,
                source_span_end,
                source_form_snapshot,
                quoted_phrase,
                target_id,
                target_chunk_id,
                target_locator,
                payload_json,
                target_sort_key,
                reference_type,
                confidence,
                source_method,
                curator_status,
                curator_note,
                src_edition_id,
                src_translation_id,
                source_sort_key,
                idx,
            ),
        )
        return int(cur.lastrowid or 0)

    return insert_with_shadow_retry(
        max_retries=_MAX_INSERT_RETRIES,
        next_index=lambda: next_instance_index(
            conn,
            source_edition_id=src_edition_id,
            source_sort_key=source_sort_key,
            source_form_snapshot=source_form_snapshot,
        ),
        do_insert=_do_insert,
        unique_table_substring="cross_references",
        exhausted_error=lambda last: RefsError(
            f"insert_cross_reference: exhausted {_MAX_INSERT_RETRIES} retries on the "
            f"shadow UNIQUE constraint (source_edition_id={src_edition_id}, "
            f"source_sort_key={source_sort_key!r}, "
            f"source_form_snapshot={source_form_snapshot!r}); "
            f"last error: {last}"
        ),
    )


# ──────────────────────────────────────────────────────────────────
# Read-side helpers (used by CLI list + API endpoints)
# ──────────────────────────────────────────────────────────────────


def outgoing_for_chunk(
    conn: sqlite3.Connection,
    source_chunk_id: str,
    *,
    min_confidence: float = 0.0,
    statuses: tuple[str, ...] = ("approved", "manual", "auto"),
) -> list[sqlite3.Row]:
    """References whose source is ``source_chunk_id``. JOINs against
    ``reference_targets`` so callers see the canonical author/work in
    one round trip. Filters on confidence threshold + curator status
    (default: everything except 'rejected')."""

    placeholders = ",".join("?" * len(statuses))
    return list(
        conn.execute(
            f"SELECT xr.*, "
            f"       rt.canonical_author, rt.canonical_work, "
            f"       rt.in_corpus_work_id "
            f"FROM cross_references xr "
            f"JOIN reference_targets rt ON rt.id = xr.target_id "
            f"WHERE xr.source_chunk_id = ? "
            f"  AND xr.confidence >= ? "
            f"  AND xr.curator_status IN ({placeholders}) "
            f"ORDER BY xr.confidence DESC, xr.id",
            (source_chunk_id, min_confidence, *statuses),
        )
    )


def incoming_for_chunk(
    conn: sqlite3.Connection,
    target_chunk_id: str,
    *,
    min_confidence: float = 0.0,
    statuses: tuple[str, ...] = ("approved", "manual", "auto"),
) -> list[sqlite3.Row]:
    """References whose target is ``target_chunk_id``. Mirrors
    :func:`outgoing_for_chunk` for the symmetric direction."""

    placeholders = ",".join("?" * len(statuses))
    return list(
        conn.execute(
            f"SELECT xr.*, "
            f"       rt.canonical_author, rt.canonical_work, "
            f"       rt.in_corpus_work_id "
            f"FROM cross_references xr "
            f"JOIN reference_targets rt ON rt.id = xr.target_id "
            f"WHERE xr.target_chunk_id = ? "
            f"  AND xr.confidence >= ? "
            f"  AND xr.curator_status IN ({placeholders}) "
            f"ORDER BY xr.confidence DESC, xr.id",
            (target_chunk_id, min_confidence, *statuses),
        )
    )


def list_references(
    conn: sqlite3.Connection,
    *,
    source_author: str | None = None,
    target_author: str | None = None,
    target_work: str | None = None,
    curator_status: str | None = None,
    curated_by: str | None = None,
    limit: int = 100,
) -> list[sqlite3.Row]:
    """Filtered listing for the curator CLI. JOINs through
    ``editions``/``translations`` + ``works`` to surface the source
    author/work alongside the target.

    ``curated_by`` is one of :data:`constants.CURATED_BY_VALUES`, or
    ``"none"`` for rows with no recorded verdict author (#720)."""

    clauses: list[str] = []
    args: list[Any] = []
    if source_author is not None:
        clauses.append(f"{SOURCE_AUTHOR} = ?")
        args.append(source_author)
    if target_author is not None:
        clauses.append("rt.canonical_author = ?")
        args.append(target_author)
    if target_work is not None:
        clauses.append("rt.canonical_work = ?")
        args.append(target_work)
    if curator_status is not None:
        clauses.append("xr.curator_status = ?")
        args.append(curator_status)
    if curated_by == "none":
        clauses.append("xr.curated_by IS NULL")
    elif curated_by is not None:
        if curated_by not in CURATED_BY_VALUES:
            raise ValueError(f"curated_by must be one of {CURATED_BY_VALUES} or 'none'")
        clauses.append("xr.curated_by = ?")
        args.append(curated_by)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    sql = (
        f"SELECT xr.id, xr.source_chunk_id, "
        f"       {SOURCE_AUTHOR} AS source_author, src_work.title AS source_work, "
        f"       c.section AS source_section, "
        f"       rt.canonical_author AS target_author, "
        f"       rt.canonical_work AS target_work, "
        f"       xr.target_locator, "
        f"       xr.reference_type, xr.confidence, xr.source_method, "
        f"       xr.curator_status, xr.curated_by, xr.curated_at, xr.quoted_phrase "
        f"FROM cross_references xr "
        f"JOIN reference_targets rt ON rt.id = xr.target_id "
        f"JOIN chunks c ON c.chunk_id = xr.source_chunk_id "
        f"LEFT JOIN editions e ON e.id = c.edition_id "
        f"LEFT JOIN translations t ON t.id = c.translation_id "
        f"LEFT JOIN works src_work ON src_work.id = COALESCE(e.work_id, t.work_id) "
        f"{where} "
        f"ORDER BY xr.id "
        f"LIMIT ?"
    )
    args.append(limit)
    return list(conn.execute(sql, args))
