"""Curator PATCH write path for cross-references."""

from __future__ import annotations

import sqlite3
from typing import Any

from ..errors import BadRequestError, NotFoundError
from .constants import CURATOR_STATUS_VALUES
from .row_utils import xref_row_to_dict


def parse_reference_update_body(body: dict[str, Any]) -> tuple[str, str | None, bool]:
    """Validate a PATCH body and return ``(status, note, update_note)``."""

    status = body.get("curator_status")
    if status is None:
        raise BadRequestError("missing 'curator_status'")
    if status not in CURATOR_STATUS_VALUES:
        raise BadRequestError(
            f"'curator_status' must be one of {CURATOR_STATUS_VALUES}",
        )

    note: str | None
    if "curator_note" in body:
        raw_note = body["curator_note"]
        if raw_note is not None and not isinstance(raw_note, str):
            raise BadRequestError("'curator_note' must be a string or null")
        if isinstance(raw_note, str):
            trimmed = raw_note.strip()
            note = trimmed if trimmed else None
        else:
            note = None
        update_note = True
    else:
        note = None
        update_note = False
    return status, note, update_note


def update_reference(
    conn: sqlite3.Connection,
    reference_id: int,
    *,
    status: str,
    note: str | None,
    update_note: bool,
) -> dict[str, Any]:
    """Update ``curator_status`` (and optionally ``curator_note``) on one row.

    Returns the updated reference as a JSON dict. Raises ``NotFoundError``
    when ``reference_id`` is unknown.
    """

    before = conn.execute(
        "SELECT id FROM cross_references WHERE id = ?", (reference_id,)
    ).fetchone()
    if before is None:
        raise NotFoundError(f"reference {reference_id} not found")
    if update_note:
        conn.execute(
            "UPDATE cross_references SET curator_status = ?, curator_note = ?, "
            "  curated_by = 'human', curated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
            "WHERE id = ?",
            (status, note, reference_id),
        )
    else:
        conn.execute(
            "UPDATE cross_references SET curator_status = ?, "
            "  curated_by = 'human', curated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
            "WHERE id = ?",
            (status, reference_id),
        )
    conn.commit()
    row = conn.execute(
        "SELECT xr.*, rt.canonical_author, rt.canonical_work, "
        "       rt.in_corpus_work_id "
        "FROM cross_references xr "
        "JOIN reference_targets rt ON rt.id = xr.target_id "
        "WHERE xr.id = ?",
        (reference_id,),
    ).fetchone()
    return xref_row_to_dict(row)
