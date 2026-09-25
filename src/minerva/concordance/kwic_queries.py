"""Lemma detail / KWIC queries."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from ..errors import BadRequestError
from ..query_params import escape_like_substring, parse_int_param
from ..reader.queries import _parse_morph_feats, work_sort_key
from ..text import build_kwic
from ._scope import (
    _DEFAULT_KWIC_LIMIT,
    _KWIC_CONTEXT_RADIUS,
    _MAX_KWIC_LIMIT,
    _scope_clause,
    parse_authors,
    parse_works,
)
from .index_queries import _corpus_label, _lower_unicode

# Feature keys the `morph=` filter will accept.
#
# Derived from the corpus, NOT from the UD spec — the two differ, and the
# spec is the wrong authority here. The lemmatizers write language-specific
# keys that no UD feature table lists (`HebBinyan` from the Hebrew Stanza
# model; `ConjType`, `VerbType`, `AdpType` from the LatinCy/spaCy models),
# so validating against textbook UD would reject 80k+ rows of real data.
#
# Regenerate after adding a language or changing lemmatizer models:
#
#     sqlite3 data/index.sqlite "
#       SELECT DISTINCT substr(x.value, 1, instr(x.value,'=')-1)
#       FROM chunk_lemmas, json_each('[\"' || replace(feats,'|','\",\"') || '\"]') x
#       WHERE feats IS NOT NULL AND feats <> ''"
#
# A key present in the data but missing here becomes a 400, which is loud
# and easy to spot — the failure mode this replaces (silent zero rows) was
# not. Ordered by corpus frequency.
_MORPH_FEATURE_KEYS = frozenset(
    {
        "Number",
        "Gender",
        "Case",
        "VerbForm",
        "PronType",
        "Person",
        "Tense",
        "Mood",
        "Definite",
        "Voice",
        "Aspect",
        "Degree",
        "ConjType",
        "Poss",
        "Polarity",
        "Reflex",
        "NumType",
        "HebBinyan",
        "VerbType",
        "Foreign",
        "AdpType",
        "PunctType",
        "Abbr",
        "Hyph",
        "PunctSide",
        "ExtPos",
        "Prefix",
    }
)


# How a token's language is decided, for every query in this module.
#
# `chunk_lemmas.lang` (migration 0032) is NULL for an ordinary same-script
# token and carries an explicit code for a cross-script run — an embedded
# Latin phrase inside a `grc` chunk, tagged 'lat' by the lemmatizer. #430
# taught `lemma_counts` to count that run as Latin vocabulary; the read
# path behind the click kept matching on the chunk's own language, so
# 2,869 leaderboard cells listed a count and returned no rows (#644).
# One rule, and the two agree by construction.
#
# The rule is `COALESCE(cl.lang, chunks.lang)`, stored resolved in
# `cl.lang_resolved` by migration 0036 and kept current by its triggers.
# Computing it here instead forced a probe into `chunks` for every matching
# row, which was the whole cost of this endpoint (#649).
_LANG_MATCH = "cl.lang_resolved = ?"


def lemma_detail(conn: sqlite3.Connection, query: dict[str, str]) -> dict[str, Any]:
    """For one lemma, return all occurrence rows with KWIC snippets.

    Query params:
      lemma       (required) the lemma to look up — case-sensitive,
                  matches ``chunk_lemmas.lemma`` exactly. Should be
                  the form the lemmatizer produced (NFC-normalised).
      lang        (required) ISO-639-3 code
      scope       corpus | author | work (default: corpus)
      author      required when scope=author
      work        required when scope=work
      pos         optional POS filter (e.g. ``NOUN``)
      morph       optional morphology filter as ``Key=Val,Key=Val``,
                  e.g. ``Case=Nom,Number=Sing``. All keys must match.
      surface     optional exact surface-form filter
      limit       default 50, max 200
      offset      default 0
      radius      KWIC context chars on each side (default 60, max 240)

    Response:
      {
        lemma: "Geist",
        scope: "work",
        scope_label: "Phänomenologie des Geistes",
        total: 312,
        pos_breakdown: { "NOUN": 312 },
        case_breakdown: { "Nom": 180, "Gen": 60, "Dat": 50, "Akk": 22 },
        surface_breakdown: { "Geist": 208, "Geistes": 80, "Geiste": 24 },
        rows: [
          {
            chunk_id: "...",
            section: "Vorrede, ¶17",
            book: "Vorrede",
            work: "Phänomenologie des Geistes",
            author: "Hegel",
            ord: 17,
            surface: "Geist",
            pos: "NOUN",
            morph: { Case: "Nom", Number: "Sing", Gender: "Masc" },
            morph_str: "Nom · Sg · Mask",
            kwic_left: "...substanz wesentlich",
            kwic_match: "Geist",
            kwic_right: "sei, drückt diejenige Vorstellung aus...",
          },
          ...
        ],
        next_offset: 50 | null,
      }
    """

    lemma = query.get("lemma")
    if not lemma:
        raise BadRequestError("'lemma' query param is required")
    lang = query.get("lang")
    if not lang:
        raise BadRequestError("'lang' query param is required")
    scope = query.get("scope", "corpus")
    authors = parse_authors(query)
    works = parse_works(query)
    pos = query.get("pos")
    morph_str = query.get("morph") or ""
    surface = query.get("surface")
    # When ON (default), the lemma match folds case so e.g. clicking
    # "Herr" in the leaderboard fetches HErr+Herr+HERR+HERRN. Pass
    # merge_case=0 to retrieve only exact-lemma occurrences.
    merge_case = query.get("merge_case", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )

    limit = parse_int_param(
        query,
        "limit",
        _DEFAULT_KWIC_LIMIT,
        lo=1,
        hi=_MAX_KWIC_LIMIT,
        clamp=True,
    )
    offset = parse_int_param(query, "offset", 0, lo=0, clamp=True)
    radius = parse_int_param(
        query,
        "radius",
        _KWIC_CONTEXT_RADIUS,
        lo=20,
        hi=240,
        clamp=True,
    )

    morph_filters: dict[str, str] = {}
    for part in morph_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise BadRequestError(
                f"morph filter must be Key=Val, got {part!r}",
            )
        k, _, v = part.partition("=")
        k, v = k.strip(), v.strip()
        # Reject unknown feature keys. Without this a typo (`Casee=Nom`)
        # and a genuinely-absent form (`Case=Nomm`) both return zero rows,
        # indistinguishable from "this lemma has no such forms" — which
        # makes client bugs invisible. #120 escaped the key and value so
        # `?morph=Case=%` no longer widens the filter; this is the
        # separate validation half that escaping doesn't provide.
        if k not in _MORPH_FEATURE_KEYS:
            raise BadRequestError(
                f"unknown morph feature {k!r}; expected one of: "
                + ", ".join(sorted(_MORPH_FEATURE_KEYS))
            )
        morph_filters[k] = v

    scope_sql, scope_params = _scope_clause(scope, authors, works)
    work_label = works[0] if len(works) == 1 else f"{len(works)} works"
    author_label = authors[0] if len(authors) == 1 else f"{len(authors)} authors"

    # Lemma-match SQL fragment. When merge_case is on, fold to lower
    # so ``Herr`` matches ``HErr`` / ``HERR`` / ``HERRN`` etc. We
    # apply ``LOWER`` to both sides — Python casefold() isn't
    # available in SQLite but LOWER handles all the ASCII-only
    # capitalization variants the Lutheran convention produces.
    # Use the stored ``lemma_fold`` column (migration 0018) for the
    # case-folded path so the KWIC seek hits the ``lemma_fold``-led
    # indexes of migration 0036 instead of forcing a full chunks scan via
    # ``LOWER(cl.lemma) = LOWER(?)``. The exact-match path stays on
    # ``cl.lemma`` — the primary lemma index already covers it.
    lemma_match_sql = "cl.lemma_fold = LOWER(?)" if merge_case else "cl.lemma = ?"

    extra_sql, extra_params = _filter_sql("cl", pos, surface, morph_filters)

    # One grouped pass yields the filtered total *and* the four
    # unfiltered breakdowns. The five aggregate queries this replaces
    # each carried the identical FROM/WHERE, so one request paid the
    # lemma seek and the per-row join into `chunks` six times over —
    # 733 ms for `haben`/deu, 3.6 s for `der`/deu (#643).
    breakdowns, total, groups = _lemma_aggregates(
        conn,
        lemma,
        lang,
        scope_sql,
        scope_params,
        lemma_match_sql,
        _filter_sql("g", pos, surface, morph_filters)[0],
        extra_params,
    )
    if total == 0:
        # Empty result — the breakdowns above describe the *unfiltered*
        # scope, so the empty-state UI can still suggest broadening
        # moves (the wireframe's F6 "Drop Number — 3 hits" affordance).
        return {
            "lemma": lemma,
            "lang": lang,
            "scope": scope,
            "scope_label": {
                "corpus": _corpus_label(lang),
                "author": author_label,
                "work": work_label,
            }[scope],
            "filters": {
                "pos": pos,
                "morph": morph_filters,
                "surface": surface,
            },
            "total": 0,
            "limit": limit,
            "offset": offset,
            **breakdowns,
            "rows": [],
            "next_offset": None,
        }

    # The page, in two steps. First its rows are chosen as `chunk_lemmas`
    # rowids, in reading order, from the counts the aggregate pass already
    # returned (`_page_rowids`). Then those rows alone are joined to
    # chunks_full for section/work/author and the text the KWIC snippet is
    # cut from. Joining first meant probing `chunks` for every matching row,
    # 671,411 of them for `der`, to keep 50 (#649).
    where = _Where(lang, lemma, lemma_match_sql, scope_sql, scope_params, extra_sql, extra_params)
    works = _work_counts(groups, filtered=bool(extra_sql))
    rowids = _page_rowids(
        conn,
        where,
        works,
        offset=offset,
        limit=limit,
        facet_range=_facet_range_for(conn, where, groups, scope, pos, surface)
        if extra_sql and merge_case
        else None,
    )
    page = _page_details(conn, rowids)

    out: list[dict[str, Any]] = []
    for r in page:
        morph = _parse_morph_feats(r["feats"])
        kwic = build_kwic(r["text"], r["s_start"], r["s_end"], radius)
        out.append(
            {
                "chunk_id": r["chunk_id"],
                "section": r["section"] or "",
                "book": r["book"] or "",
                "work": r["work"] or "",
                "author": r["author"] or "",
                "ord": int(r["ord"]) if r["ord"] is not None else 0,
                "surface": r["surface"],
                "pos": r["pos"] or "",
                "morph": morph,
                "morph_str": _morph_short(morph),
                **kwic,
            }
        )

    next_offset = offset + limit if offset + limit < total else None

    return {
        "lemma": lemma,
        "lang": lang,
        "scope": scope,
        "scope_label": {"corpus": _corpus_label(lang), "author": author_label, "work": work_label}[
            scope
        ],
        "filters": {
            "pos": pos,
            "morph": morph_filters,
            "surface": surface,
        },
        "total": total,
        "limit": limit,
        "offset": offset,
        **breakdowns,
        "rows": out,
        "next_offset": next_offset,
    }


def _filter_sql(
    alias: str, pos: str | None, surface: str | None, morph_filters: dict[str, str]
) -> tuple[str, list[Any]]:
    """The request's `pos`/`surface`/`morph` filter as ` AND …` terms on
    ``alias``, which is either a `chunk_lemmas` row or an aggregate group:
    both carry the three columns under the same names."""

    sql = ""
    params: list[Any] = []
    if pos:
        sql += f" AND {alias}.pos = ?"
        params.append(pos)
    if surface:
        sql += f" AND {alias}.surface_form = ?"
        params.append(surface)
    # spaCy feats stored as ``Key=Val|Key=Val``; a string-contains
    # match is faster than parsing every row in SQL. We require all
    # requested features to appear as substrings.
    # `morph` is free-form beyond its Key=Val shape check, so the key
    # and value are escaped — an unescaped `%` would widen the match
    # to "any row carrying this feature" instead of narrowing it (#120).
    for k, v in morph_filters.items():
        sql += f" AND {alias}.feats LIKE ? ESCAPE '\\'"
        params.append(f"%{escape_like_substring(k)}={escape_like_substring(v)}%")
    return sql, params


def _lemma_aggregates(
    conn: sqlite3.Connection,
    lemma: str,
    lang: str,
    scope_sql: str,
    scope_params: list[Any],
    lemma_match_sql: str,
    group_filter_sql: str,
    filter_params: list[Any],
) -> tuple[dict[str, Any], int, list[sqlite3.Row]]:
    """One grouped pass over a lemma's rows → (breakdowns, total, groups).

    ``groups`` is the grouped rows themselves, one per
    ``(pos, surface, feats, work)``. The page is planned from them: which
    works it touches, how far into each, and which index to read (#656,
    #657).

    Returns the pos/case/number/gender/surface/work breakdowns under the
    **unfiltered** scope — they drive the filter rail's facet counts and
    the F6 empty-state's "drop filter X for N hits" suggestions — and the
    total under the **filtered** one.

    Those two scopes are why this is not simply ``SUM(n)``. The group key
    is ``(pos, surface_form, feats, work)``, and ``pos`` / ``surface`` /
    ``morph`` are the only filters this endpoint accepts — so every filter
    lands on a column already in the key, and the filtered total is a
    sub-sum of the same groups. ``group_filter_sql`` is that filter on the
    group (`g.`) rather than on the row, and SQLite evaluates it once per
    group in the outer SELECT, so `LIKE`'s semantics (ASCII-case-
    insensitive, and `%`/`_` escaped by the caller) stay in one place.
    Evaluated per row inside the grouping, as it first was, it ran 671,411
    times for `der`/deu instead of 16,075, and cost 14–40 ms of a ~58 ms
    pass (#666).

    Group cardinality is what makes the Python-side fold affordable, and
    it was measured rather than assumed: the busiest lemma in each
    language yields thousands of groups (16,075 for `der`/deu, 16,604 for
    grc `ὁ`, measured 2026-09-25), over far fewer distinct `feats` strings
    (143 and 159), which is why the fold parses each string once.
    """

    # The `CASE` sits in the SELECT list, which precedes the WHERE in the
    # statement text, and SQLite binds `?` by position in that text — so
    # the filter params bind FIRST. Same ordering trap as the concordance
    # totals query.
    filtered_col = ""
    lead_params: list[Any] = []
    if group_filter_sql:
        filtered_col = f", CASE WHEN 1=1{group_filter_sql} THEN g.n ELSE 0 END AS n_filtered"
        lead_params = list(filter_params)

    # Grouped on the lemma row's own `work_id`, then joined to `works` once
    # per group for the title. Every grouped column is in
    # `chunk_lemmas_by_facet`, so the pass never leaves that index — 1,176 ms
    # for `der` through `chunks_full`, 57 ms this way (#649). Two works that
    # share a title (the two Luther Bibles) now arrive as two groups instead
    # of one; the fold below sums by title, so the breakdowns are unchanged.
    rows = conn.execute(
        f"""
        SELECT g.pos, g.surface_form AS surface, g.feats, g.work_id, w.title AS work,
               w.author, g.n{filtered_col}
        FROM (
            SELECT cl.pos          AS pos,
                   cl.surface_form AS surface_form,
                   cl.feats        AS feats,
                   cl.work_id      AS work_id,
                   COUNT(*)        AS n
            FROM chunk_lemmas cl
            WHERE {_LANG_MATCH} AND {lemma_match_sql}{scope_sql}
            GROUP BY 1, 2, 3, 4
        ) g
        JOIN works w ON w.id = g.work_id
        """,
        [*lead_params, lang, lemma, *scope_params],
    ).fetchall()

    breakdowns = _fold_breakdowns(rows)
    total = sum(_matches(r, filtered=bool(group_filter_sql)) for r in rows)
    return breakdowns, total, rows


def _matches(group: sqlite3.Row, *, filtered: bool) -> int:
    """The rows of one aggregate group that the request's filters keep."""

    return int(group["n_filtered"] or 0) if filtered else int(group["n"])


def _fold_breakdowns(rows: list[sqlite3.Row]) -> dict[str, Any]:
    """The facet rail's breakdowns, summed from the grouped rows."""

    pos_b: dict[str, int] = {}
    surface_b: dict[str, int] = {}
    feats_b: dict[str, int] = {}
    work_b: dict[str, int] = {}
    for r in rows:
        n = int(r["n"])
        # The empty-string guards mirror the `IS NOT NULL AND != ''`
        # predicates the four separate queries carried: a token with no
        # POS is not a POS bucket of its own.
        if r["pos"]:
            pos_b[r["pos"]] = pos_b.get(r["pos"], 0) + n
        if r["surface"]:
            surface_b[r["surface"]] = surface_b.get(r["surface"], 0) + n
        if r["feats"]:
            feats_b[r["feats"]] = feats_b.get(r["feats"], 0) + n
        work_b[r["work"]] = work_b.get(r["work"], 0) + n
    case_b, number_b, gender_b = _morph_breakdowns(feats_b)

    def _top(d: dict[str, int], n: int = 12) -> list[dict[str, Any]]:
        # Ties break on the value, not on scan order. Sorting by count
        # alone left the order of equal counts to the order SQLite
        # happened to emit the groups in — stable in practice, arbitrary
        # in principle, and it silently changed when the five separate
        # GROUP BYs became one. `Geist` has six surface variants tied at
        # 1 and 3 occurrences; which of them the top-12 shows was already
        # unspecified, and now it is not.
        return [
            {"value": k, "count": v}
            for k, v in sorted(d.items(), key=lambda x: (-x[1], x[0]))[:n]
        ]

    return {
        "pos_breakdown": _top(pos_b),
        "case_breakdown": _top(case_b),
        "number_breakdown": _top(number_b),
        "gender_breakdown": _top(gender_b),
        "surface_breakdown": _top(surface_b),
        "work_breakdown": _top(work_b, n=20),
    }


def _morph_breakdowns(
    feats_counts: dict[str, int],
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    """Case/Number/Gender buckets from per-`feats`-string counts, parsing
    each distinct string once: `der`/deu's 16,075 groups carry 143 (#666)."""

    case_b: dict[str, int] = {}
    number_b: dict[str, int] = {}
    gender_b: dict[str, int] = {}
    for raw, n in feats_counts.items():
        feats = _parse_morph_feats(raw)
        for key, bucket in (("Case", case_b), ("Number", number_b), ("Gender", gender_b)):
            if key in feats:
                bucket[feats[key]] = bucket.get(feats[key], 0) + n
    return case_b, number_b, gender_b


# ──────────────────────────────────────────────────────────────────
#  Choosing the page's rows (#656, #657)
# ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Where:
    """The lemma/lang/scope/filter predicate, shared by every page statement."""

    lang: str
    lemma: str
    lemma_match_sql: str
    scope_sql: str
    scope_params: list[Any]
    extra_sql: str
    extra_params: list[Any]


@dataclass(frozen=True)
class _WorkCount:
    work_id: int
    rank: tuple[Any, ...]
    rows: int  # the lemma's rows in this work, before the filters
    matches: int  # the rows the filters keep


def _work_counts(groups: list[sqlite3.Row], *, filtered: bool) -> list[_WorkCount]:
    """Per-work totals from the aggregate groups, in reading order.

    Reading order is the Reader's (`work_sort_key`): author chronology, then
    each author's canon or titles (#656). It cannot come from an index,
    because it is a Python table, so the page is planned from these counts
    instead. `work_id` ends the rank so two works that compare equal (the two
    Luther Bibles share every book title, at different ordinals, but an
    unlisted author could tie) still order totally.
    """

    acc: dict[int, list[Any]] = {}
    for g in groups:
        a = acc.setdefault(g["work_id"], [g["author"], g["work"], 0, 0])
        a[2] += int(g["n"])
        a[3] += _matches(g, filtered=filtered)
    works = [
        _WorkCount(wid, (*work_sort_key(author, title), wid), n, m)
        for wid, (author, title, n, m) in acc.items()
        if m > 0
    ]
    works.sort(key=lambda w: w.rank)
    return works


def _slice_works(
    works: list[_WorkCount], offset: int, limit: int
) -> list[tuple[_WorkCount, int, int]]:
    """The page as `(work, offset into it, rows to take)`, walking works in
    order and skipping whole works that end before `offset`."""

    out: list[tuple[_WorkCount, int, int]] = []
    for w in works:
        if limit <= 0:
            break
        if offset >= w.matches:
            offset -= w.matches
            continue
        take = min(limit, w.matches - offset)
        out.append((w, offset, take))
        limit -= take
        offset = 0
    return out


def _walk_length(page: list[tuple[_WorkCount, int, int]]) -> int:
    """Expected locator-index entries a filtered walk visits for this page:
    in each work, as far as its last wanted match, assuming matches are
    spread evenly through the work's rows — and never more than all of them."""

    return sum(min(w.rows, -(-(off + take) * w.rows // w.matches)) for w, off, take in page)


def _facet_range(groups: list[sqlite3.Row], pos: str | None, surface: str | None) -> int:
    """Entries in the `chunk_lemmas_by_facet` range a filtered page reads.

    The index is `(lemma_fold, lang_resolved, pos, surface_form, feats, …)`,
    so `pos`, and `surface` after it, narrow the seek. A `surface` without
    `pos`, or any `morph`, is checked on every entry of the lemma's range.
    """

    return sum(
        int(g["n"])
        for g in groups
        if not pos or (g["pos"] == pos and (not surface or g["surface"] == surface))
    )


def _facet_range_for(
    conn: sqlite3.Connection,
    where: _Where,
    groups: list[sqlite3.Row],
    scope: str,
    pos: str | None,
    surface: str | None,
) -> int:
    """`_facet_range` for any scope.

    At corpus scope the groups are the whole range. A scoped request's groups
    count only its own works, but the facet seek has no `work_id` ahead of the
    filter columns and reads the lemma's range across every work, so the size
    comes from `lemma_counts` instead (#665). The scope's own count is a lower
    bound on it, and it stands in when `lemma_counts` has not been built.
    """

    in_scope = _facet_range(groups, pos, surface)
    if scope == "corpus":
        return in_scope
    return max(in_scope, _corpus_facet_range(conn, where.lang, where.lemma, pos=pos))


def _corpus_facet_range(conn: sqlite3.Connection, lang: str, lemma: str, *, pos: str | None) -> int:
    """The lemma's corpus-wide rows, under the KWIC fold, from `lemma_counts`.

    `lemma_key` is Python's Unicode `lower()`, and the KWIC match is SQL's
    ASCII-only `LOWER`, which never merges more. So the seek on the key is a
    superset and the `LOWER` check trims it to the KWIC match exactly.
    Without `pos` this is the whole range. With `pos` it is the `pos` range,
    which overstates a `surface` seek within it. A larger range only makes the
    walk look cheaper, so the rule errs towards the path it took before.
    `lemma_counts` skips untagged rows, so it can undercount.
    """

    pos_sql = " AND pos = ?" if pos else ""
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(count), 0) FROM lemma_counts
        WHERE lang = ? AND scope_kind = 'corpus' AND scope_value IS NULL
          AND lemma_key = ? AND LOWER(lemma) = LOWER(?){pos_sql}
        """,
        [lang, _lower_unicode(lemma), lemma, *([pos] if pos else [])],
    ).fetchone()
    return int(row[0])


# Microseconds per unit of work, measured on the live index (`der`/deu,
# 671,411 rows, warm, #657's prototype). A filtered locator walk checks each
# entry on its table row: 266 ms for all 671,411. A facet range read is index
# only: 45 ms for the same count. Each facet match then fetches `chunk_ord`
# and `surface_start` from its row: 104 ms for 85,934 `PRON` matches.
_US_PER_WALKED = 0.4
_US_PER_SCANNED = 0.07
_US_PER_MATCH = 1.1


def _prefer_facet(*, matches: int, walked: int, scanned: int) -> bool:
    """Whether reading every match from the facet index beats walking.

    The walk stops after the page's last match, so it wins whenever matches
    are common (`pos=PRON`: a ~390-entry walk against 85,934 match reads). The
    facet read wins when they are rare and the walk would visit nearly every
    entry to find them (`pos=NOUN`: 37 matches, 266 ms walking, ~0 ms here).
    """

    facet = scanned * _US_PER_SCANNED + matches * _US_PER_MATCH
    return facet < walked * _US_PER_WALKED


def _page_rowids(
    conn: sqlite3.Connection,
    where: _Where,
    works: list[_WorkCount],
    *,
    offset: int,
    limit: int,
    facet_range: int | None,
) -> list[int]:
    """The page's `chunk_lemmas` rowids, in reading order.

    Two access paths. The default seeks `chunk_lemmas_by_locator` once per
    work the page touches, walked in paragraph order with no sort. When the
    request is filtered and the filter is rare, it reads every match from
    `chunk_lemmas_by_facet` instead and sorts them here. `facet_range` is
    None when that path is not on offer: an unfiltered request always
    walks, and so does an exact-case (`merge_case=0`) one, whose match is
    not the index's leading `lemma_fold`.
    """

    page = _slice_works(works, offset, limit)
    if facet_range is not None and _prefer_facet(
        matches=sum(w.matches for w in works), walked=_walk_length(page), scanned=facet_range
    ):
        return _facet_rowids(conn, where, works, offset=offset, limit=limit)
    return _walk_rowids(conn, where, page)


def _walk_rowids(
    conn: sqlite3.Connection, where: _Where, page: list[tuple[_WorkCount, int, int]]
) -> list[int]:
    # `rowid` ends the order so it is total within a work, and it is the
    # index's own implicit last column, so the walk still needs no sort.
    sql = f"""
        SELECT cl.rowid FROM chunk_lemmas cl
        WHERE {_LANG_MATCH} AND {where.lemma_match_sql} AND cl.work_id = ?{where.extra_sql}
        ORDER BY cl.chunk_ord, cl.surface_start, cl.rowid
        LIMIT ? OFFSET ?
    """
    rowids: list[int] = []
    for w, off, take in page:
        params = [where.lang, where.lemma, w.work_id, *where.extra_params, take, off]
        rowids += [r[0] for r in conn.execute(sql, params)]
    return rowids


def _facet_rowids(
    conn: sqlite3.Connection, where: _Where, works: list[_WorkCount], *, offset: int, limit: int
) -> list[int]:
    # INDEXED BY because the planner, left alone, prefers the locator walk: it
    # avoids a sort, and the planner cannot see the filter is rare.
    sql = f"""
        SELECT cl.rowid, cl.work_id, cl.chunk_ord, cl.surface_start
        FROM chunk_lemmas cl INDEXED BY chunk_lemmas_by_facet
        WHERE {_LANG_MATCH} AND {where.lemma_match_sql}{where.scope_sql}{where.extra_sql}
    """
    params = [where.lang, where.lemma, *where.scope_params, *where.extra_params]
    rank = {w.work_id: w.rank for w in works}
    # A work missing from `rank` means lemmatize wrote between the two
    # statements; it sorts last rather than failing the request.
    last = (float("inf"),)
    rows = sorted(
        conn.execute(sql, params), key=lambda r: (rank.get(r[1], last), r[2], r[3], r[0])
    )
    return [r[0] for r in rows[offset : offset + limit]]


def _page_details(conn: sqlite3.Connection, rowids: list[int]) -> list[sqlite3.Row]:
    """The page's rows, joined to chunks_full, in `rowids` order."""

    if not rowids:
        return []
    placeholders = ",".join("?" * len(rowids))
    rows = conn.execute(
        f"""
        SELECT cl.rowid        AS rid,
               cl.chunk_id     AS chunk_id,
               cl.surface_form AS surface,
               cl.surface_start AS s_start,
               cl.surface_end   AS s_end,
               cl.pos          AS pos,
               cl.feats        AS feats,
               cf.section      AS section,
               cf.book         AS book,
               cf.work         AS work,
               cf.author       AS author,
               cf.ord          AS ord,
               cf.text         AS text
        FROM chunk_lemmas cl
        JOIN chunks_full cf ON cf.chunk_id = cl.chunk_id
        WHERE cl.rowid IN ({placeholders})
        """,
        rowids,
    ).fetchall()
    by_rid = {r["rid"]: r for r in rows}
    return [by_rid[rid] for rid in rowids if rid in by_rid]


# Order in which we report morphology in the compact ``morph_str``.
# Matches the German-philology convention (Case · Number · Gender for
# nouns; Person · Number · Tense · Mood for verbs).
_MORPH_ORDER = (
    "Case",
    "Number",
    "Gender",  # nouns/adj
    "Person",
    "Tense",
    "Mood",  # verbs
    "Degree",
    "VerbForm",  # adj / participle
)
_CASE_SHORT = {
    "Nom": "Nom",
    "Acc": "Akk",
    "Gen": "Gen",
    "Dat": "Dat",
    "Voc": "Vok",
}
_NUMBER_SHORT = {"Sing": "Sg", "Plur": "Pl"}
_GENDER_SHORT = {"Masc": "Mask", "Fem": "Fem", "Neut": "Neut"}


def _morph_short(morph: dict[str, str]) -> str:
    """Render the morph dict as a single compact display string,
    using German philology shorthands (``Nom · Sg · Mask``). Drops
    keys not in :data:`_MORPH_ORDER`."""

    bits: list[str] = []
    for key in _MORPH_ORDER:
        if key not in morph:
            continue
        val = morph[key]
        if key == "Case":
            val = _CASE_SHORT.get(val, val)
        elif key == "Number":
            val = _NUMBER_SHORT.get(val, val)
        elif key == "Gender":
            val = _GENDER_SHORT.get(val, val)
        bits.append(val)
    return " · ".join(bits)
