"""Lemma frequency index queries."""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from typing import Any

from ..errors import BadRequestError
from ._scope import (
    _DEFAULT_CONTENT_POS,
    _DEFAULT_INDEX_LIMIT,
    _MAX_INDEX_LIMIT,
    _scope_clause,
    parse_authors,
    parse_works,
)


def lemma_index(conn: sqlite3.Connection, query: dict[str, str]) -> dict[str, Any]:
    """Aggregate all lemmas in scope, return ranked leaderboard.

    Query params:
      lang       (required) ISO-639-3 code, e.g. ``deu``
      scope      one of corpus | author | work  (default: corpus)
      author     required when scope=author
      work       required when scope=work
      letter     one-character leading-letter filter. For Latin-script
                 langs this is an ASCII A–Z, case-insensitive LIKE. For
                 Greek (``grc``) the lemma's first character is folded
                 (diacritics stripped, upper-cased) before comparison so
                 ``Α`` matches ἀ/ἄ/Ἀ/α (see ``_fold_initial``).
      q          case-insensitive substring filter on the lemma —
                 drives the F1 "find lemma" search field. Trimmed; an
                 empty/whitespace-only value is ignored.
      pos_in     comma-separated POS whitelist; default content words
                 only (NOUN/VERB/ADJ/PROPN). Pass ``all`` to
                 disable the filter and surface function words too.
      sort       freq | alpha | pos  (default: freq)
      limit      default 200, max 1000
      offset     default 0
      min_count  drop lemmas with fewer than this many occurrences in
                 scope (default 2 — strips spaCy noise + hapax that
                 would otherwise dominate the long tail). Drives the
                 lower edge of the F1 frequency-range slider.
      max_count  drop lemmas with more than this many occurrences in
                 scope (default: no upper bound). Drives the upper
                 edge of the F1 frequency-range slider.

    Response:
      {
        scope: "corpus" | "author" | "work",
        scope_label: "All German" | "Hegel" | "PhdG",
        total_lemmas: int,
        total_occurrences: int,
        sort: "freq" | "alpha" | "pos",
        letter: "A" | None,
        rows: [
          {
            rank: 1,
            lemma: "Geist",
            pos: "NOUN",
            count: 1247,
            distinct_works: 4,
            per_work: [ { work: "PhdG", n: 312 }, ... ],   # top 8
          },
          ...
        ],
      }
    """

    lang = query.get("lang")
    if not lang:
        raise BadRequestError("'lang' query param is required")
    scope = query.get("scope", "corpus")
    authors = parse_authors(query)
    works = parse_works(query)
    letter = (query.get("letter") or "").strip()[:1]
    sort = query.get("sort", "freq")
    if sort not in ("freq", "alpha", "pos"):
        raise BadRequestError("'sort' must be one of: freq, alpha, pos")

    pos_in_raw = query.get("pos_in")
    pos_in: tuple[str, ...] | None
    if pos_in_raw is None:
        pos_in = _DEFAULT_CONTENT_POS
    elif pos_in_raw.strip().lower() == "all":
        pos_in = None  # disable filter
    else:
        pos_in = tuple(p.strip().upper() for p in pos_in_raw.split(",") if p.strip())

    # Case-variant merging — spaCy preserves typographic flourishes
    # ("GOtt", "HErr", "HERRN") as distinct lemmas; the concordance
    # leaderboard wants these collapsed under their canonical
    # capitalization. Default ON; pass merge_case=0 to disable.
    merge_case = query.get("merge_case", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )

    try:
        limit = int(query.get("limit", str(_DEFAULT_INDEX_LIMIT)))
        offset = int(query.get("offset", "0"))
        min_count = int(query.get("min_count", "2"))
        max_count_raw = query.get("max_count")
        max_count: int | None = int(max_count_raw) if max_count_raw not in (None, "") else None
    except ValueError as e:
        raise BadRequestError(f"integer query param parse error: {e}") from None
    limit = max(1, min(_MAX_INDEX_LIMIT, limit))
    offset = max(0, offset)
    min_count = max(1, min_count)
    if max_count is not None and max_count < min_count:
        # Caller passed an inverted range — return zero rows rather than
        # silently swapping or erroring. The UI's slider can land here
        # transiently while the user drags the upper knob below the lower.
        max_count = min_count - 1

    q = (query.get("q") or "").strip()

    _scope_clause(scope, authors, works)  # validates scope/author/work pairing


    # Polytonic Greek lemmas begin with *precomposed* diacritic forms
    # (ἀ / ἄ / Ἀ), so the ASCII ``LIKE 'Α%' NOCASE`` letter filter used
    # for Latin-script langs would miss almost everything. For Greek we
    # match on a diacritic-folded, case-folded leading letter instead
    # (registered as a SQLite scalar fn below). Gated to ``grc`` so the
    # German Ä/Ö/Ü/ß bucketing the LIKE path gives is left untouched.
    fold_letter = lang == "grc"
    if fold_letter:
        conn.create_function("fold_initial", 1, _fold_initial, deterministic=True)

    # ── Materialized read path ────────────────────────────────────
    # The ``lemma_counts`` table (migration 0019, populated by
    # ``minerva.concordance.aggregate.build``) carries one row per
    # (lang, scope_kind, scope_value, lemma, pos) with the count,
    # distinct_works, and top-8 per-work breakdown pre-computed.
    # This swaps a 16-36s GROUP BY scan over chunk_lemmas for a
    # millisecond seek by index.
    #
    # Filters (letter / pos / q / freq range) apply against the
    # materialized columns. case-merge happens in Python on the
    # narrowed result so the per-work JSON values from merged
    # variants combine correctly.
    if scope == "corpus":
        scope_kind, scope_values = "corpus", []
    elif scope == "author":
        scope_kind, scope_values = "author", authors
    else:
        scope_kind, scope_values = "work", works

    # Multiple authors/works → multiple lemma_counts rows per (lemma,
    # pos), one per scope value; they must be summed in Python (the
    # materialized rows are per-scope-value). The case-merge block
    # already sums + merges per_work, so we route the multi-value case
    # through it even when case-merge is off.
    multi_work = len(scope_values) > 1
    aggregate = merge_case or multi_work

    # Shared WHERE clause against lemma_counts (also used by the
    # totals query below). The main query alone adds the freq range.
    where_parts, where_params = _counts_where(
        lang,
        scope_kind,
        scope_values,
        letter=letter,
        fold_letter=fold_letter,
        pos_in=pos_in,
        q=q,
    )
    if max_count is not None:
        where_parts.append("count <= ?")
        where_params.append(max_count)
    where_parts.append("count >= ?")
    where_params.append(min_count)

    order_clause = {
        "freq": "count DESC, lemma COLLATE NOCASE ASC",
        "alpha": "lemma COLLATE NOCASE ASC",
        "pos": "pos COLLATE NOCASE ASC, count DESC",
    }[sort]

    if aggregate:
        rows, variants_by_display = _fetch_aggregate_page(
            conn,
            lang=lang,
            fold_letter=fold_letter,
            merge_case=merge_case,
            where_parts=where_parts,
            where_params=where_params,
            min_count=min_count,
            max_count=max_count,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    else:
        sql_main = f"""
            SELECT lemma, pos, count AS n, distinct_works, per_work_json
            FROM lemma_counts
            WHERE {" AND ".join(where_parts)}
            ORDER BY {order_clause}
            LIMIT ? OFFSET ?
        """
        raw_rows = conn.execute(
            sql_main, [*where_params, limit, offset]
        ).fetchall()
        rows = [
            {
                "lemma": r["lemma"],
                "pos": r["pos"] or "",
                "n": int(r["n"]),
                "distinct_works": int(r["distinct_works"]),
                "per_work": json.loads(r["per_work_json"] or "[]"),
            }
            for r in raw_rows
        ]
        variants_by_display = {(r["lemma"], r["pos"]): [r["lemma"]] for r in rows}

    # ── Totals ────────────────────────────────────────────────────
    # Sum the same scope+filter slice for header counts. Frequency
    # range is deliberately NOT applied here (the range shapes which
    # lemmas show up; the header is meant to be a scope-wide
    # reference). The lemma-search ``q`` IS applied so a search for
    # "geist" doesn't show "1.9M occurrences" next to 4 rows.
    totals_where_parts, totals_where_params = _counts_where(
        lang,
        scope_kind,
        scope_values,
        letter=letter,
        fold_letter=fold_letter,
        pos_in=pos_in,
        q=q,
    )
    if aggregate and merge_case:
        group_expr = _lemma_group_expr(fold_letter, merge_case=True)
        sql_totals = f"""
            SELECT COUNT(*) AS total_lemmas,
                   COALESCE(SUM(n), 0) AS total_tokens
            FROM (
                SELECT {group_expr} AS lemma_key, pos, SUM(count) AS n
                FROM lemma_counts
                WHERE {" AND ".join(totals_where_parts)}
                GROUP BY lemma_key, pos
            )
        """
    elif aggregate:
        sql_totals = f"""
            SELECT COUNT(*) AS total_lemmas,
                   COALESCE(SUM(n), 0) AS total_tokens
            FROM (
                SELECT lemma, pos, SUM(count) AS n
                FROM lemma_counts
                WHERE {" AND ".join(totals_where_parts)}
                GROUP BY lemma, pos
            )
        """
    else:
        # COUNT(DISTINCT lemma) — not COUNT(*) — because a single lemma
        # can carry multiple POS tags (the lemmatizer occasionally splits
        # the same word into NOUN + VERB rows). The header reads as
        # "distinct lemmas", which is what users expect.
        sql_totals = f"""
            SELECT COUNT(DISTINCT lemma) AS total_lemmas,
                   COALESCE(SUM(count), 0) AS total_tokens
            FROM lemma_counts
            WHERE {" AND ".join(totals_where_parts)}
        """
    totals = conn.execute(sql_totals, totals_where_params).fetchone()

    out_rows = []
    for i, r in enumerate(rows):
        key = (r["lemma"], r["pos"])
        out_rows.append(
            {
                "rank": offset + i + 1,
                "lemma": r["lemma"],
                "pos": r["pos"] or "",
                "count": int(r["n"]),
                "distinct_works": int(r["distinct_works"]),
                "per_work": r.get("per_work", []),
                # Include variant list for transparency — the UI can show
                # "(also GOtt, GOTT)" if curious. Not currently rendered.
                "variants": variants_by_display.get(key, [r["lemma"]]),
            }
        )

    if scope == "work":
        scope_label = works[0] if len(works) == 1 else f"{len(works)} works"
    elif scope == "author":
        scope_label = authors[0] if len(authors) == 1 else f"{len(authors)} authors"
    else:
        scope_label = _corpus_label(lang)

    return {
        "scope": scope,
        "scope_label": scope_label,
        "lang": lang,
        "letter": letter or None,
        "sort": sort,
        "total_lemmas": int(totals["total_lemmas"]) if totals else 0,
        "total_occurrences": int(totals["total_tokens"]) if totals else 0,
        "limit": limit,
        "offset": offset,
        "rows": out_rows,
    }


def _lemma_group_expr(fold_letter: bool, *, merge_case: bool) -> str:
    if not merge_case:
        return "lemma"
    return "fold_initial(lemma)" if fold_letter else "LOWER(lemma)"


def _fetch_aggregate_page(
    conn: sqlite3.Connection,
    *,
    lang: str,
    fold_letter: bool,
    merge_case: bool,
    where_parts: list[str],
    where_params: list[Any],
    min_count: int,
    max_count: int | None,
    sort: str,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], list[str]]]:
    """Page merged lemma rows in SQL instead of scanning from offset 0."""

    group_expr = _lemma_group_expr(fold_letter, merge_case=merge_case)
    having_parts = ["SUM(count) >= ?"]
    having_params: list[Any] = [min_count]
    if max_count is not None:
        having_parts.append("SUM(count) <= ?")
        having_params.append(max_count)

    order_clause = {
        "freq": "n DESC, lemma_key COLLATE NOCASE ASC",
        "alpha": "lemma_key COLLATE NOCASE ASC",
        "pos": "pos COLLATE NOCASE ASC, n DESC",
    }[sort]

    sql = f"""
        SELECT lemma_key, pos, n, variants_blob, per_work_blob
        FROM (
            SELECT
                {group_expr} AS lemma_key,
                pos,
                SUM(count) AS n,
                GROUP_CONCAT(lemma || CHAR(1) || count, CHAR(2)) AS variants_blob,
                GROUP_CONCAT(per_work_json, CHAR(3)) AS per_work_blob
            FROM lemma_counts
            WHERE {" AND ".join(where_parts)}
            GROUP BY lemma_key, pos
            HAVING {" AND ".join(having_parts)}
        )
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """
    raw_rows = conn.execute(
        sql,
        [*where_params, *having_params, limit, offset],
    ).fetchall()

    rows: list[dict[str, Any]] = []
    variants_by_display: dict[tuple[str, str], list[str]] = {}
    for r in raw_rows:
        pos = r["pos"] or ""
        variants = _parse_variants_blob(r["variants_blob"] or "")
        display = _canonical_display(lang, pos, [v[0] for v in variants])
        work_counts = _merge_per_work_blobs(r["per_work_blob"] or "")
        top_per_work = sorted(work_counts.items(), key=lambda kv: -kv[1])[:8]
        rows.append(
            {
                "lemma": display,
                "pos": pos,
                "n": int(r["n"]),
                "distinct_works": len(work_counts),
                "per_work": [{"work": w, "n": n} for w, n in top_per_work],
            }
        )
        variants_by_display[(display, pos)] = [v[0] for v in variants]
    return rows, variants_by_display


