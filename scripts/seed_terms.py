"""Thin wrapper around `minerva terms import` for the original
hand-curated Aristotle seed set.

History: this script used to carry the full TERMS / WORK_TARGETS data
inline. That data has been ported to ``data/glossary/aristotle.grc.yaml``
and the script is kept as an entry point for muscle memory —
re-running it against an already-seeded DB should be a no-op. (This
docstring used to add "CI regression coverage" to that list; no test,
workflow or Makefile target runs the script, #505.)

For new term work, write a YAML spec under ``data/glossary/`` and
invoke ``uv run minerva terms import path/to/spec.yaml`` directly.
This script will also seed any additional ``data/glossary/*.yaml``
files automatically, so a curator who drops a new spec into the
directory doesn't have to remember a flag.

Role: workflow
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `import minerva.*` when running this script directly from the
# repo root (`uv run python scripts/seed_terms.py`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from minerva.cli.terms.bulk import cmd_terms_import


def _yaml_specs(root: Path) -> list[Path]:
    """Every `*.yaml` directly under `data/glossary/`. Subdirectories
    are skipped so the curator can stash experimental drafts in
    `data/glossary/_drafts/` etc. without them getting auto-loaded."""

    if not root.exists():
        return []
    return sorted(p for p in root.glob("*.yaml") if p.is_file())


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--db",
        type=Path,
        default=Path("data/index.sqlite"),
        help="path to the index sqlite (default: data/index.sqlite)",
    )
    p.add_argument(
        "--glossary-dir",
        type=Path,
        default=Path("data/glossary"),
        help="directory of YAML spec files to import (default: data/glossary)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate + count what would happen; no writes.",
    )
    args = p.parse_args()

    specs = _yaml_specs(args.glossary_dir)
    if not specs:
        print(f"seed_terms: no specs found under {args.glossary_dir}")
        return 0

    rc = 0
    for spec_path in specs:
        # Pass through `minerva terms import`'s handler — it owns
        # the validation + report layout. We build an argparse-shaped
        # namespace so we don't have to fork the CLI plumbing.
        import_args = argparse.Namespace(
            db=args.db,
            path=spec_path,
            dry_run=args.dry_run,
            only_work=None,
            report="text",
        )
        rc |= cmd_terms_import(import_args)
    return rc


if __name__ == "__main__":
    sys.exit(main())
