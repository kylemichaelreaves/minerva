"""`minerva refs review` — terminal curator walker for `auto` rows.

Walks every ``curator_status='auto'`` row in the cross-references
table, showing source context (with the matched span highlighted) +
target metadata + rule provenance. Keys:

  [a]pprove — promote curator_status to 'approved'. Row stays in
              the index forever (until a future build pass or
              embed-verify might bump confidence; status is what the
              UI filters on).
  [r]eject  — set curator_status to 'rejected'. Row stays on disk
              but is hidden from the reader's default filter.
  [s]kip    — leave the row unchanged (`auto`) and move on.
  [q]uit    — exit the walker.

Filters: ``--source-author`` and ``--target-author`` for focused
review of one channel (e.g. just Aquinas → Aristotle). ``--limit``
caps the number of rows shown per session (defaults to 50).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from typing import Any

from ...refs.constants import SOURCE_AUTHOR
from ..terms._io import _open


# ANSI color codes — used only when stdout is a tty. Detection is a
# one-liner so we don't pull in a colour-management dep.
def _tty() -> bool:
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _accent(s: str) -> str:
    return f"\033[33m{s}\033[0m" if _tty() else s


def _dim(s: str) -> str:
    return f"\033[2m{s}\033[0m" if _tty() else s


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if _tty() else s


def _highlight_span(text: str, start: int | None, end: int | None) -> str:
    """Return ``text`` with the [start, end) span bracketed (and
    color-bolded on a tty). Falls back to the raw text when the spans
    aren't provided — rule_strong rows always have spans, but a
    rule_weak that fired on a whole-chunk content match might not."""

    if start is None or end is None or start >= end or end > len(text):
        return text
    return text[:start] + _bold(_accent(text[start:end])) + text[end:]


def _fetch_one_row(
    conn: sqlite3.Connection,
    *,
    source_author: str | None,
    target_author: str | None,
    after_id: int,
) -> sqlite3.Row | None:
    """Fetch the next reviewable row past ``after_id``. Joins through
    chunks → editions/translations → works so the display has the
    source-side citation context without extra round trips.

    Rows are returned in ``cross_references.id`` order — stable across
    re-runs, so a curator can leave the walker and pick up where they
    left off."""

    clauses = [
        "xr.id > ?",
        "xr.curator_status = 'auto'",
    ]
    params: list[Any] = [after_id]
    if source_author is not None:
        clauses.append(f"{SOURCE_AUTHOR} = ?")
        params.append(source_author)
    if target_author is not None:
        clauses.append("rt.canonical_author = ?")
        params.append(target_author)

    where = " AND ".join(clauses)

    sql = (
        "SELECT xr.id, xr.source_chunk_id, xr.source_span_start, "
        "       xr.source_span_end, xr.source_form_snapshot, xr.quoted_phrase, "
        "       xr.target_id, xr.reference_type, xr.confidence, "
        "       xr.source_method, xr.curator_note, "
        "       xr.curated_by, xr.curated_at, "
        "       rt.canonical_author AS target_author, "
        "       rt.canonical_work AS target_work, "
        "       rt.in_corpus_work_id, "
        f"       {SOURCE_AUTHOR} AS source_author, "
        "       src_work.title AS source_work, "
        "       c.section AS source_section, "
        "       c.text AS source_text "
        "FROM cross_references xr "
        "JOIN reference_targets rt ON rt.id = xr.target_id "
        "JOIN chunks c ON c.chunk_id = xr.source_chunk_id "
        "LEFT JOIN editions e ON e.id = c.edition_id "
        "LEFT JOIN translations t ON t.id = c.translation_id "
        "LEFT JOIN works src_work "
        "       ON src_work.id = COALESCE(e.work_id, t.work_id) "
        f"WHERE {where} "
        "ORDER BY xr.id "
        "LIMIT 1"
    )
    return conn.execute(sql, params).fetchone()


def _print_row(row: sqlite3.Row, ordinal: int) -> None:
    """Render one row for curator review. Highlights the matched span
    in source text, shows target + provenance + rule confidence."""

    sep = "─" * 72
    print(f"\n{sep}")
    print(
        f"#{ordinal}  "
        f"{_bold(row['source_author'] or '?')} → "
        f"{_bold(row['target_author'])}"
        f"  {_dim('(refs.id=' + str(row['id']) + ')')}"
    )
    print(sep)
    src_loc = (
        f"{row['source_work']}  {_dim(row['source_section'] or '')}" if row["source_work"] else "?"
    )
    print(f"source : {src_loc}")
    print(
        f"target : {row['target_author']}, {row['target_work']}  "
        f"{_dim('(in_corpus_work_id=' + str(row['in_corpus_work_id'] or '–') + ')')}"
    )
    print(
        f"type   : {row['reference_type']}  "
        f"confidence={row['confidence']:.2f}  "
        f"method={row['source_method']}"
    )
    # NULL is "unrecorded", never "machine": most rejections predate the
    # column (#720).
    if row["curated_by"]:
        print(f"curated: {row['curated_by']}  {_dim('(at ' + str(row['curated_at']) + ')')}")
    else:
        print(f"curated: {_dim('unrecorded')}")
    if row["source_form_snapshot"]:
        # Labelled "matched", not "form", because it is deliberately a
        # WIDER extent than the highlight below: the rule matches the
        # whole construction (`in Psalmo: <quote>.`) and spans only the
        # quotation. 212 scripture references in Aquinas and Augustine
        # differ this way and none of them is misanchored (#414). The
        # snapshot cannot simply be narrowed to agree — it is a column of
        # the shadow address that makes references recoverable across a
        # re-ingest (`refs/schema.py:165-181`).
        print(f"matched: {row['source_form_snapshot']!r}  {_dim('(may exceed the highlight)')}")
    if row["quoted_phrase"]:
        print(f"quoted : {row['quoted_phrase']!r}")
    if row["curator_note"]:
        print(f"note   : {row['curator_note']}")
    print(sep)
    print(
        _highlight_span(
            row["source_text"],
            row["source_span_start"],
            row["source_span_end"],
        )
    )
    print(sep)


def _prompt() -> str:
    """Read one keystroke + return its lowercased letter. Empty input
    (the user hit Enter alone) is treated as 'skip' — the most
    conservative default. Ctrl-D / EOF returns 'q' so the walker
    exits cleanly without leaving an uncommitted transaction."""

    try:
        raw = (
            input(
                f"\n{_accent('[a]')}pprove  "
                f"{_accent('[r]')}eject  "
                f"{_accent('[s]')}kip  "
                f"{_accent('[q]')}uit  "
                f"› "
            )
            .strip()
            .lower()
        )
    except EOFError:
        return "q"
    if not raw:
        return "s"
    return raw[0]


def cmd_refs_review(args: argparse.Namespace) -> int:
    # `closing` so an interactive session left via `q` — or an EOF out
    # of `_prompt` — still releases the handle (#246).
    with closing(_open(args)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        n_approved = 0
        n_rejected = 0
        n_skipped = 0
        n_seen = 0
        after_id = 0
        limit = args.limit

        while n_seen < limit:
            row = _fetch_one_row(
                conn,
                source_author=args.source_author,
                target_author=args.target_author,
                after_id=after_id,
            )
            if row is None:
                print(_dim("\n(no more auto rows match the current filter)"))
                break
            n_seen += 1
            _print_row(row, ordinal=n_seen)
            key = _prompt()

            if key == "q":
                break
            if key == "a":
                conn.execute(
                    "UPDATE cross_references SET curator_status='approved', "
                    "  curated_by = 'human', curated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                    "WHERE id = ?",
                    (row["id"],),
                )
                conn.commit()
                n_approved += 1
                print(_accent("→ approved."))
            elif key == "r":
                conn.execute(
                    "UPDATE cross_references SET curator_status='rejected', "
                    "  curated_by = 'human', curated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                    "WHERE id = ?",
                    (row["id"],),
                )
                conn.commit()
                n_rejected += 1
                print(_dim("→ rejected."))
            else:
                n_skipped += 1
                print(_dim("→ skipped."))

            # Advance past this row so the next iteration of the loop
            # fetches the next-higher id rather than re-fetching the same
            # row we just decided on.
            after_id = int(row["id"])

        print(
            f"\nreview session: seen={n_seen}, approved={n_approved}, "
            f"rejected={n_rejected}, skipped={n_skipped}"
        )
        return 0
