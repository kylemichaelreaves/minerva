"""Lemma detail / KWIC queries."""

from __future__ import annotations

import sqlite3
from typing import Any

from ..errors import BadRequestError
from ..query_params import escape_like_substring, parse_int_param
from ..reader.queries import _parse_morph_feats
from ..text import build_kwic
from ._scope import (
    _DEFAULT_KWIC_LIMIT,
    _KWIC_CONTEXT_RADIUS,
    _MAX_KWIC_LIMIT,
    _scope_clause,
    parse_authors,
    parse_works,
)
from .index_queries import _corpus_label

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
        "Number", "Gender", "Case", "VerbForm", "PronType", "Person",
        "Tense", "Mood", "Definite", "Voice", "Aspect", "Degree",
        "ConjType", "Poss", "Polarity", "Reflex", "NumType", "HebBinyan",
        "VerbType", "Foreign", "AdpType", "PunctType", "Abbr", "Hyph",
        "PunctSide", "ExtPos", "Prefix",
    }
)


def lemma_detail(
    conn: sqlite3.Connection, query: dict[str, str]
) -> dict[str, Any]:
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
        "0", "false", "no", "off",
    )

    limit = parse_int_param(
        query, "limit", _DEFAULT_KWIC_LIMIT, lo=1, hi=_MAX_KWIC_LIMIT, clamp=True,
    )
    offset = parse_int_param(query, "offset", 0, lo=0, clamp=True)
    radius = parse_int_param(
        query, "radius", _KWIC_CONTEXT_RADIUS, lo=20, hi=240, clamp=True,
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
    # case-folded path so the KWIC seek hits ``chunk_lemmas_by_fold``
    # instead of forcing a full chunks scan via
    # ``LOWER(cl.lemma) = LOWER(?)``. The exact-match path stays on
    # ``cl.lemma`` — the primary lemma index already covers it.
    lemma_match_sql = "cl.lemma_fold = LOWER(?)" if merge_case else "cl.lemma = ?"

    extra_sql = ""
    extra_params: list[Any] = []
    if pos:
        extra_sql += " AND cl.pos = ?"
        extra_params.append(pos)
    if surface:
        extra_sql += " AND cl.surface_form = ?"
        extra_params.append(surface)
    # spaCy feats stored as ``Key=Val|Key=Val``; a string-contains
    # match is faster than parsing every row in SQL. We require all
    # requested features to appear as substrings.
    # `morph` is free-form beyond its Key=Val shape check, so the key
    # and value are escaped — an unescaped `%` would widen the match
    # to "any row carrying this feature" instead of narrowing it (#120).
    for k, v in morph_filters.items():
        extra_sql += " AND cl.feats LIKE ? ESCAPE '\\'"
        extra_params.append(
            f"%{escape_like_substring(k)}={escape_like_substring(v)}%"
        )


    # Total + breakdowns. Two extra aggregate queries; both hit the
    # same index path so they're cheap.
    total_row = conn.execute(
        f"""
        SELECT COUNT(*) AS n
        FROM chunk_lemmas cl
        JOIN chunks_full cf ON cf.chunk_id = cl.chunk_id
        WHERE cf.lang = ? AND {lemma_match_sql}{scope_sql}{extra_sql}
        """,
        [lang, lemma, *scope_params, *extra_params],
    ).fetchone()
    total = int(total_row["n"]) if total_row else 0
    if total == 0:
        # Empty result — still return the breakdowns under the *un-
        # filtered* scope so the empty-state UI can suggest broadening
        # moves (the wireframe's F6 "Drop Number — 3 hits" affordance).
        breakdowns = _lemma_breakdowns(
            conn, lemma, lang, scope_sql, scope_params, lemma_match_sql,
        )
        return {
            "lemma": lemma,
            "lang": lang,
            "scope": scope,
            "scope_label": {"corpus": _corpus_label(lang),
                            "author": author_label,
                            "work": work_label}[scope],
            "filters": {
                "pos": pos, "morph": morph_filters, "surface": surface,
            },
            "total": 0,
            "limit": limit,
            "offset": offset,
            **breakdowns,
            "rows": [],
            "next_offset": None,
        }

    breakdowns = _lemma_breakdowns(
        conn, lemma, lang, scope_sql, scope_params, lemma_match_sql,
    )

    # Main page query — joins to chunks_full for section/work/author
    # + the chunk text so we can build KWIC snippets in Python.
    sql_rows = f"""
        SELECT cl.chunk_id    AS chunk_id,
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
        WHERE cf.lang = ? AND {lemma_match_sql}{scope_sql}{extra_sql}
        ORDER BY cf.ord ASC, cl.surface_start ASC
        LIMIT ? OFFSET ?
    """
    page = conn.execute(
        sql_rows,
        [lang, lemma, *scope_params, *extra_params, limit, offset],
    ).fetchall()

    out: list[dict[str, Any]] = []
    for r in page:
        morph = _parse_morph_feats(r["feats"])
        kwic = build_kwic(r["text"], r["s_start"], r["s_end"], radius)
        out.append({
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
        })

    next_offset = offset + limit if offset + limit < total else None

    return {
        "lemma": lemma,
        "lang": lang,
        "scope": scope,
        "scope_label": {"corpus": _corpus_label(lang),
                        "author": author_label,
                        "work": work_label}[scope],
        "filters": {
            "pos": pos, "morph": morph_filters, "surface": surface,
        },
        "total": total,
        "limit": limit,
        "offset": offset,
        **breakdowns,
        "rows": out,
        "next_offset": next_offset,
    }


def _lemma_breakdowns(
    conn: sqlite3.Connection,
    lemma: str,
    lang: str,
    scope_sql: str,
    scope_params: list[Any],
    lemma_match_sql: str = "cl.lemma = ?",
) -> dict[str, Any]:
    """Compute pos/case/number/gender/surface breakdowns under the
    unfiltered scope. Drives the filter rail's facet counts and the
    F6 empty-state's "drop filter X for N hits" suggestions.

    ``lemma_match_sql`` is the SQL fragment matching ``cl.lemma`` —
    pass ``LOWER(cl.lemma) = LOWER(?)`` for case-folded matching."""

    rows = conn.execute(
        f"""
        SELECT cl.pos AS pos, COUNT(*) AS n
        FROM chunk_lemmas cl
        JOIN chunks_full cf ON cf.chunk_id = cl.chunk_id
        WHERE cf.lang = ? AND {lemma_match_sql}{scope_sql}
          AND cl.pos IS NOT NULL AND cl.pos != ''
        GROUP BY cl.pos
        """,
        [lang, lemma, *scope_params],
    ).fetchall()
    pos_b = {r["pos"]: int(r["n"]) for r in rows}

    surface_rows = conn.execute(
        f"""
        SELECT cl.surface_form AS surface, COUNT(*) AS n
        FROM chunk_lemmas cl
        JOIN chunks_full cf ON cf.chunk_id = cl.chunk_id
        WHERE cf.lang = ? AND {lemma_match_sql}{scope_sql}
          AND cl.surface_form IS NOT NULL AND cl.surface_form != ''
        GROUP BY cl.surface_form
        """,
        [lang, lemma, *scope_params],
    ).fetchall()
    surface_b = {r["surface"]: int(r["n"]) for r in surface_rows}

    feat_rows = conn.execute(
        f"""
        SELECT cl.feats AS feats, COUNT(*) AS n
        FROM chunk_lemmas cl
        JOIN chunks_full cf ON cf.chunk_id = cl.chunk_id
        WHERE cf.lang = ? AND {lemma_match_sql}{scope_sql}
          AND cl.feats IS NOT NULL AND cl.feats != ''
        GROUP BY cl.feats
        """,
        [lang, lemma, *scope_params],
    ).fetchall()

    case_b: dict[str, int] = {}
    number_b: dict[str, int] = {}
    gender_b: dict[str, int] = {}
    for r in feat_rows:
        feats = _parse_morph_feats(r["feats"])
        count = int(r["n"])
        if "Case" in feats:
            case_b[feats["Case"]] = case_b.get(feats["Case"], 0) + count
        if "Number" in feats:
            number_b[feats["Number"]] = number_b.get(feats["Number"], 0) + count
        if "Gender" in feats:
            gender_b[feats["Gender"]] = gender_b.get(feats["Gender"], 0) + count

    work_rows = conn.execute(
        f"""
        SELECT cf.work AS work, COUNT(*) AS n
        FROM chunk_lemmas cl
        JOIN chunks_full cf ON cf.chunk_id = cl.chunk_id
        WHERE cf.lang = ? AND {lemma_match_sql}{scope_sql}
        GROUP BY cf.work
        ORDER BY n DESC
        """,
        [lang, lemma, *scope_params],
    ).fetchall()
    work_b = {wr["work"]: int(wr["n"]) for wr in work_rows}

    def _top(d: dict[str, int], n: int = 12) -> list[dict[str, Any]]:
        return [
            {"value": k, "count": v}
            for k, v in sorted(d.items(), key=lambda x: -x[1])[:n]
        ]

    return {
        "pos_breakdown": _top(pos_b),
        "case_breakdown": _top(case_b),
        "number_breakdown": _top(number_b),
        "gender_breakdown": _top(gender_b),
        "surface_breakdown": _top(surface_b),
        "work_breakdown": _top(work_b, n=20),
    }


# Order in which we report morphology in the compact ``morph_str``.
# Matches the German-philology convention (Case · Number · Gender for
# nouns; Person · Number · Tense · Mood for verbs).
_MORPH_ORDER = (
    "Case", "Number", "Gender",      # nouns/adj
    "Person", "Tense", "Mood",       # verbs
    "Degree", "VerbForm",            # adj / participle
)
_CASE_SHORT = {
    "Nom": "Nom", "Acc": "Akk", "Gen": "Gen", "Dat": "Dat", "Voc": "Vok",
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
