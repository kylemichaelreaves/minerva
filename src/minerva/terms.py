"""Term-glossary data access — CRUD helpers around the tables created
by ``migrations/0001_term_glossary.sql``.

This module is the only place that should write to ``term_occurrences``
in production code. The shadow-address scheme on that table
(``edition_id``, ``location_sort_key``, ``source_form_snapshot``,
``instance_index``) makes occurrences recoverable after a chunks
re-ingest, but only if every insert assigns ``instance_index``
correctly. ``next_instance_index`` plus ``insert_occurrence`` enforce
that — callers must not insert directly with raw SQL.

Why a dedicated helper for instance_index
-----------------------------------------
The shadow address requires that the n-th occurrence of a source form
at a given locator gets ``instance_index = n``. Computing n is a
``SELECT MAX(instance_index) + 1 FROM term_occurrences WHERE …``
lookup, and the race window between that read and the corresponding
INSERT is closed by the UNIQUE constraint
``(edition_id, location_sort_key, source_form_snapshot,
instance_index)``. Two curators racing on the same site both compute
``n`` from the same prior state; one INSERT wins, the other hits the
UNIQUE and retries with the incremented value.

``insert_occurrence`` handles the retry loop. Retry budget is bounded
because in practice contention is at most "two curators tagging the
same passage at the same moment" — a near-impossible event for a
single-curator workflow but cheap to handle robustly.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .sqlite_util import insert_with_shadow_retry

# Number of retries before we give up and surface the IntegrityError.
# Higher than any plausible concurrent-curator burst; low enough that
# a genuine programming bug (e.g., missing rows preventing progress)
# fails fast.
_MAX_INSERT_RETRIES = 8


class TermsError(Exception):
    """Raised when a term-glossary write can't be completed."""


def next_instance_index(
    conn: sqlite3.Connection,
    *,
    edition_id: int,
    location_sort_key: str,
    source_form_snapshot: str,
) -> int:
    """Return the next available ``instance_index`` for a fresh
    occurrence at this shadow-address prefix.

    Returns 1 when no prior occurrence exists with the same
    ``(edition_id, location_sort_key, source_form_snapshot)``. The
    caller is expected to immediately INSERT using this value; if the
    UNIQUE constraint fires (because a parallel transaction beat us
    to it) the caller should re-call this helper and retry.
    Prefer ``insert_occurrence`` over driving the loop by hand.
    """

    row = conn.execute(
        "SELECT COALESCE(MAX(instance_index), 0) + 1 "
        "FROM term_occurrences "
        "WHERE edition_id = ? "
        "  AND location_sort_key = ? "
        "  AND source_form_snapshot = ?",
        (edition_id, location_sort_key, source_form_snapshot),
    ).fetchone()
    return int(row[0])


def insert_occurrence(
    conn: sqlite3.Connection,
    *,
    term_id: int,
    edition_id: int,
    source_chunk_id: str,
    source_start: int,
    source_end: int,
    context_snippet: str,
    location_kind: str,
    location_payload: dict[str, Any],
    location_sort_key: str,
    source_form_snapshot: str,
    tradition: str | None = None,
) -> int:
    """Insert a single term occurrence and return its new ``id``.

    Computes ``instance_index`` from the prior state of the table,
    inserts, and on a UNIQUE-constraint conflict (a parallel writer
    beat us) recomputes and retries up to ``_MAX_INSERT_RETRIES`` times.

    ``location_payload`` is serialized to JSON on the way in. The
    caller is responsible for ensuring its shape matches
    ``location_kind`` — schema doesn't enforce payload structure
    (see the schema-design notes).

    ``work_id`` is derived from the edition rather than passed
    separately, because the schema requires the two to agree
    (``term_occurrences.work_id`` is denormalized from
    ``editions.work_id``). One lookup at insert time beats the
    alternative — letting callers pass it and risking divergence.
    """

    work_id_row = conn.execute(
        "SELECT work_id FROM editions WHERE id = ?", (edition_id,)
    ).fetchone()
    if work_id_row is None:
        raise TermsError(f"unknown edition_id {edition_id}")
    work_id = int(work_id_row[0])

    payload_json = json.dumps(location_payload, ensure_ascii=False)

    def _do_insert(idx: int) -> int:
        cur = conn.execute(
            "INSERT INTO term_occurrences ("
            "  term_id, edition_id, work_id, source_chunk_id, "
            "  source_start, source_end, context_snippet, "
            "  location_kind, location_payload, location_sort_key, "
            "  tradition, source_form_snapshot, instance_index"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                term_id,
                edition_id,
                work_id,
                source_chunk_id,
                source_start,
                source_end,
                context_snippet,
                location_kind,
                payload_json,
                location_sort_key,
                tradition,
                source_form_snapshot,
                idx,
            ),
        )
        return int(cur.lastrowid)

    return insert_with_shadow_retry(
        max_retries=_MAX_INSERT_RETRIES,
        next_index=lambda: next_instance_index(
            conn,
            edition_id=edition_id,
            location_sort_key=location_sort_key,
            source_form_snapshot=source_form_snapshot,
        ),
        do_insert=_do_insert,
        unique_table_substring="term_occurrences",
        exhausted_error=lambda last: TermsError(
            f"insert_occurrence: exhausted {_MAX_INSERT_RETRIES} retries on the "
            f"shadow UNIQUE constraint (edition_id={edition_id}, "
            f"location_sort_key={location_sort_key!r}, "
            f"source_form_snapshot={source_form_snapshot!r}); last error: "
            f"{last}"
        ),
    )


