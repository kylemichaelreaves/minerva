"""Term glossary read queries."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .errors import BadRequestError, NotFoundError
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


def terms_list(conn: sqlite3.Connection,
               query: dict[str, str]) -> dict[str, Any]:
    """List terms with an occurrence count alongside each row. Filters
    accept ``lang`` (exact match on `source_language`) and ``like``
    (case-insensitive substring on `source_form` for fuzzy lookup)."""

    sql = (
        "SELECT t.id, t.source_form, t.source_language, t.transliteration, "
        "       t.lemma, t.short_gloss, t.long_description, "
        "       (SELECT COUNT(*) FROM term_occurrences WHERE term_id = t.id) "
        "         AS occurrences "
        "FROM terms t"
    )
    where: list[str] = []
    params: list[Any] = []
    if query.get("lang"):
        where.append("t.source_language = ?")
        params.append(query["lang"])
    if query.get("like"):
        where.append("t.source_form LIKE ?")
        params.append(f"%{query['like']}%")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY t.source_language, t.source_form"
    rows = conn.execute(sql, params).fetchall()
    out_terms = []
    for r in rows:
        d = term_to_dict(r)
        d["occurrences"] = r["occurrences"]
        out_terms.append(d)
    return {"terms": out_terms}


def term_by_id(conn: sqlite3.Connection, term_id: int) -> dict[str, Any]:
    """Full term record plus per-translator default renderings and
    per-edition occurrence counts. The renderings list carries the
    `translator` name and target `language` so the UI can group by
    translator without an extra round trip."""

    term = conn.execute("SELECT * FROM terms WHERE id = ?",
                        (term_id,)).fetchone()
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


def terms_by_chunk(conn: sqlite3.Connection, chunk_id: str) -> dict[str, Any]:
    """Every term occurrence whose source_chunk_id == the given chunk.
    Returns spans + minimal term info so the reader can render hover
    targets without a second round trip per term.

    Sorted by source_start so the UI can paint highlights in document
    order; the client may further index by start offset for cursor →
    occurrence resolution."""

    rows = conn.execute(
        "SELECT o.id, o.term_id, o.source_start, o.source_end, "
        "       o.context_snippet, o.tradition, "
        "       o.location_kind, o.location_payload, o.location_sort_key, "
        "       t.source_form, t.source_language, t.short_gloss "
        "FROM term_occurrences o "
        "JOIN terms t ON t.id = o.term_id "
        "WHERE o.source_chunk_id = ? "
        "ORDER BY o.source_start",
        (chunk_id,),
    ).fetchall()
    return {
        "chunk_id": chunk_id,
        "occurrences": [
            {
                "id": r["id"],
                "term_id": r["term_id"],
                "source_form": r["source_form"],
                "source_language": r["source_language"],
                "short_gloss": r["short_gloss"],
                "source_start": r["source_start"],
                "source_end": r["source_end"],
                "context_snippet": r["context_snippet"],
                "tradition": r["tradition"],
                "location_kind": r["location_kind"],
                "location_payload": json.loads(r["location_payload"]),
                "location_sort_key": r["location_sort_key"],
            }
            for r in rows
        ],
    }


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
        conn, work_id, window.lang, window.from_ord, window.limit,
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


def work_occurrences(
    conn: sqlite3.Connection,
    work_id: int,
    query: dict[str, str],
) -> dict[str, Any]:
    """Every occurrence of one term in one work, with the rendering
    each translation gives. Implements Q2 from the original spec:
        "given a Term, list every occurrence in this work and how each
    translation rendered it."

    Per the language-filter clarification, occurrences are restricted
    to editions in the term's `source_language`. When the work has
    multiple source-language editions, only the canonical edition is
    returned by default; pass ``edition_id=<id>`` to override.

    Each occurrence row carries a `renderings` map keyed by
    translation_id; the value is either the per-occurrence override
    (from ``occurrence_renderings``) or the translator's stated
    default (from ``term_renderings``), tagged with a
    ``source: 'override' | 'default'`` field so the UI can flag
    divergences.
    """

    try:
        term_id = int(query.get("term_id", ""))
    except ValueError:
        raise BadRequestError("term_id query param required (int)") from None

    edition_filter: int | None = None
    if query.get("edition_id"):
        try:
            edition_filter = int(query["edition_id"])
        except ValueError:
            raise BadRequestError("edition_id must be an integer") from None

    term = conn.execute(
        "SELECT source_language FROM terms WHERE id = ?", (term_id,)
    ).fetchone()
    if term is None:
        raise NotFoundError("unknown term id")
    work = conn.execute(
        "SELECT id, author, title FROM works WHERE id = ?", (work_id,)
    ).fetchone()
    if work is None:
        raise NotFoundError("unknown work id")

    # Pick the edition(s) to consult: canonical edition in the
    # term's source language unless the caller pinned a specific
    # edition_id. The canonical default sidesteps the cross-
    # edition Q2 multiplication question for the common case.
    if edition_filter is not None:
        editions = conn.execute(
            "SELECT id FROM editions WHERE id = ? AND work_id = ?   AND language = ?",
            (edition_filter, work_id, term["source_language"]),
        ).fetchall()
        if not editions:
            raise NotFoundError("edition_id does not belong to this work/source-language pair",
            )
    else:
        editions = conn.execute(
            "SELECT id FROM editions WHERE work_id = ? AND language = ?   AND is_canonical = 1",
            (work_id, term["source_language"]),
        ).fetchall()
    edition_ids = [r["id"] for r in editions]
    if not edition_ids:
        return {
            "work_id": work_id,
            "term_id": term_id,
            "occurrences": [],
        }

    placeholders = ",".join("?" * len(edition_ids))
    occs = conn.execute(
        f"SELECT id, source_chunk_id, source_start, source_end, "
        f"       context_snippet, tradition, location_kind, "
        f"       location_payload, location_sort_key, edition_id "
        f"FROM term_occurrences "
        f"WHERE term_id = ? AND edition_id IN ({placeholders}) "
        f"ORDER BY location_sort_key, instance_index",
        (term_id, *edition_ids),
    ).fetchall()

    # Translations of this work — used to populate per-occurrence
    # rendering grids. We pull the default renderings once and
    # apply per-occurrence overrides on top.
    translations = conn.execute(
        "SELECT id, translator_name, year, language FROM translations "
        "WHERE work_id = ? ORDER BY language, translator_name, year",
        (work_id,),
    ).fetchall()
    translation_ids = [r["id"] for r in translations]
    # translation_id → {term_id → rendering}
    defaults: dict[int, dict[int, str]] = {}
    for tr_id in translation_ids:
        row = conn.execute(
            "SELECT default_rendering FROM term_renderings "
            "WHERE translation_id = ? AND term_id = ?",
            (tr_id, term_id),
        ).fetchone()
        if row is not None:
            defaults.setdefault(tr_id, {})[term_id] = row[0]

    # Per-occurrence overrides.
    occ_ids = [r["id"] for r in occs]
    overrides: dict[tuple[int, int], str] = {}
    if occ_ids:
        placeholders2 = ",".join("?" * len(occ_ids))
        for row in conn.execute(
            f"SELECT occurrence_id, translation_id, rendered_text "
            f"FROM occurrence_renderings "
            f"WHERE occurrence_id IN ({placeholders2})",
            occ_ids,
        ):
            overrides[(row["occurrence_id"], row["translation_id"])
                      ] = row["rendered_text"]

    def _renderings_for(occ_id: int) -> list[dict[str, Any]]:
        out = []
        for tr in translations:
            rid = tr["id"]
            override = overrides.get((occ_id, rid))
            default = defaults.get(rid, {}).get(term_id)
            if override is not None:
                out.append(
                    {
                        "translation_id": rid,
                        "translator": tr["translator_name"],
                        "year": tr["year"],
                        "language": tr["language"],
                        "rendered": override,
                        "source": "override",
                    }
                )
            elif default is not None:
                out.append(
                    {
                        "translation_id": rid,
                        "translator": tr["translator_name"],
                        "year": tr["year"],
                        "language": tr["language"],
                        "rendered": default,
                        "source": "default",
                    }
                )
            # No rendering at all: omit the translator from this
            # occurrence's grid. UI can show a column header for every
            # translation it knows about and treat missing rows as gaps.
        return out

    return {
        "work_id": work_id,
        "work_title": work["title"],
        "author": work["author"],
        "term_id": term_id,
        "occurrences": [
            {
                "id": r["id"],
                "edition_id": r["edition_id"],
                "source_chunk_id": r["source_chunk_id"],
                "source_start": r["source_start"],
                "source_end": r["source_end"],
                "context_snippet": r["context_snippet"],
                "tradition": r["tradition"],
                "location_kind": r["location_kind"],
                "location_payload": json.loads(r["location_payload"]),
                "location_sort_key": r["location_sort_key"],
                "renderings": _renderings_for(r["id"]),
            }
            for r in occs
        ],
    }


def translation_renderings(
    conn: sqlite3.Connection,
    translation_id: int,
) -> dict[str, Any]:
    """Every term rendering used by one translation, paired with the
    matching source-language term. Powers the "toggle this translator's
    text back to the source language" UI: walk the translated text,
    look up each rendering's term, swap the rendered phrase for the
    term's `source_form`.

    Returns the translator's full glossary (default renderings) plus a
    summary count of per-occurrence overrides — overrides themselves
    are joined per-occurrence in /api/works/.../term_occurrences."""

    tr = conn.execute(
        "SELECT t.id, t.translator_name, t.year, t.language, "
        "       t.work_id, w.author, w.title AS work_title "
        "FROM translations t JOIN works w ON w.id = t.work_id "
        "WHERE t.id = ?",
        (translation_id,),
    ).fetchone()
    if tr is None:
        raise NotFoundError("unknown translation id")
    renderings = conn.execute(
        "SELECT r.id, r.default_rendering, r.translator_note, "
        "       t.id AS term_id, t.source_form, t.source_language, "
        "       t.transliteration, t.short_gloss "
        "FROM term_renderings r "
        "JOIN terms t ON t.id = r.term_id "
        "WHERE r.translation_id = ? "
        "ORDER BY t.source_form",
        (translation_id,),
    ).fetchall()
    override_count = conn.execute(
        "SELECT COUNT(*) FROM occurrence_renderings WHERE translation_id = ?",
        (translation_id,),
    ).fetchone()[0]
    return {
        "translation_id": tr["id"],
        "translator": tr["translator_name"],
        "year": tr["year"],
        "language": tr["language"],
        "work_id": tr["work_id"],
        "work_title": tr["work_title"],
        "author": tr["author"],
        "renderings": [
            {
                "id": r["id"],
                "term_id": r["term_id"],
                "source_form": r["source_form"],
                "source_language": r["source_language"],
                "transliteration": r["transliteration"],
                "short_gloss": r["short_gloss"],
                "default_rendering": r["default_rendering"],
                "translator_note": r["translator_note"],
            }
            for r in renderings
        ],
        "override_count": override_count,
    }
