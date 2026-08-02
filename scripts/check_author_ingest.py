#!/usr/bin/env python3
"""Verify a corpus author is fully wired for ingest (registry, manifest, rules)."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from chunk_count_validation import (
    DEFAULT_DB,
    SNAPSHOT_PATH,
    build_snapshot,
    load_snapshot,
    snapshot_drift,
    validate_chunk_counts,
    validate_snapshot,
    write_snapshot,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = REPO_ROOT / "src" / "minerva" / "refs" / "rules"
SPECS_DIR = RULES_DIR / "specs"
MANIFEST_PATH = REPO_ROOT / "data" / "authors" / "manifest.yaml"


def _load_manifest() -> dict:
    import yaml

    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def _rules_module_for_corpus(corpus_id: str, manifest: dict) -> str:
    for author in manifest.get("authors") or []:
        if author.get("corpus_id") == corpus_id:
            return author.get("rules_module") or corpus_id.replace("-", "_")
    return corpus_id


def _has_rules(corpus_id: str, manifest: dict) -> bool:
    mod = _rules_module_for_corpus(corpus_id, manifest)
    py_path = RULES_DIR / f"{mod}.py"
    yaml_path = SPECS_DIR / f"{mod}.yaml"
    if yaml_path.is_file():
        return True
    if not py_path.is_file():
        return False
    text = py_path.read_text(encoding="utf-8")
    return "RULES" in text or "rules" in text.lower()


def check_corpus(corpus_id: str, manifest: dict, ingest_ids: set[str]) -> list[str]:
    errors: list[str] = []
    corpus_ids = {c["id"] for c in manifest.get("corpora") or []}
    if corpus_id not in corpus_ids:
        errors.append(f"corpus {corpus_id!r} missing from manifest corpora")
    # Registry is the single source of truth for which IngestSources feed
    # a corpus — no hand-maintained corpus→ingest map to drift (issue #70).
    from minerva.ingest.registry import corpus_slugs_for_ingest_ids

    if corpus_id not in corpus_slugs_for_ingest_ids(ingest_ids):
        errors.append(f"corpus {corpus_id!r} has no IngestSource in ingest/registry")
    from minerva import author_ordering, corpus_registry

    if corpus_id not in {e.id for e in corpus_registry.CORPORA}:
        errors.append(f"corpus {corpus_id!r} missing from corpus_registry.CORPORA")
    author_names = [
        a["display_name"]
        for a in manifest.get("authors") or []
        if a.get("corpus_id") == corpus_id
    ]
    if not author_names:
        errors.append(f"no manifest author row with corpus_id={corpus_id!r}")
    for name in author_names:
        if name not in author_ordering.AUTHOR_ORDINAL:
            errors.append(f"author {name!r} missing from AUTHOR_ORDINAL")
    if not _has_rules(corpus_id, manifest):
        mod = _rules_module_for_corpus(corpus_id, manifest)
        errors.append(
            f"no refs rules at rules/{mod}.py or rules/specs/{mod}.yaml "
            f"(scripture_cite may cover biblical corpora — add to SKIP_RULES if intentional)"
        )
    return errors


# Curated allowlist of corpora that intentionally ship NO per-corpus refs
# rules module: biblical hosts covered by scripture_cite, plus text-only
# reference targets (Homer, the Presocratics) that other authors cite but
# which have no outgoing rules of their own. A corpus that later grows a
# rules module must be REMOVED from here — the meta-check in main() flags
# a stale entry so this list can't silently rot (issue #70). It used to
# also list plato/aristotle/descartes/the tragedians, which have since
# grown real rules modules.
SKIP_RULES: frozenset[str] = frozenset(
    {
        "homer",
        "hebrew_mt",
        "septuagint",
        "new_testament",
        "vulgate",
        "luther_1912",
        "luther_1545",
        "kjv",
        "sacy",
        "quran",
        "presocratic",
    }
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", help="Check one corpus id")
    parser.add_argument("--all", action="store_true", help="Check every manifest corpus")
    parser.add_argument(
        "--db",
        default=None,
        help=(
            "Optional index.sqlite path for chunk-count range validation "
            f"(default when present: {DEFAULT_DB.relative_to(REPO_ROOT)})"
        ),
    )
    parser.add_argument(
        "--skip-chunk-counts",
        action="store_true",
        help="Waive chunk-count validation entirely (prints that it did)",
    )
    parser.add_argument(
        "--write-chunk-counts",
        action="store_true",
        help=(
            "Regenerate the committed counts snapshot from the DB "
            f"({SNAPSHOT_PATH.name}); requires the index to exist"
        ),
    )
    args = parser.parse_args()
    if not MANIFEST_PATH.is_file():
        print(f"Missing {MANIFEST_PATH}", file=sys.stderr)
        return 1
    manifest = _load_manifest()
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from minerva.ingest.registry import INGEST_SOURCES

    ingest_ids = {s.id for s in INGEST_SOURCES}
    if args.all:
        corpus_ids = [c["id"] for c in manifest["corpora"]]
    elif args.corpus:
        corpus_ids = [args.corpus]
    else:
        parser.print_help()
        return 1

    failed = False
    for cid in corpus_ids:
        errs = check_corpus(cid, manifest, ingest_ids)
        if cid in SKIP_RULES:
            # Suppress the "no refs rules" error for intentionally
            # rule-less corpora — but flag the skip entry itself as
            # stale if the corpus has since grown a rules module, so
            # SKIP_RULES stays honest (issue #70).
            if _has_rules(cid, manifest):
                errs.append(
                    f"corpus {cid!r} is in SKIP_RULES but now has a rules "
                    f"module — remove it from SKIP_RULES"
                )
            else:
                errs = [e for e in errs if "refs rules" not in e]
        if errs:
            failed = True
            print(f"{cid}:")
            for e in errs:
                print(f"  - {e}")

    db_path = Path(args.db) if args.db else DEFAULT_DB

    if args.write_chunk_counts:
        if not db_path.is_file():
            print(f"cannot write counts: no DB at {db_path}", file=sys.stderr)
            return 1
        with sqlite3.connect(db_path) as conn:
            write_snapshot(build_snapshot(conn, manifest))
        print(f"wrote {SNAPSHOT_PATH.relative_to(REPO_ROOT)}")
        return 1 if failed else 0

    if args.skip_chunk_counts:
        # An explicit waiver, so say so — the whole point of #157 is that
        # a silent skip is indistinguishable from a passing check.
        print("chunk counts: skipped (--skip-chunk-counts)", file=sys.stderr)
        return 1 if failed else 0

    count_errs: list[str] = []
    if db_path.is_file():
        # Local: the index is authoritative. Check it against the bands,
        # and check the committed snapshot against it so the file CI
        # relies on can't quietly go stale.
        with sqlite3.connect(db_path) as conn:
            count_errs += validate_chunk_counts(
                conn, manifest, corpus_ids=tuple(corpus_ids)
            )
            if SNAPSHOT_PATH.is_file():
                count_errs += snapshot_drift(conn, manifest, load_snapshot())
            else:
                count_errs.append(
                    f"no counts snapshot at "
                    f"{SNAPSHOT_PATH.relative_to(REPO_ROOT)} — run "
                    f"`make generate-authors`"
                )
    elif SNAPSHOT_PATH.is_file():
        # CI: `data/index.sqlite` is gitignored and never built here, so
        # the committed snapshot is the only thing to validate against.
        # This used to fall through to nothing at all (#157).
        print(f"chunk counts: no DB at {db_path}, using committed snapshot")
        count_errs += validate_snapshot(load_snapshot(), manifest)
    else:
        failed = True
        print(
            f"chunk counts: no DB at {db_path} and no snapshot at "
            f"{SNAPSHOT_PATH.relative_to(REPO_ROOT)} — nothing to validate "
            f"against. Run `make generate-authors`, or pass "
            f"--skip-chunk-counts to waive.",
            file=sys.stderr,
        )

    if count_errs:
        failed = True
        print("chunk counts:")
        for e in count_errs:
            print(f"  - {e}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
