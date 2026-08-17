"""Lemma frequency index queries."""

from __future__ import annotations

import functools
import json
import sqlite3
import unicodedata
from typing import Any

from ..errors import BadRequestError
from ..query_params import escape_like_substring, parse_int_param
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
      q          substring filter on the lemma, **diacritic- and
                 case-folded** on both sides (see ``_fold_text``), so
                 ``λογος`` matches ``λόγος`` and ``schroder`` matches
                 ``Schröder`` (#363). Applies to every language, not just
                 Greek. Drives the F1 "find lemma" search field.
                 Trimmed; an empty/whitespace-only value is ignored.
      pos_in     comma-separated POS whitelist; default content words
                 only (NOUN/VERB/ADJ/PROPN). Pass ``all`` to
                 disable the filter and surface function words too.
      sort       freq | alpha | pos  (default: freq)
      limit      default 200, max 1000
      offset     default 0. Page with ``next_offset`` from the response
                 rather than computing it from ``total_lemmas``, which is
                 not a row count — see the note beside it below.
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
        total_lemmas: int,       # NB: not a row count — see `next_offset`
        total_occurrences: int,
        next_offset: int | None, # offset of the next page, None when done
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

    limit = parse_int_param(
        query, "limit", _DEFAULT_INDEX_LIMIT, lo=1, hi=_MAX_INDEX_LIMIT, clamp=True,
    )
    offset = parse_int_param(query, "offset", 0, lo=0, clamp=True)
    min_count = parse_int_param(query, "min_count", 2, lo=1, clamp=True)
    max_count_raw = query.get("max_count")
    max_count: int | None = None
    if max_count_raw not in (None, ""):
        try:
            max_count = int(max_count_raw)
        except ValueError:
            raise BadRequestError("invalid 'max_count' query param") from None
    if max_count is not None and max_count < min_count:
        # Caller passed an inverted range — return zero rows rather than
        # silently swapping or erroring. The UI's slider can land here
        # transiently while the user drags the upper knob below the lower.
        max_count = min_count - 1

    q = (query.get("q") or "").strip()

    _scope_clause(scope, authors, works)  # validates scope/author/work pairing


    # The A–Z rail's letter filter folds diacritics for EVERY language
    # (#381), not just Greek. Greek got the fold first because polytonic
    # lemmas begin with precomposed forms (ἀ / ἄ / Ἀ) and an ASCII
    # ``LIKE 'Α%'`` prefix missed almost all of them — the gap was
    # impossible to overlook. The Latin-script languages have the same gap,
    # just smaller: SQLite's ``LIKE`` is case-insensitive for ASCII only and
    # folds nothing, so ``LIKE 'A%'`` never matched ``Ähnlich``. Measured
    # over the whole live index: 914 German rows, 1,344 French and 571
    # English began with a character that had no rail key at all and were
    # unreachable from the rail.
    #
    # This is also what makes display and filter agree at last. The frontend
    # already folds initials client-side for its alpha-sort section headers
    # (``foldInitial`` in ``Concordance/constants.ts``), so a reader saw
    # ``Ähnlich`` under an ``A`` heading, clicked ``A``, and did not get it.
    #
    # Registered unconditionally now, so it is on the page's own load
    # request. It is `lru_cache`d for the same reason `lower_uni` is.
    conn.create_function("fold_initial", 1, _fold_initial_cached, deterministic=True)
    # The `q` filter folds the whole lemma, for every language rather than just
    # Greek: German umlauts and the eszett want it as much as polytonic accents
    # do, and gating it would mean two `q` semantics to document. Registered
    # only when there is a query, so the callback is never installed on the
    # request the page issues on load. See `_fold_text` for the cost.
    if q:
        conn.create_function("fold_text", 1, _fold_text_cached, deterministic=True)
    # The `merge_case` group key. Unlike `q` this cannot be gated on a
    # request parameter — `merge_case` defaults to on, so the callback is
    # installed on the page's own load request. See `_lower_unicode` for
    # what that costs and why SQL `LOWER()` could not stay.
    if merge_case:
        conn.create_function("lower_uni", 1, _lower_unicode_cached, deterministic=True)

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
        pos_in=pos_in,
        q=q,
    )
    if max_count is not None:
        where_parts.append("count <= ?")
        where_params.append(max_count)
    where_parts.append("count >= ?")
    where_params.append(min_count)

    # Total order, for the reason given on the aggregate branch's clause below.
    # Rows here are per `(lemma, pos)`, so that pair is the unique key. The bare
    # `lemma ASC` after the NOCASE one matters: NOCASE folds ASCII case, so
    # `Gott` and `gott` are distinct rows that compare equal under it.
    order_clause = {
        "freq": "count DESC, lemma COLLATE NOCASE ASC, lemma ASC, pos ASC",
        "alpha": "lemma COLLATE NOCASE ASC, lemma ASC, pos ASC",
        "pos": "pos COLLATE NOCASE ASC, count DESC, lemma COLLATE NOCASE ASC, lemma ASC",
    }[sort]

    if aggregate:
        rows, variants_by_display = _fetch_aggregate_page(
            conn,
            lang=lang,
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

    # ── Totals + rail letter populations ──────────────────────────
    # Two header numbers and the A–Z rail's per-letter counts, over the
    # same scope+filter slice as the rows.
    #
    # They differ in exactly two ways, and the differences are what makes
    # this one function rather than three queries:
    #
    #   * The **frequency range** applies to the rail and not to the
    #     totals. `total_lemmas` is a scope-wide reference the slider is
    #     not supposed to move; a rail dot means "clicking here returns
    #     rows", so it has to agree with the rows. That is a `SUM(CASE …)`
    #     over one grouped scan rather than a second scan.
    #   * The **letter predicate** applies to the totals and not to the
    #     rail, which must keep showing where else there is something
    #     while one letter is selected. When no letter is selected the two
    #     WHERE clauses are identical and one scan serves both — the
    #     default view, and the reason this is worth the shape. Measured
    #     on the deu corpus partition: 116 ms + 127 ms as two scans
    #     against 148 ms as one.
    #
    # The lemma-search `q` applies to both, so a search for "geist" does
    # not show "1.9M occurrences" next to 4 rows.
    #
    # One grouping expression covers every branch. It used to be three,
    # and the odd one out counted `DISTINCT lemma` while its rows were per
    # `(lemma, pos)` (#377); with that corrected, `merge_case` off is just
    # `group_expr = "lemma"` and the branches collapse.
    conn.create_function("fold_initial", 1, _fold_initial_cached, deterministic=True)
    group_expr = _lemma_group_expr(merge_case=merge_case)
    letter_expr = _letter_key_expr("lemma_key")

    def _scan(parts: list[str], params: list[Any]) -> list[sqlite3.Row]:
        """One grouped pass: per-letter totals, and per-letter counts
        inside the frequency range."""
        freq_parts = ["n >= ?"]
        freq_params: list[Any] = [min_count]
        if max_count is not None:
            freq_parts.append("n <= ?")
            freq_params.append(max_count)
        sql = f"""
            SELECT {letter_expr} AS letter,
                   COUNT(*) AS n_lemmas,
                   COALESCE(SUM(n), 0) AS n_tokens,
                   SUM(CASE WHEN {" AND ".join(freq_parts)} THEN 1 ELSE 0 END)
                       AS n_in_range
            FROM (
                SELECT {group_expr} AS lemma_key, pos, SUM(count) AS n
                FROM lemma_counts
                WHERE {" AND ".join(parts)}
                GROUP BY lemma_key, pos
            )
            GROUP BY letter
        """
        # Freq params FIRST: the `CASE` sits in the SELECT list, which
        # precedes the WHERE in the statement text, and SQLite binds `?`
        # by position in that text.
        return conn.execute(sql, [*freq_params, *params]).fetchall()

    totals_where_parts, totals_where_params = _counts_where(
        lang, scope_kind, scope_values,
        letter=letter, pos_in=pos_in, q=q,
    )
    totals_rows = _scan(totals_where_parts, totals_where_params)
    total_lemmas = sum(int(r["n_lemmas"]) for r in totals_rows)
    total_tokens = sum(int(r["n_tokens"]) for r in totals_rows)

    if letter:
        rail_where_parts, rail_where_params = _counts_where(
            lang, scope_kind, scope_values,
            letter="", pos_in=pos_in, q=q,
        )
        rail_rows = _scan(rail_where_parts, rail_where_params)
    else:
        rail_rows = totals_rows
    letter_counts = {
        r["letter"]: int(r["n_in_range"])
        for r in rail_rows
        if r["letter"] and int(r["n_in_range"] or 0) > 0
    }

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

    # Pagination cursor (#371). Derived from the rows actually returned, NOT
    # from `total_lemmas` — unlike the KWIC endpoint, which can do
    # `offset + limit < total` because its total describes its rows.
    # `total_lemmas` here does not: it is computed without the frequency range
    # applied (see the note above the totals query), and on the non-aggregate
    # branch it counts DISTINCT lemma while rows are per (lemma, pos). A cursor
    # built on it would keep requesting pages that come back empty, or stop
    # before the end.
    #
    # A full page means "there may be more"; a short one means "that was the
    # last". The cost is one extra request when the final page is exactly full,
    # which is the standard trade and cheaper than being wrong.
    next_offset = offset + len(out_rows) if len(out_rows) == limit else None

    return {
        "scope": scope,
        "scope_label": scope_label,
        "lang": lang,
        "letter": letter or None,
        "sort": sort,
        "total_lemmas": total_lemmas,
        "total_occurrences": total_tokens,
        "letter_counts": letter_counts,
        "limit": limit,
        "offset": offset,
        "next_offset": next_offset,
        "rows": out_rows,
    }


def _lemma_group_expr(*, merge_case: bool) -> str:
    """The ``GROUP BY`` key ``merge_case`` collapses variants on.

    One expression for every language. It used to be two, and both were
    wrong: ``LOWER(lemma)`` is ASCII-only so non-ASCII case variants
    stayed split (#373), and Greek took ``fold_initial(lemma)`` — a
    *single character* — so every Greek lemma sharing an initial and a
    POS collapsed into one row (#366). ``fold_initial`` keeps its real
    job, the A–Z letter rail's WHERE clause; it was only ever reused
    here on the strength of its name.
    """

    return "lower_uni(lemma)" if merge_case else "lemma"


def _letter_key_expr(col: str = "lemma") -> str:
    """The A–Z rail's bucket for ``col``.

    Deliberately the same key the ``letter`` filter matches on, so a dot on
    the rail means "clicking here returns rows" rather than something close
    to it. One expression for every language since #381: ``fold_initial``,
    which is what ``grc`` always used.

    It used to branch, and the non-Greek arm broke the invariant this
    docstring claims. ``UPPER(SUBSTR(col, 1, 1))`` was chosen to bucket
    "exactly what ``LIKE 'A%'`` matches", but the two ran on *different
    strings*: this key is computed on ``lemma_key`` (i.e. ``lower_uni(lemma)``
    when ``merge_case`` is on) while the filter ran ``LIKE`` against raw
    ``lemma``. So ``Ähnlich`` bucketed under ``ä`` — a key the rail does not
    have — while ``letter=Ä`` matched rows the rail reported as zero. Both
    sides now fold, so both sides agree, and every bucket is a rail key.
    """

    return f"fold_initial({col})"


def _fetch_aggregate_page(
    conn: sqlite3.Connection,
    *,
    lang: str,
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

    group_expr = _lemma_group_expr(merge_case=merge_case)
    having_parts = ["SUM(count) >= ?"]
    having_params: list[Any] = [min_count]
    if max_count is not None:
        having_parts.append("SUM(count) <= ?")
        having_params.append(max_count)

    # Every clause ends on a key combination unique per row, because
    # `LIMIT/OFFSET` over a partial order is unsound: tied rows are
    # interchangeable, so a page boundary can serve one twice and its partner
    # never. `pos` is in the GROUP BY, so `(lemma_key, pos)` identifies a row —
    # naming it last makes each sort total.
    #
    # Measured: 805 groups in the German corpus partition tie on the whole `freq`
    # key `(n, lemma_key)` and differ only in `pos` — `rechtschaffen` ADJ/VERB
    # both at 47, `zween` NOUN/VERB both at 29. Nothing had noticed because
    # nothing sent an `offset` (#371).
    #
    # This is hardening on principle, not a fix for an observed duplicate: no
    # page boundary has been caught mis-serving a tie. A 200-row walk of that
    # index DOES surface `('Übergehen', 'NOUN')` twice, but that turned out to be
    # a different defect — SQLite's `LOWER()` is ASCII-only, so `merge_case`
    # leaves umlaut-initial variants in separate groups that then render the same
    # display label — #373.
    order_clause = {
        "freq": "n DESC, lemma_key COLLATE NOCASE ASC, pos ASC",
        "alpha": "lemma_key COLLATE NOCASE ASC, pos ASC",
        "pos": "pos COLLATE NOCASE ASC, n DESC, lemma_key COLLATE NOCASE ASC",
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
        # Folded equality for every language since #381 — see
        # `_letter_key_expr`. Both sides go through the same `_fold_initial`,
        # via the SQL function on the column and directly on the parameter,
        # so the two cannot drift.
        #
        # This also retires #120's escaping concern for `letter` rather than
        # working around it: an equality test on a folded single character
        # has no pattern syntax to abuse, so a `letter` of `%` or `_` now
        # matches nothing instead of needing `escape_like_substring` to stop
        # it matching the whole index. The `q` filter still needs that
        # escape, and still has it.
        where_parts.append("fold_initial(lemma) = ?")
        where_params.append(_fold_initial(letter))
    if pos_in is not None:
        placeholders = ",".join("?" * len(pos_in))
        where_parts.append(f"pos IN ({placeholders})")
        where_params.extend(pos_in)
    if q:
        # Diacritic- and case-folded substring match (#363), so `λογος` finds
        # `λόγος` and `schroder` finds `Schröder`. Both sides go through the
        # same `_fold_text`, via the SQL function on the column and directly on
        # the parameter, so the two cannot drift.
        #
        # `escape_like_substring` is applied AFTER the fold. Either order works
        # today — NFD + upper-casing cannot emit `%`, `_` or `\` — but escaping
        # last means #120's invariant does not depend on that staying true.
        where_parts.append("fold_text(lemma) LIKE ? ESCAPE '\\'")
        where_params.append(f"%{escape_like_substring(_fold_text(q))}%")
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


def _fold_text(s: str | None) -> str:
    """Fold a whole string to its base capital letters.

    NFD-decompose, drop combining marks, then upper-case. Diacritics and
    case both stop mattering, which is what lets ``q=λογος`` find
    ``λόγος`` and ``q=schroder`` find ``Schröder`` (#363).

    Note this is *not* interchangeable with SQL ``LOWER()``, which is
    ASCII-only — measured, ``SELECT lower('ΛΟΓΟΣ')`` returns the string
    unchanged, so the ``q`` filter was case-sensitive for every
    non-Latin script in the corpus before this.

    Two behaviours worth knowing: ``ß`` expands to ``SS`` under
    upper-casing, so ``Strasse`` and ``Straße`` fold together; and
    lunate sigma ``ϲ`` upper-cases to ``Ϲ`` rather than ``Σ``, so it does
    not fold with ``σ`` (3 rows in the whole corpus — not worth a case).

    Returns ``""`` for empty/None input.
    """

    if not s:
        return ""
    decomposed = unicodedata.normalize("NFD", s)
    base = "".join(c for c in decomposed if not unicodedata.combining(c))
    return base.upper()


# The SQL-callback path only. `q` is a substring match, so the predicate is
# `LIKE '%…%'` and cannot seek an index — measured with EXPLAIN QUERY PLAN, the
# index seek covers `(lang, scope_kind, scope_value)` and the LIKE is a residual
# filter, i.e. this already scanned the partition before the fold existed. So
# the fold's whole cost is a Python callback per row over up to 165,049 rows
# (the largest corpus partition, deu). Memoizing it takes that from 5.1x the C
# built-in to ~1.3x, because the vocabulary is tiny next to the row count.
# Bounded rather than unbounded: the full 596,351-lemma corpus vocabulary
# measures 48.7 MB cached, and this connection is long-lived.
_fold_text_cached = functools.lru_cache(maxsize=200_000)(_fold_text)


def _lower_unicode(s: str | None) -> str:
    """Lower-case a lemma for the ``merge_case`` group key.

    Python's ``str.lower()`` rather than SQL ``LOWER()``, which is
    ASCII-only: measured, ``SELECT lower('Übergehen')`` returns the
    string unchanged, so ``Übergehen`` and ``übergehen`` were two groups
    that then rendered the *same* display label at different ranks —
    113 such pairs in the German corpus partition (#373).

    Deliberately **not** ``_fold_text``. That drops combining marks,
    which is right for the ``q`` search box and wrong for a group key:
    it merges ``Abdruck`` with ``Abdrück``, and in Greek — where accent
    is lexical rather than typographic — it collapses a further 8,228
    groups. Measured over the live index, folding diacritics here would
    break 7,705 German and French groups to fix 113.

    Case is the whole job, because case is the whole of what
    ``merge_case`` claims to merge.
    """

    return (s or "").lower()


# One callback per row of an already-narrowed partition, same shape as
# `_fold_text_cached` above and memoized for the same reason: the
# vocabulary is tiny next to the row count. Measured on the largest
# partition (deu, 165,049 rows), a 200-row freq page costs 166.3 ms with
# SQL `LOWER(lemma)` and 197.5 ms with this — +19%, and unlike `q` this
# one is installed on the request the page issues on load, because a
# group key runs on every request.
_lower_unicode_cached = functools.lru_cache(maxsize=200_000)(_lower_unicode)


def _fold_initial(s: str | None) -> str:
    """Fold a string's first character to its base capital letter.

    ``ἄ`` → ``Α``, ``ὁ`` → ``Ο``, ``Ἀθηνᾶ`` → ``Α``, and since #381 the
    Latin-script cases too: ``Ähnlich`` → ``A``, ``über`` → ``U``. The
    concordance letter rail buckets on this and its ``letter`` filter matches
    on it, which is what makes every bucket a rail key.

    Truncated to one character AFTER folding, which is not redundant: ``ß``
    upper-cases to ``SS`` (German eszett expands), and a two-character bucket
    is not on a 26-key rail — so a ``ß``-initial lemma would be unreachable
    without the trailing slice. Every other case folds 1→1, so this is a
    no-op for them, Greek included.
    """

    return _fold_text(s[:1] if s else s)[:1]


# Memoized for the same reason `_lower_unicode_cached` is, and it matters more
# here than it did when this was Greek-only: since #381 the letter key runs on
# every language's page-load request, not just `grc`'s. The cache is far more
# effective than the other two — the key space is the 26-key rail plus a short
# tail, so after the first rows every call is a hit regardless of vocabulary
# size.
_fold_initial_cached = functools.lru_cache(maxsize=200_000)(_fold_initial)


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