def _parse_variants_blob(blob: str) -> list[tuple[str, int]]:
    variants: list[tuple[str, int]] = []
    for part in blob.split(chr(2)):
        if not part:
            continue
        lemma, _, count_raw = part.partition(chr(1))
        if not lemma:
            continue
        try:
            variants.append((lemma, int(count_raw)))
        except ValueError:
            continue
    variants.sort(key=lambda v: -v[1])
    return variants


def _merge_per_work_blobs(blob: str) -> dict[str, int]:
    work_counts: dict[str, int] = {}
    for chunk in blob.split(chr(3)):
        if not chunk:
            continue
        try:
            entries = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            work = entry.get("work")
            if work:
                work_counts[work] = work_counts.get(work, 0) + int(entry.get("n", 0))
    return work_counts


def _counts_where(
    lang: str,
    scope_kind: str,
    scope_values: list[str],
    *,
    letter: str,
    fold_letter: bool,
    pos_in: tuple[str, ...] | None,
    q: str,
) -> tuple[list[str], list[Any]]:
    """WHERE fragments + params against ``lemma_counts``, shared by the
    main leaderboard query and the header-totals query so the two can't
    drift. ``lemma`` and ``pos`` columns map 1:1 from chunk_lemmas →
    lemma_counts; the query-time guards (letter, pos_in, q, valid
    lemma) apply identically. The freq range is appended by the main
    query only — the header is meant as a scope-wide reference.

    ``scope_values``: empty for corpus (``scope_value IS NULL``), one
    entry for author, one-or-more for work (``scope_value IN (...)`` —
    the per-work rows are summed downstream)."""

    where_parts: list[str] = ["lang = ?", "scope_kind = ?"]
    where_params: list[Any] = [lang, scope_kind]
    if not scope_values:
        # corpus rows carry a NULL scope_value.
        where_parts.append("scope_value IS NULL")
    elif len(scope_values) == 1:
        where_parts.append("scope_value IS ?")
        where_params.append(scope_values[0])
    else:
        placeholders = ",".join("?" * len(scope_values))
        where_parts.append(f"scope_value IN ({placeholders})")
        where_params.extend(scope_values)

    if letter:
        if fold_letter:
            where_parts.append("fold_initial(lemma) = ?")
            where_params.append(_fold_initial(letter))
        else:
            where_parts.append("lemma LIKE ? ESCAPE '\\'")
            where_params.append(letter.replace("\\", "\\\\") + "%")
    if pos_in is not None:
        placeholders = ",".join("?" * len(pos_in))
        where_parts.append(f"pos IN ({placeholders})")
        where_params.extend(pos_in)
    if q:
        # Case-insensitive substring match. LOWER on both sides plays
        # nice with SQLite's collation-free LIKE; we escape the user's
        # wildcard chars so a literal "%" in the search string doesn't
        # blow open the filter.
        escaped = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        where_parts.append("LOWER(lemma) LIKE LOWER(?) ESCAPE '\\'")
        where_params.append(f"%{escaped}%")
    # Lemma-validity guard: matches the same first-char rule we apply
    # at lemmatize time / KWIC. Defense-in-depth — if a partial
    # rebuild ever leaves junk in lemma_counts, the read path skips it.
    where_parts.append(
        "substr(lemma, 1, 1) NOT IN ('-', '+', '''', '\"', '(', '[', '$', '*', '^', '.', ',')"
    )
    where_parts.append("substr(lemma, 1, 1) NOT BETWEEN '0' AND '9'")
    return where_parts, where_params


