"""Term glossary read queries."""

from __future__ import annotations

import sqlite3
from typing import Any

from .errors import NotFoundError
from .reader.window import (
    empty_window_response,
    fetch_chunk_ids_in_window,
    parse_window_params,
)


def term_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "source_form": row["source_form"],
        "source_language": row["source_language"],
        "transliteration": row["transliteration"],
        "lemma": row["lemma"],
        "short_gloss": row["short_gloss"],
        "long_description": row["long_description"],
    }


def term_by_id(conn: sqlite3.Connection, term_id: int) -> dict[str, Any]:
    """Full term record plus per-translator default renderings and
    per-edition occurrence counts. The renderings list carries the
    `translator` name and target `language` so the UI can group by
    translator without an extra round trip."""

    term = conn.execute("SELECT * FROM terms WHERE id = ?", (term_id,)).fetchone()
    if term is None:
        raise NotFoundError("unknown term id")
    renderings = conn.execute(
        "SELECT r.id, r.translation_id, r.default_rendering, "
        "       r.translator_note, "
        "       tr.translator_name, tr.year, tr.language, "
        "       w.title AS work_title "
        "FROM term_renderings r "
        "JOIN translations tr ON tr.id = r.translation_id "
        "JOIN works w ON w.id = tr.work_id "
        "WHERE r.term_id = ? "
        "ORDER BY tr.language, tr.translator_name, tr.year",
        (term_id,),
    ).fetchall()
    edition_counts = conn.execute(
        "SELECT e.id AS edition_id, e.name, e.language, e.is_canonical, "
        "       w.title AS work_title, COUNT(o.id) AS occurrences "
        "FROM term_occurrences o "
        "JOIN editions e ON e.id = o.edition_id "
        "JOIN works w ON w.id = e.work_id "
        "WHERE o.term_id = ? "
        "GROUP BY e.id "
        "ORDER BY occurrences DESC",
        (term_id,),
    ).fetchall()
    related = conn.execute(
        "SELECT rel.related_term_id AS id, rel.relation_kind, rel.notes, "
        "       t.source_form, t.source_language, t.short_gloss "
        "FROM term_relations rel "
        "JOIN terms t ON t.id = rel.related_term_id "
        "WHERE rel.term_id = ?",
        (term_id,),
    ).fetchall()
    out = term_to_dict(term)
    out["renderings"] = [dict(r) for r in renderings]
    out["occurrences_by_edition"] = [dict(r) for r in edition_counts]
    out["related"] = [dict(r) for r in related]
    return out


def work_occurrence_map(
    conn: sqlite3.Connection,
    work_id: int,
    query: dict[str, str],
) -> dict[str, Any]:
    """All term occurrences for one work + language, grouped by
    source_chunk_id and optionally windowed by chunk-ord. Powers the
    Reader's dotted-underline markers: one round trip pre-paints every
    visible page, regardless of how many terms are in the work.

    Query params:

    - ``lang`` (default ``grc``) — language of the chunks to scope to.
      Required because the reader window is per-language.
    - ``from`` / ``limit`` — same shape as
      :func:`_handle_work_range` so callers can fetch occurrences for
      exactly the chunks they just rendered. Both optional; default to
      ``from=0`` and ``limit=200``.

    The payload is intentionally minimal (term_id, source_form,
    short_gloss, span). The full term card is fetched on demand from
    ``/api/terms/:id`` when the user clicks a marked word.
    """

    window = parse_window_params(query)
    chunk_ids = fetch_chunk_ids_in_window(
        conn,
        work_id,
        window.lang,
        window.from_ord,
        window.limit,
    )
    if not chunk_ids:
        return empty_window_response(work_id, window)
    placeholders = ",".join("?" * len(chunk_ids))
    rows = conn.execute(
        f"SELECT o.id, o.term_id, o.source_chunk_id, "
        f"       o.source_start, o.source_end, "
        f"       o.source_form_snapshot, t.source_form, t.short_gloss, "
        f"       t.transliteration "
        f"FROM term_occurrences o "
        f"JOIN terms t ON t.id = o.term_id "
        f"WHERE o.source_chunk_id IN ({placeholders}) "
        f"ORDER BY o.source_chunk_id, o.source_start",
        chunk_ids,
    ).fetchall()
    by_chunk: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_chunk.setdefault(r["source_chunk_id"], []).append(
            {
                "id": r["id"],
                "term_id": r["term_id"],
                "source_start": r["source_start"],
                "source_end": r["source_end"],
                "source_form": r["source_form_snapshot"],
                "lemma": r["source_form"],
                "transliteration": r["transliteration"],
                "short_gloss": r["short_gloss"],
            }
        )
    return {
        "work_id": work_id,
        "lang": window.lang,
        "from": window.from_ord,
        "limit": window.limit,
        "by_chunk": by_chunk,
    }
