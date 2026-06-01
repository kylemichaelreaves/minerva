"""Citation-network dashboard aggregate queries."""

from __future__ import annotations

import sqlite3
from typing import Any

from .filters import parse_filters, status_clause
from .row_utils import short_author


def _corpus_bucket(author: str) -> str:
    from ..author_ordering import AUTHOR_ORDINAL, DEFAULT_AUTHOR_ORDINAL

    if author in (
        "Hebrew Bible", "Septuagint", "New Testament", "Vulgate", "Quran",
        "Luther Bibel 1545", "Luther Bibel 1912", "King James Bible", "Sacy",
    ):
        return "scrip"
    ord_ = AUTHOR_ORDINAL.get(author, DEFAULT_AUTHOR_ORDINAL)
    if ord_ < 500:
        return "class"
    if ord_ < 800:
        return "med"
    if ord_ < 900:
        return "em"
    if ord_ < 9999:
        return "mod"
    return "ext"


# Books of the Bible the heatmap shows, grouped by canonical
# division. Mirrors the wireframe — SBL abbreviations as labels,
# but matched against the full book names that appear in
# ``reference_targets.canonical_work``.
_BIBLE_SECTIONS: tuple[tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...] = (
    (
        "Torah",
        (
            ("Gen", ("Genesis",)),
            ("Exod", ("Exodus",)),
            ("Lev", ("Leviticus",)),
            ("Num", ("Numbers",)),
            ("Deut", ("Deuteronomy",)),
        ),
    ),
    (
        "Prophets",
        (
            ("Josh", ("Joshua",)),
            ("Judg", ("Judges",)),
            ("1 Sam", ("1 Samuel",)),
            ("2 Sam", ("2 Samuel",)),
            ("1 Kgs", ("1 Kings",)),
            ("2 Kgs", ("2 Kings",)),
            ("Isa", ("Isaiah",)),
            ("Jer", ("Jeremiah",)),
            ("Ezek", ("Ezekiel",)),
            ("Hos", ("Hosea",)),
            ("Amos", ("Amos",)),
            ("Mic", ("Micah",)),
        ),
    ),
    (
        "Writings",
        (
            ("Ps", ("Psalms",)),
            ("Prov", ("Proverbs",)),
            ("Job", ("Job",)),
            ("Eccl", ("Ecclesiastes",)),
            ("Cant", ("Song of Solomon", "Song of Songs", "Canticles")),
            ("Dan", ("Daniel",)),
            ("Ezra", ("Ezra",)),
            ("Neh", ("Nehemiah",)),
            ("1 Chr", ("1 Chronicles",)),
            ("2 Chr", ("2 Chronicles",)),
        ),
    ),
    (
        "Gospels",
        (
            ("Mt", ("Matthew",)),
            ("Mk", ("Mark",)),
            ("Lk", ("Luke",)),
            ("Jn", ("John",)),
            ("Acts", ("Acts",)),
        ),
    ),
    (
        "Epistles",
        (
            ("Rom", ("Romans",)),
            ("1 Cor", ("1 Corinthians",)),
            ("2 Cor", ("2 Corinthians",)),
            ("Gal", ("Galatians",)),
            ("Eph", ("Ephesians",)),
            ("Phil", ("Philippians",)),
            ("Col", ("Colossians",)),
            ("Heb", ("Hebrews",)),
            ("Jas", ("James",)),
            ("1 Pet", ("1 Peter",)),
            ("1 Jn", ("1 John",)),
        ),
    ),
    (
        "Apoc.",
        (("Rev", ("Revelation",)),),
    ),
)


_SOURCE_METHOD_BUCKETS: tuple[str, ...] = (
    "manual",
    "rule_strong",
    "rule+embed",
    "rule+embed+llm",
    "rule_weak",
)


