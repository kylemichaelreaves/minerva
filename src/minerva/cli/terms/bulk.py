"""`minerva terms import` — bulk-import a YAML glossary spec.

The spec format lives in :mod:`minerva.glossary_spec`; the engine is
:func:`minerva.glossary_import.apply_spec`. This handler is the thin
CLI wiring that resolves command-line flags, prints a report, and
sets the exit code on validation failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ...glossary_import import ImportReport, apply_spec
from ...glossary_spec import SpecError, load_spec, resolve_and_validate
from ._io import _open


def cmd_terms_import(args: argparse.Namespace) -> int:
    path: Path = args.path
    if not path.exists():
        print(f"import: {path} does not exist", file=sys.stderr)
        return 2
    try:
        spec = load_spec(path)
    except SpecError as exc:
        print(f"import: {exc}", file=sys.stderr)
        return 2

    conn = _open(args)
    try:
        # Resolution turns the spec's natural-key anchors (edition name,
        # translator name) into the surrogate ids the importer writes.
        # `apply_spec` must get the RESOLVED spec — the parsed one has
        # `edition_id = None` wherever the curator used a name (#193).
        spec, errors = resolve_and_validate(spec, conn)
        if errors:
            print("import: spec failed DB-level validation:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            return 2
        report = apply_spec(
            conn,
            spec,
            dry_run=args.dry_run,
            only_work=args.only_work,
        )
    finally:
        conn.close()

    if args.report == "json":
        print(json.dumps(_report_to_dict(report, dry_run=args.dry_run), indent=2))
    else:
        _print_text_report(report, dry_run=args.dry_run, spec_path=path)
    return 0


def _report_to_dict(r: ImportReport, *, dry_run: bool) -> dict[str, object]:
    return {
        "dry_run": dry_run,
        "terms_upserted": r.terms_upserted,
        "renderings_upserted": r.renderings_upserted,
        "relations_upserted": r.relations_upserted,
        "occurrences_inserted": r.occurrences_inserted,
        "occurrences_skipped_duplicate": r.occurrences_skipped_duplicate,
        "occurrences_unparseable_locator": r.occurrences_unparseable_locator,
        "per_work_counts": r.per_work_counts,
    }


def _print_text_report(r: ImportReport, *, dry_run: bool, spec_path: Path) -> None:
    prefix = "would " if dry_run else ""
    print(f"{spec_path}: {prefix}upsert {r.terms_upserted} terms, "
          f"{r.renderings_upserted} renderings, {r.relations_upserted} relations")
    for work, stats in sorted(r.per_work_counts.items()):
        print(f"  {work}: {prefix}insert {stats['ins']} occurrences "
              f"(skipped {stats['skip']} existing)")
    if r.occurrences_unparseable_locator:
        print(
            f"  {r.occurrences_unparseable_locator} chunks had unparseable section locators "
            f"(skipped)"
        )
    print(
        f"total: {prefix}insert {r.occurrences_inserted} occurrences "
        f"(skipped {r.occurrences_skipped_duplicate} existing)"
    )
