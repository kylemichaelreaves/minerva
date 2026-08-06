"""`minerva refs add` — record one manual cross-reference."""

from __future__ import annotations

import argparse
import sys

from ...refs import schema as refs_schema
from ..terms._io import _open


def cmd_refs_add(args: argparse.Namespace) -> int:
    conn = _open(args)
    conn.execute("PRAGMA foreign_keys = ON")

    # Resolve target — either by id or by "Author / Work" string.
    target_id: int
    if args.target_id is not None:
        target = refs_schema.find_target_by_id(conn, args.target_id)
        if target is None:
            print(
                f"error: no reference_targets row with id={args.target_id}; "
                f"try `minerva refs targets` to find one",
                file=sys.stderr,
            )
            return 2
        target_id = target.id
    else:
        # Parse "Author / Work".
        raw = args.target
        if "/" not in raw:
            print(
                f"error: --target {raw!r} must be 'Author / Work'",
                file=sys.stderr,
            )
            return 2
        author_part, _, work_part = raw.partition("/")
        author = author_part.strip()
        work = work_part.strip()
        if not author or not work:
            print(
                f"error: --target {raw!r} must have non-empty author + work",
                file=sys.stderr,
            )
            return 2
        target = refs_schema.ensure_target(
            conn,
            canonical_author=author,
            canonical_work=work,
        )
        target_id = target.id
        if target.in_corpus_work_id is not None:
            print(
                f"target: {target.canonical_author} / {target.canonical_work} "
                f"(in-corpus, work_id={target.in_corpus_work_id})",
                file=sys.stderr,
            )
        else:
            print(
                f"target: {target.canonical_author} / {target.canonical_work} (out-of-corpus)",
                file=sys.stderr,
            )

    # Parse the optional --source-span.
    span_start: int | None = None
    span_end: int | None = None
    if args.source_span is not None:
        try:
            s, _, e = args.source_span.partition(":")
            span_start = int(s)
            span_end = int(e) if e else None
            if span_end is None or span_end <= span_start:
                raise ValueError("end must be > start")
        except ValueError as exc:
            print(
                f"error: --source-span {args.source_span!r} must be 'start:end' "
                f"with end > start ({exc})",
                file=sys.stderr,
            )
            return 2

    try:
        ref_id = refs_schema.insert_cross_reference(
            conn,
            source_chunk_id=args.source_chunk,
            target_id=target_id,
            reference_type=args.ref_type,
            source_span_start=span_start,
            source_span_end=span_end,
            source_form_snapshot=args.source_form,
            quoted_phrase=args.quoted_phrase,
            target_chunk_id=args.target_chunk,
            target_locator=args.target_locator,
            confidence=args.confidence,
            source_method="manual",
            curator_status="manual",
            curator_note=args.note,
        )
    except refs_schema.RefsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    conn.commit()
    print(f"cross_references id={ref_id} created")
    return 0