def network_summary(
    conn: sqlite3.Connection,
    query: dict[str, str],
) -> dict[str, Any]:
    """``GET /api/network/summary``.

    One-shot payload for the citation-network dashboard. Returns
    the author×author matrix (sparse), top author-pairs, scripture
    citation heatmap, per-author verification-method breakdown,
    and the leaderboard of most-cited works.

    Honours the standard visibility filters
    (``include_rejected`` / ``min_confidence``) so the dashboard
    counts agree with the /refs list at the same filter setting.

    The whole payload is one query roundtrip in practice — five
    aggregate queries against ``cross_references`` joined with
    ``reference_targets`` and ``works`` — designed to fit in
    well under 200 ms on the current index.
    """

    from ..author_ordering import AUTHOR_ORDINAL, author_sort_key

    statuses, min_conf = parse_filters(query)
    status_sql, status_params = status_clause(statuses, min_conf)

    # Optional extra filters: comma-separated lists of source authors,
    # corpus buckets, and source_methods. Every clause is opt-in — if
    # the caller omits the param, the corresponding fragment is empty
    # and the WHERE retains its existing shape.
    extra_sql = ""
    extra_params: list[Any] = []

    raw_source_authors = (query.get("source_author") or "").strip()
    if raw_source_authors:
        names = [s for s in (n.strip() for n in raw_source_authors.split(",")) if s]
        if names:
            extra_sql += (
                f" AND src_work.author IN ({','.join('?' * len(names))})"
            )
            extra_params.extend(names)

    raw_methods = (query.get("source_method") or "").strip()
    if raw_methods:
        methods = [m for m in (s.strip() for s in raw_methods.split(",")) if m]
        if methods:
            extra_sql += (
                f" AND xr.source_method IN ({','.join('?' * len(methods))})"
            )
            extra_params.extend(methods)

    raw_corpora = (query.get("corpus") or "").strip()
    if raw_corpora:
        buckets = {b for b in (s.strip() for s in raw_corpora.split(",")) if b}
        if buckets:
            authors_in_buckets = [
                a for a in AUTHOR_ORDINAL if _corpus_bucket(a) in buckets
            ]
            if not authors_in_buckets:
                # Bucket name didn't match any author — return zero rows
                # rather than dropping the filter silently.
                authors_in_buckets = ["__no_such_author__"]
            extra_sql += (
                f" AND src_work.author IN ({','.join('?' * len(authors_in_buckets))})"
            )
            extra_params.extend(authors_in_buckets)

    # 1. Author × author counts (source → target).
    rows = conn.execute(
        f"""
        SELECT src_work.author AS src_author,
               rt.canonical_author AS tgt_author,
               COUNT(*) AS n
        FROM cross_references xr
        JOIN chunks c ON c.chunk_id = xr.source_chunk_id
        LEFT JOIN editions e ON e.id = c.edition_id
        LEFT JOIN translations t ON t.id = c.translation_id
        LEFT JOIN works src_work
               ON src_work.id = COALESCE(e.work_id, t.work_id)
        JOIN reference_targets rt ON rt.id = xr.target_id
        WHERE {status_sql}
          AND src_work.author IS NOT NULL
          AND rt.canonical_author IS NOT NULL
          {extra_sql}
        GROUP BY src_work.author, rt.canonical_author
        """,
        (*status_params, *extra_params),
    ).fetchall()

    # Matrix axis = in-corpus authors only (those with an explicit
    # AUTHOR_ORDINAL). Out-of-corpus targets (Proudhon, Wagner,
    # Schopenhauer, Smith…) still appear in the top-pairs list and
    # the works leaderboard, but don't get their own row/column —
    # they'd bunch at the right edge without a real ordinal, and
    # render the chronological sort meaningless.
    in_corpus = set(AUTHOR_ORDINAL.keys())
    authors_sorted = sorted(
        [a for a in {r[0] for r in rows} | {r[1] for r in rows} if a in in_corpus],
        key=author_sort_key,
    )
    author_idx = {a: i for i, a in enumerate(authors_sorted)}

    cells: list[tuple[int, int, int]] = []
    pair_rows: list[tuple[str, str, int, bool]] = []
    for src_a, tgt_a, n in rows:
        intra_scrip = (
            _corpus_bucket(src_a) == "scrip" and _corpus_bucket(tgt_a) == "scrip"
        )
        pair_rows.append((src_a, tgt_a, int(n), intra_scrip))
        if src_a in author_idx and tgt_a in author_idx:
            cells.append((author_idx[src_a], author_idx[tgt_a], int(n)))

    authors_payload = [
        {
            "name": a,
            "short": short_author(a),
            "ord": AUTHOR_ORDINAL.get(a, 9999),
            "corpus": _corpus_bucket(a),
        }
        for a in authors_sorted
    ]

    # 2. Top author pairs (three slices, used by the arc panel).
    #
    # a) ``all`` and ``non_scrip`` are volume-ranked. We surface
    #    enough pairs to keep the new modern→Bible edges visible on
    #    the arc even when intra-medieval pairs (Aquinas→Augustine,
    #    Marx→Proudhon) dominate the volumetric leaderboard.
    # b) ``per_author_top`` is a different cut: for each source
    #    author, their top 3 non-intra-scripture outgoing pairs. This
    #    guarantees a canonical-lineage view — Hegel→Heraclitus and
    #    Nietzsche→Heraclitus survive even though their volumes (49,
    #    58) sit just below the volumetric top-30 cutoff. The frontend
    #    arc unions ``non_scrip`` with ``per_author_top`` so both the
    #    "what's heavy?" and the "what's each thinker's top 3?"
    #    perspectives land on screen.
    pair_rows.sort(key=lambda r: r[2], reverse=True)
    top_pairs_all = [
        {"src": s, "tgt": t, "n": n, "intra_scrip": isc}
        for s, t, n, isc in pair_rows[:60]
    ]
    top_pairs_non_scrip = [
        {"src": s, "tgt": t, "n": n, "intra_scrip": isc}
        for s, t, n, isc in pair_rows
        if not isc
    ][:50]
    # Top 5 per author (not 3) because some thinkers' canonical
    # interlocutors don't crack their own top 3 by volume — Hegel's
    # top 3 is Kant/Cicero/KJV, but Heraclitus (49) is #4 and is
    # pedagogically central to the Logic. Top 5 catches the canonical
    # lineage without exploding the arc.
    _per_author_seen: dict[str, int] = {}
    top_pairs_per_author: list[dict[str, Any]] = []
    for s, t, n, isc in pair_rows:
        if isc:
            continue
        if _per_author_seen.get(s, 0) >= 5:
            continue
        _per_author_seen[s] = _per_author_seen.get(s, 0) + 1
        top_pairs_per_author.append(
            {"src": s, "tgt": t, "n": n, "intra_scrip": isc}
        )

    # 3. Scripture heatmap: per (source_author, target_work)
    # counts where target_work is a biblical book the heatmap
    # tracks. Only source authors from Augustine onward are shown.
    scrip_authors = [
        a
        for a in authors_sorted
        if _corpus_bucket(a) in ("med", "em", "mod")
        and AUTHOR_ORDINAL.get(a, 9999) >= 600
    ]
    book_aliases: dict[str, tuple[str, str]] = {}  # canonical_work → (label, section)
    for section_name, books in _BIBLE_SECTIONS:
        for label, aliases in books:
            for alias in aliases:
                book_aliases[alias] = (label, section_name)
    heat_counts: dict[tuple[str, str], int] = {}
    if scrip_authors:
        # Two book sources, coalesced: ``rt.canonical_work`` (from rule-pass
        # refs that name a specific biblical book, e.g. Hobbes→Matthew) and
        # ``tgt.book`` (from embed-verify Pass B refs that target a
        # specific chunk but emit ``canonical_work='*'``, e.g. Pascal's
        # paraphrases targeting a specific Sacy verse). Without the
        # target-chunk fallback the heatmap silently drops every
        # paraphrase/allusion ref and looks bare for Pascal / Spinoza /
        # any author whose biblical engagement is paraphrastic.
        scrip_rows = conn.execute(
            f"""
            SELECT src_work.author AS src_author,
                   COALESCE(NULLIF(rt.canonical_work, '*'), tgt.book) AS book,
                   COUNT(*) AS n
            FROM cross_references xr
            JOIN chunks c ON c.chunk_id = xr.source_chunk_id
            LEFT JOIN editions e ON e.id = c.edition_id
            LEFT JOIN translations t ON t.id = c.translation_id
            LEFT JOIN works src_work
                   ON src_work.id = COALESCE(e.work_id, t.work_id)
            JOIN reference_targets rt ON rt.id = xr.target_id
            LEFT JOIN chunks tgt ON tgt.chunk_id = xr.target_chunk_id
            WHERE {status_sql}
              AND src_work.author IN ({",".join("?" * len(scrip_authors))})
              AND COALESCE(NULLIF(rt.canonical_work, '*'), tgt.book) IS NOT NULL
              {extra_sql}
            GROUP BY src_work.author, COALESCE(NULLIF(rt.canonical_work, '*'), tgt.book)
            """,
            (*status_params, *scrip_authors, *extra_params),
        ).fetchall()
        for src_a, book, n in scrip_rows:
            alias = book_aliases.get(book)
            if alias is None:
                continue
            label, _section = alias
            key = (src_a, label)
            heat_counts[key] = heat_counts.get(key, 0) + int(n)

    heatmap_payload = {
        "authors": scrip_authors,
        "sections": [
            {"name": section, "books": [label for label, _ in books]}
            for section, books in _BIBLE_SECTIONS
        ],
        "cells": [
            {"author": a, "book": b, "n": n}
            for (a, b), n in heat_counts.items()
        ],
    }

    # 4. Verification — source_author × source_method counts, then
    # top 10 by total. ``rule+embed`` and ``rule+embed+llm`` are
    # carried verbatim; anything else falls into ``other``.
    verif_rows = conn.execute(
        f"""
        SELECT src_work.author AS src_author,
               xr.source_method AS method,
               COUNT(*) AS n
        FROM cross_references xr
        JOIN chunks c ON c.chunk_id = xr.source_chunk_id
        LEFT JOIN editions e ON e.id = c.edition_id
        LEFT JOIN translations t ON t.id = c.translation_id
        LEFT JOIN works src_work
               ON src_work.id = COALESCE(e.work_id, t.work_id)
        WHERE {status_sql} AND src_work.author IS NOT NULL
          {extra_sql}
        GROUP BY src_work.author, xr.source_method
        """,
        (*status_params, *extra_params),
    ).fetchall()
    verif_totals: dict[str, int] = {}
    verif_breakdown: dict[str, dict[str, int]] = {}
    for src_a, method, n in verif_rows:
        bucket = method if method in _SOURCE_METHOD_BUCKETS else "other"
        verif_totals[src_a] = verif_totals.get(src_a, 0) + int(n)
        verif_breakdown.setdefault(src_a, {})
        verif_breakdown[src_a][bucket] = (
            verif_breakdown[src_a].get(bucket, 0) + int(n)
        )
    top_verif = sorted(
        verif_totals.items(), key=lambda kv: kv[1], reverse=True
    )[:10]
    verification_payload = [
        {
            "author": a,
            "total": total,
            "parts": {
                m: verif_breakdown[a].get(m, 0) for m in _SOURCE_METHOD_BUCKETS
            },
            "other": verif_breakdown[a].get("other", 0),
        }
        for a, total in top_verif
    ]

    # 5. Top-cited works. Joins the source-side editions/works so the
    # corpus / source_method / source_author filters apply here too —
    # otherwise the leaderboard would ignore the user's filter slice.
    work_rows = conn.execute(
        f"""
        SELECT rt.canonical_author AS author,
               rt.canonical_work AS work,
               COUNT(*) AS n
        FROM cross_references xr
        JOIN reference_targets rt ON rt.id = xr.target_id
        JOIN chunks c ON c.chunk_id = xr.source_chunk_id
        LEFT JOIN editions e ON e.id = c.edition_id
        LEFT JOIN translations t ON t.id = c.translation_id
        LEFT JOIN works src_work
               ON src_work.id = COALESCE(e.work_id, t.work_id)
        WHERE {status_sql}
          AND rt.canonical_author IS NOT NULL
          AND rt.canonical_work IS NOT NULL
          AND rt.canonical_work != '*'
          {extra_sql}
        GROUP BY rt.canonical_author, rt.canonical_work
        ORDER BY n DESC
        LIMIT 30
        """,
        (*status_params, *extra_params),
    ).fetchall()
    top_works = [
        {"work": work, "author": author, "n": int(n)}
        for author, work, n in work_rows
    ]

    # 6. Overall totals (for the header strip). The xref count
    # honors the active filter; the works count is a static corpus
    # statistic and stays constant.
    total_xrefs = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM cross_references xr
        JOIN chunks c ON c.chunk_id = xr.source_chunk_id
        LEFT JOIN editions e ON e.id = c.edition_id
        LEFT JOIN translations t ON t.id = c.translation_id
        LEFT JOIN works src_work
               ON src_work.id = COALESCE(e.work_id, t.work_id)
        WHERE {status_sql}
          {extra_sql}
        """,
        (*status_params, *extra_params),
    ).fetchone()[0]
    total_works = conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]

    return {
        "totals": {
            "xrefs": int(total_xrefs),
            "authors": len(authors_sorted),
            "works": int(total_works),
        },
        "matrix": {
            "authors": authors_payload,
            "cells": [
                {"r": r, "c": c, "n": n} for r, c, n in cells
            ],
        },
        "top_pairs": {
            "all": top_pairs_all,
            "non_scrip": top_pairs_non_scrip,
            "per_author_top": top_pairs_per_author,
        },
        "scripture_heatmap": heatmap_payload,
        "verification": verification_payload,
        "top_works": top_works,
    }