def next_rendering_instance_index(
    conn: sqlite3.Connection,
    *,
    translation_id: int,
    source_locator_sort_key: str,
    rendered_form_snapshot: str,
) -> int:
    """Translation-side analog of :func:`next_instance_index`. Returns
    the next available ``instance_index`` for a fresh rendering at
    this shadow-address prefix, so the per-translation chunk relink
    can pick the right physical span on re-ingest."""

    row = conn.execute(
        "SELECT COALESCE(MAX(instance_index), 0) + 1 "
        "FROM occurrence_renderings "
        "WHERE translation_id = ? "
        "  AND source_locator_sort_key = ? "
        "  AND rendered_form_snapshot = ?",
        (translation_id, source_locator_sort_key, rendered_form_snapshot),
    ).fetchone()
    return int(row[0])


def insert_occurrence_rendering(
    conn: sqlite3.Connection,
    *,
    occurrence_id: int,
    translation_id: int,
    translation_chunk_id: str,
    translation_start: int,
    translation_end: int,
    rendered_text: str,
    notes: str | None = None,
) -> int:
    """Insert a per-occurrence translation rendering and return its id.

    The shadow-address columns (``source_locator_sort_key``,
    ``rendered_form_snapshot``, ``instance_index``) are populated
    automatically:

    * ``source_locator_sort_key`` is read from the parent occurrence —
      callers don't supply it because the value must match exactly
      what's already on ``term_occurrences``.
    * ``rendered_form_snapshot`` is set to ``rendered_text`` at insert
      time; the snapshot lives separately so a future edit to
      ``rendered_text`` (typo correction) doesn't break the relink
      address.
    * ``instance_index`` comes from :func:`next_rendering_instance_index`.

    Raises :class:`TermsError` if the parent occurrence doesn't exist
    or if the (occurrence_id, translation_id) UNIQUE already has a
    row — per-occurrence overrides are one-per-pair by design.
    """

    parent = conn.execute(
        "SELECT location_sort_key FROM term_occurrences WHERE id = ?",
        (occurrence_id,),
    ).fetchone()
    if parent is None:
        raise TermsError(f"unknown occurrence_id {occurrence_id}")
    source_locator_sort_key = parent[0]

    idx = next_rendering_instance_index(
        conn,
        translation_id=translation_id,
        source_locator_sort_key=source_locator_sort_key,
        rendered_form_snapshot=rendered_text,
    )
    try:
        cur = conn.execute(
            "INSERT INTO occurrence_renderings ("
            "  occurrence_id, translation_id, translation_chunk_id, "
            "  translation_start, translation_end, rendered_text, notes, "
            "  source_locator_sort_key, rendered_form_snapshot, instance_index"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                occurrence_id,
                translation_id,
                translation_chunk_id,
                translation_start,
                translation_end,
                rendered_text,
                notes,
                source_locator_sort_key,
                rendered_text,
                idx,
            ),
        )
    except sqlite3.IntegrityError as exc:
        msg = str(exc).lower()
        if "occurrence_renderings" in msg and "unique" in msg:
            raise TermsError(
                f"a rendering already exists for occurrence {occurrence_id} in "
                f"translation {translation_id}; update the existing row "
                f"instead of inserting a new one"
            ) from exc
        raise
    return int(cur.lastrowid)
