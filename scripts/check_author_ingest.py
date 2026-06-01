#!/usr/bin/env python3
"""Verify a corpus author is fully wired for ingest (registry, manifest, rules)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = REPO_ROOT / "src" / "minerva" / "refs" / "rules"
SPECS_DIR = RULES_DIR / "specs"
MANIFEST_PATH = REPO_ROOT / "data" / "authors" / "manifest.yaml"

# Manifest corpus id → ingest/registry IngestSource.id (any match suffices).
CORPUS_TO_INGEST: dict[str, tuple[str, ...]] = {
    "septuagint": ("lxx",),
    "new_testament": ("nt",),
    "descartes": ("descartes_la", "descartes_fr"),
    "spinoza": ("spinoza_la",),
    "augustine": ("augustine_la",),
    "aquinas": ("aquinas_la",),
    "cicero": ("cicero_la", "cicero_en"),
    "origen": ("origen_grc", "origen_eng"),
    "hobbes": ("hobbes", "hobbes_la"),
    "kant": ("kant", "kant_en"),
    "marx": ("marx", "marx_ocr"),
}


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
    ingest_aliases = CORPUS_TO_INGEST.get(corpus_id, (corpus_id,))
    if not any(alias in ingest_ids for alias in ingest_aliases):
        errors.append(
            f"corpus {corpus_id!r} missing from ingest/registry "
            f"(expected one of {ingest_aliases!r})"
        )
    sys.path.insert(0, str(REPO_ROOT / "src"))
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


# Biblical / classical hosts covered by scripture_cite or no outgoing rules yet.
SKIP_RULES: frozenset[str] = frozenset(
    {
        "plato",
        "aristotle",
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
        "aeschylus",
        "sophocles",
        "euripides",
        "theognis",
        "aesop",
        "descartes",  # scripture_cite + future locator rules
    }
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", help="Check one corpus id")
    parser.add_argument("--all", action="store_true", help="Check every manifest corpus")
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
            errs = [e for e in errs if "refs rules" not in e]
        if errs:
            failed = True
            print(f"{cid}:")
            for e in errs:
                print(f"  - {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
