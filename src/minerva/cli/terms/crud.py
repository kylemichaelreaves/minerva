"""Single-entity CRUD: `list`, `show`, `add`, `canonical`."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from typing import Any

from ...query_params import escape_like_substring
from ._io import _emit, _read_text_input, _with_db


@_with_db
def cmd_terms_list(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    sql = (
        "SELECT t.id, t.source_form, t.source_language, t.short_gloss, "
        "       COUNT(o.id) AS occurrences "
        "FROM terms t "
        "LEFT JOIN term_occurrences o ON o.term_id = t.id "
    )
    where: list[str] = []
    params: list[Any] = []
    if args.lang:
        where.append("t.source_language = ?")
        params.append(args.lang)
    if args.like:
        # Without ESCAPE a `%` in --like matches every term instead of
        # none (#120).
        where.append("t.source_form LIKE ? ESCAPE '\\'")
        params.append(f"%{escape_like_substring(args.like)}%")
    if where:
        sql += "WHERE " + " AND ".join(where) + " "
    sql += "GROUP BY t.id ORDER BY t.source_language, t.source_form"
    rows = [tuple(r) for r in conn.execute(sql, params).fetchall()]
    _emit(rows, ("id", "source_form", "lang", "gloss", "n_occ"), args.json)
    return 0


@_with_db
def cmd_terms_show(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    if args.term_id_or_form.isdigit():
        term = conn.execute(
            "SELECT * FROM terms WHERE id = ?", (int(args.term_id_or_form),)
        ).fetchone()
    else:
        sql = "SELECT * FROM terms WHERE source_form = ?"
        params: list[Any] = [args.term_id_or_form]
        if args.lang:
            sql += " AND source_language = ?"
            params.append(args.lang)
        term = conn.execute(sql, params).fetchone()
    if term is None:
        print(f"no term matches {args.term_id_or_form!r}", file=sys.stderr)
        return 1
    print(f"id:               {term['id']}")
    print(f"source_form:      {term['source_form']}")
    print(f"source_language:  {term['source_language']}")
    if term["transliteration"]:
        print(f"transliteration:  {term['transliteration']}")
    if term["lemma"]:
        print(f"lemma:            {term['lemma']}")
    print(f"short_gloss:      {term['short_gloss']}")
    print()
    print("description:")
    for line in (term["long_description"] or "").splitlines():
        print(f"  {line}")
    # Renderings
    print()
    print("renderings:")
    rends = conn.execute(
        "SELECT r.default_rendering, r.translator_note, "
        "       tr.translator_name, tr.year, tr.language "
        "FROM term_renderings r "
        "JOIN translations tr ON tr.id = r.translation_id "
        "WHERE r.term_id = ? "
        "ORDER BY tr.translator_name, tr.year",
        (term["id"],),
    ).fetchall()
    if not rends:
        print("  (none)")
    else:
        for r in rends:
            label = f"{r['translator_name']} ({r['year']}) → {r['language']}"
            print(f"  {label}: {r['default_rendering']}")
    # Occurrence count by edition.
    print()
    print("occurrences by edition:")
    occ = conn.execute(
        "SELECT e.name, e.language, COUNT(o.id) AS n "
        "FROM term_occurrences o "
        "JOIN editions e ON e.id = o.edition_id "
        "WHERE o.term_id = ? "
        "GROUP BY e.id "
        "ORDER BY n DESC",
        (term["id"],),
    ).fetchall()
    if not occ:
        print("  (none)")
    else:
        for r in occ:
            print(f"  {r['name']} ({r['language']}): {r['n']}")
    return 0


@_with_db
def cmd_terms_add(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    description = _read_text_input(args.description, args.description_file)
    if description is None:
        description = ""
    try:
        cur = conn.execute(
            "INSERT INTO terms (source_form, source_language, transliteration, "
            "                   lemma, short_gloss, long_description) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                args.form,
                args.lang,
                args.transliteration,
                args.lemma,
                args.gloss,
                description,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        # The (source_form, source_language) UNIQUE constraint is the
        # natural collision. Surface the existing id so a curator can
        # decide whether to `terms show` it or supply a different form.
        existing = conn.execute(
            "SELECT id FROM terms WHERE source_form = ? AND source_language = ?",
            (args.form, args.lang),
        ).fetchone()
        if existing:
            print(
                f"term already exists: id={existing[0]} "
                f"source_form={args.form!r} source_language={args.lang!r}",
                file=sys.stderr,
            )
            return 1
        raise exc
    print(f"created term id={cur.lastrowid}")
    return 0


@_with_db
def cmd_terms_canonical(args: argparse.Namespace, conn: sqlite3.Connection) -> int:
    """Mark / unmark an edition as the canonical one for its
    (work_id, language) pair. The UNIQUE index from migration 0004
    enforces at most one canonical edition per pair, so setting a new
    one is a two-step: clear the old, set the new."""

    ed = conn.execute(
        "SELECT id, work_id, language FROM editions WHERE id = ?",
        (args.edition,),
    ).fetchone()
    if ed is None:
        print(f"no edition with id={args.edition}", file=sys.stderr)
        return 1
    if args.unset:
        conn.execute(
            "UPDATE editions SET is_canonical = 0 WHERE id = ?",
            (args.edition,),
        )
        conn.commit()
        print(f"edition {args.edition} marked non-canonical")
        return 0
    # Setting canonical: clear any existing canonical for the pair,
    # then mark this one.
    conn.execute(
        "UPDATE editions SET is_canonical = 0 WHERE work_id = ? AND language = ? AND id != ?",
        (ed["work_id"], ed["language"], ed["id"]),
    )
    conn.execute(
        "UPDATE editions SET is_canonical = 1 WHERE id = ?",
        (ed["id"],),
    )
    conn.commit()
    print(
        f"edition {args.edition} marked canonical for "
        f"(work_id={ed['work_id']}, language={ed['language']})"
    )
    return 0
