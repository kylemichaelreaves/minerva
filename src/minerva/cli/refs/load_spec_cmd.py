"""`minerva refs load-spec` — load YAML curator specs into cross_references.

Walks one or more paths (file or directory). For each YAML file it
parses via :func:`minerva.refs.spec.load_spec`, then for each
``ReferenceSpec``:

1. Resolves the source chunk_id (either provided directly or looked up
   via (work, lang, section) in the ``chunks_full`` view).
2. Resolves the target via :func:`refs.schema.ensure_target` (creates
   the ``reference_targets`` row if needed).
3. Inserts the row via :func:`refs.schema.insert_cross_reference`.

Module name is ``load_spec_cmd`` (not ``load_spec``) to avoid clashing
with the sibling ``refs.spec.load_spec`` function — same defensive
naming as ``list_cmd.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ...refs import schema as refs_schema
from ...refs import spec as refs_spec
from ..terms._io import _open


def cmd_refs_load_spec(args: argparse.Namespace) -> int:
    conn = _open(args)
    conn.execute("PRAGMA foreign_keys = ON")

    # Expand each input path: a directory becomes its *.yaml children.
    spec_files: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        if not p.exists():
            print(f"error: path does not exist: {p}", file=sys.stderr)
            return 2
        if p.is_dir():
            spec_files.extend(sorted(p.glob("*.yaml")))
            spec_files.extend(sorted(p.glob("*.yml")))
        else:
            spec_files.append(p)

    if not spec_files:
        print("error: no YAML files found in the given paths", file=sys.stderr)
        return 2

    total_parsed = 0
    total_inserted = 0
    total_skipped = 0
    total_errors = 0

    for path in spec_files:
        try:
            spec = refs_spec.load_spec(path)
        except refs_spec.SpecError as exc:
            print(f"parse error in {path}: {exc}", file=sys.stderr)
            total_errors += 1
            continue

        print(f"\n{path} — {len(spec.references)} references")
        for ref_idx, ref in enumerate(spec.references):
            total_parsed += 1
            try:
                inserted = _insert_one_reference(conn, ref, dry_run=args.dry_run)
            except _LoadError as exc:
                print(f"  references[{ref_idx}] error: {exc}", file=sys.stderr)
                total_errors += 1
                continue

            if inserted is None:
                total_skipped += 1
                continue
            total_inserted += 1
            print(
                f"  references[{ref_idx}] → id={inserted} "
                f"({ref.target.author} / {ref.target.work}, type={ref.type})"
            )

    if not args.dry_run and total_inserted > 0:
        conn.commit()

    mode = "dry-run" if args.dry_run else "committed"
    print(
        f"\n{mode}: parsed={total_parsed}, inserted={total_inserted}, "
        f"skipped={total_skipped}, errors={total_errors}",
        file=sys.stderr,
    )
    return 0 if total_errors == 0 else 1


class _LoadError(Exception):
    """One-reference-level error during a load-spec run."""


def _insert_one_reference(
    conn,
    ref: refs_spec.ReferenceSpec,
    *,
    dry_run: bool,
) -> int | None:
    """Resolve + insert one ReferenceSpec. Returns the new row id, or
    None when dry-run or when an equivalent row already exists.

    Idempotency: a content match on
    ``(source_chunk_id, target_id, reference_type, source_form_snapshot,
    quoted_phrase)`` causes the load to skip rather than create a duplicate.
    The shadow-address UNIQUE constraint on
    ``cross_references`` would otherwise let the same logical
    reference accrete multiple rows (with incrementing
    ``source_instance_index``) on every re-run, which is the wrong
    behaviour for canonical curator specs that are expected to be
    loaded idempotently."""

    # Source resolution.
    source_chunk_id = _resolve_source_chunk_id(conn, ref.source)
    if source_chunk_id is None:
        raise _LoadError(
            f"could not resolve source: {ref.source!r}"
        )

    # Target resolution. ``ensure_target`` is a no-op (returns the
    # existing row) when the (author, work) pair is already present.
    target = refs_schema.ensure_target(
        conn,
        canonical_author=ref.target.author,
        canonical_work=ref.target.work,
    )

    # Content-based dedup. Use `IS` for NULL-safe equality.
    existing = conn.execute(
        "SELECT id FROM cross_references "
        "WHERE source_chunk_id = ? "
        "  AND target_id = ? "
        "  AND reference_type = ? "
        "  AND source_form_snapshot IS ? "
        "  AND quoted_phrase IS ?",
        (
            source_chunk_id,
            target.id,
            ref.type,
            ref.source_form,
            ref.quoted_phrase,
        ),
    ).fetchone()
    if existing is not None:
        return None

    if dry_run:
        return None

    return refs_schema.insert_cross_reference(
        conn,
        source_chunk_id=source_chunk_id,
        target_id=target.id,
        reference_type=ref.type,
        source_form_snapshot=ref.source_form,
        quoted_phrase=ref.quoted_phrase,
        target_chunk_id=ref.target.chunk_id,
        target_locator=ref.target.locator,
        target_locator_payload=ref.target.locator_payload,
        target_sort_key=ref.target.sort_key,
        source_method="manual",
        curator_status="manual",
        confidence=1.0,
        curator_note=ref.note,
    )


def _resolve_source_chunk_id(conn, source: refs_spec.SourceRef) -> str | None:
    """Return the source_chunk_id named by a ``SourceRef``. Prefers the
    explicit ``chunk_id``; falls back to a (work, lang, section)
    lookup through the ``chunks_full`` view."""

    if source.chunk_id is not None:
        # Sanity-check it exists; raise LoadError if not so the
        # caller can report the offending reference.
        row = conn.execute(
            "SELECT 1 FROM chunks WHERE chunk_id = ?",
            (source.chunk_id,),
        ).fetchone()
        if row is None:
            raise _LoadError(f"chunk_id {source.chunk_id!r} not found")
        return source.chunk_id

    if not (source.work and source.lang and source.section):
        return None

    # Use the chunks_full view which joins through works + editions +
    # translations and exposes the (work, lang, section) triple.
    row = conn.execute(
        "SELECT chunk_id FROM chunks_full "
        "WHERE work = ? AND lang = ? AND section = ? "
        "LIMIT 1",
        (source.work, source.lang, source.section),
    ).fetchone()
    if row is None:
        raise _LoadError(
            f"no chunk found for (work={source.work!r}, "
            f"lang={source.lang!r}, section={source.section!r})"
        )
    return str(row[0])