def _canonical_display(
    lang: str,
    pos: str,
    variants_by_freq: list[str],
) -> str:
    """Pick the display capitalization for a merged variant cluster.

    For German NOUN/PROPN tokens we deliberately *override* the
    most-frequent capitalization with the orthographically canonical
    form (first letter uppercase, remainder lowercase). The Luther
    Bibel uses ``HErr`` / ``GOtt`` / ``HERRN`` as typographic
    flourishes for divine names; they dominate the surface-form
    counts but they're not what a modern reader expects on a
    lemma leaderboard.

    For verbs/adjectives/adverbs in German (and for all other
    languages today) the most-frequent variant wins — that keeps
    Greek minuscule lemmas, Latin accidence, etc. unsurprised.
    """

    if not variants_by_freq:
        return ""
    if lang == "deu" and pos in ("NOUN", "PROPN"):
        # German nouns are always Initial-Cap'd; Python's
        # str.capitalize() does exactly that (first cp upper, rest
        # lower) and handles Umlauts + ß correctly.
        return variants_by_freq[0].capitalize()
    # Default: most-frequent surface wins.
    return variants_by_freq[0]


def _fold_initial(s: str | None) -> str:
    """Fold a string's first character to its base capital letter.

    NFD-decompose the leading code point, drop combining marks, then
    upper-case. This maps polytonic Greek precomposed forms onto their
    bare capital so the concordance letter rail buckets them together:
    ``ἄ`` → ``Α``, ``ὁ`` → ``Ο``, ``Ἀθηνᾶ`` → ``Α``. Registered as a
    SQLite scalar function for the Greek leading-letter filter.

    Returns ``""`` for empty/None input.
    """

    if not s:
        return ""
    decomposed = unicodedata.normalize("NFD", s[0])
    base = "".join(c for c in decomposed if not unicodedata.combining(c))
    return base.upper()


def _corpus_label(lang: str) -> str:
    """Human-readable corpus label for the header. Mirrors common
    German philosophical convention (``DEU`` for the language code in
    monospace UI, ``German`` in prose). We keep the prose form."""

    return {
        "deu": "All German",
        "lat": "All Latin",
        "grc": "All Greek",
        "eng": "All English",
        "fra": "All French",
        "heb": "All Hebrew",
        "ara": "All Arabic",
    }.get(lang, f"All {lang.upper()}")
