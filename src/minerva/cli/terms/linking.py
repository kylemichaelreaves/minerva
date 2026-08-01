"""Schema-level browse / cross-link commands: `works`, `editions`,
`translations`, `render`, `relate`. These don't anchor anything to a
specific chunk — they wire entities together at the schema level."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from typing import Any

from ...query_params import escape_like_substring
from ._io import _emit, _open, _read_text_input


def cmd_terms_works(args: argparse.Namespace) -> int:
    conn = _open(args)
    sql = "SELECT id, author, title, original_language, citation_system FROM works "
    params: list[Any] = []
    if args.like:
        sql += "WHERE title LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\' "
        pattern = f"%{escape_like_substring(args.like)}%"
        params.extend([pattern, pattern])
    sql += "ORDER BY author, title"
    rows = [tuple(r) for r in conn.execute(sql, params).fetchall()]
    _emit(rows, ("id", "author", "title", "orig_lang", "citation"), args.json)
    return 0


def cmd_terms_editions(args: argparse.Namespace) -> int:
    conn = _open(args)
    sql = (
        "SELECT e.id, w.title AS work, e.name, e.language, e.year, e.is_canonical "
        "FROM editions e JOIN works w ON w.id = e.work_id "
    )
    params: list[Any] = []
    if args.work_id is not None:
        sql += "WHERE e.work_id = ? "
        params.append(args.work_id)
    sql += "ORDER BY w.title, e.year"
    rows = [tuple(r) for r in conn.execute(sql, params).fetchall()]
    _emit(rows, ("id", "work", "name", "lang", "year", "canonical"), args.json)
    return 0


def cmd_terms_translations(args: argparse.Namespace) -> int:
    conn = _open(args)
    sql = (
        "SELECT t.id, w.title AS work, t.translator_name, t.year, t.language "
        "FROM translations t JOIN works w ON w.id = t.work_id "
    )
    params: list[Any] = []
    if args.work_id is not None:
        sql += "WHERE t.work_id = ? "
        params.append(args.work_id)
    sql += "ORDER BY w.title, t.year"
    rows = [tuple(r) for r in conn.execute(sql, params).fetchall()]
    _emit(rows, ("id", "work", "translator", "year", "lang"), args.json)
    return 0


def cmd_terms_render(args: argparse.Namespace) -> int:
    note = _read_text_input(args.note, args.note_file)
    conn = _open(args)
    existing = conn.execute(
        "SELECT id FROM term_renderings WHERE term_id = ? AND translation_id = ?",
        (args.term_id, args.translation_id),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE term_renderings "
            "SET default_rendering = ?, translator_note = COALESCE(?, translator_note) "
            "WHERE id = ?",
            (args.rendering, note, existing["id"]),
        )
        conn.commit()
        print(f"updated rendering id={existing['id']}")
    else:
        cur = conn.execute(
            "INSERT INTO term_renderings "
            "  (term_id, translation_id, default_rendering, translator_note) "
            "VALUES (?, ?, ?, ?)",
            (args.term_id, args.translation_id, args.rendering, note),
        )
        conn.commit()
        print(f"created rendering id={cur.lastrowid}")
    return 0


def cmd_terms_relate(args: argparse.Namespace) -> int:
    if args.a == args.b:
        print("cannot relate a term to itself", file=sys.stderr)
        return 1
    note = _read_text_input(args.note, args.note_file)
    conn = _open(args)
    try:
        conn.execute(
            "INSERT INTO term_relations (term_id, related_term_id, relation_kind, notes) "
            "VALUES (?, ?, ?, ?)",
            (args.a, args.b, args.kind, note),
        )
        if args.symmetric:
            conn.execute(
                "INSERT OR IGNORE INTO term_relations "
                "  (term_id, related_term_id, relation_kind, notes) "
                "VALUES (?, ?, ?, ?)",
                (args.b, args.a, args.kind, note),
            )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        print(f"relation already exists or violates FK: {exc}", file=sys.stderr)
        return 1
    print(f"related term {args.a} → {args.b}" + (" (symmetric)" if args.symmetric else ""))
    return 0
